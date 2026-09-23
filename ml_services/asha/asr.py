"""ASR service for the ASHA interface (Module 9).

Backends, chosen automatically:
  1. faster-whisper (CTranslate2, int8 quantized) — the on-device/server default. On a
     6GB laptop GPU `whisper-small` int8 runs comfortably; `whisper-tiny`/`base` for phones.
  2. transformers Whisper / IndicWhisper checkpoints (`ai4bharat/IndicWhisper`) — better
     Hindi/Indic accuracy; use when the model is downloaded.
  3. No backend -> raises a clear error telling you the pip command (never silently
     produces fake transcripts).

Fine-tuning recipe (whisper-small LoRA on IndicVoices-Hindi + Common Voice-Hi) lives in
docs/TRAINING_RECIPES.md and ml_services/asha/train_whisper.py.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from ml_services.config import MODELS_DIR
from ml_services.asha.vocab_corrector import MedicalVocabCorrector

# Medical/domain prompt biases Whisper toward clinical vocabulary (huge quality win)
DOMAIN_PROMPT_HI = ("मरीज़ की शिकायत: बुखार, खांसी, कमजोरी, पीलिया, दौरा, सूजन, "
                    "खून की कमी, दवा - क्लोपिडोग्रेल, वारफ़ेरिन, फ़ेनिटॉइन, प्राइमाक्वीन।")
DOMAIN_PROMPT_EN = ("Clinical note in Indian English/Hinglish: fever, cough, weakness, jaundice, "
                    "seizures, swelling, anemia; drugs: clopidogrel, warfarin, phenytoin, primaquine.")


class ASRService:
    def __init__(self, model_size: str = "small", device: str = "auto", compute_type: str = "int8",
                 language: str = "hi", corrector: Optional[MedicalVocabCorrector] = None):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.corrector = corrector or MedicalVocabCorrector()
        self._model = None
        self.backend = None

    # ------------------------------ loading ------------------------------

    def _load(self):
        if self._model is not None:
            return self._model
        local_dir = MODELS_DIR / f"whisper-{self.model_size}-hi"
        try:
            from faster_whisper import WhisperModel

            source = str(local_dir) if local_dir.exists() else self.model_size
            self._model = WhisperModel(source, device=self.device, compute_type=self.compute_type)
            self.backend = "faster-whisper"
            return self._model
        except Exception:
            pass
        try:
            from transformers import pipeline

            model_id = str(local_dir) if local_dir.exists() else f"openai/whisper-{self.model_size}"
            self._model = pipeline("automatic-speech-recognition", model=model_id, device_map="auto")
            self.backend = "transformers"
            return self._model
        except Exception as exc:
            raise RuntimeError(
                "No ASR backend available. Install one of:\n"
                "  pip install faster-whisper            (recommended, int8 quantized)\n"
                "  pip install transformers torch         (Whisper/IndicWhisper)\n"
                "Then re-run. Original error: " + str(exc)
            ) from exc

    # ------------------------------ transcribe ------------------------------

    def transcribe(self, audio_path: str, language: Optional[str] = None, correct_vocab: bool = True) -> Dict:
        model = self._load()
        lang = language or self.language
        initial_prompt = DOMAIN_PROMPT_HI if lang.startswith(("hi", "hin")) else DOMAIN_PROMPT_EN

        if self.backend == "faster-whisper":
            segments, info = model.transcribe(audio_path, language=lang, initial_prompt=initial_prompt,
                                              vad_filter=True, beam_size=5)
            text = " ".join(s.text.strip() for s in segments).strip()
            duration = getattr(info, "duration", None)
        else:
            out = model(audio_path, generate_kwargs={"language": lang, "initial_prompt": initial_prompt},
                        return_timestamps=False)
            text = out.get("text", "").strip()
            duration = None

        result = {"transcript_raw": text, "language": lang, "backend": self.backend,
                  "model": self.model_size, "duration_seconds": duration,
                  "initial_prompt_used": bool(initial_prompt)}
        if correct_vocab and text:
            corrected = self.corrector.correct_text(text)
            result.update({"transcript": corrected["corrected"], "vocab_corrections": corrected["changes"],
                           "n_corrections": corrected["n_changes"]})
        else:
            result.update({"transcript": text, "vocab_corrections": [], "n_corrections": 0})
        return result

    def asr_then_triage(self, audio_path: str, patient: Optional[dict] = None, language: Optional[str] = None) -> Dict:
        """Full ASHA pipeline: voice -> transcript -> vocab correction -> NER/HPO -> triage."""
        from ml_services.asha.triage_engine import TriageEngine

        asr = self.transcribe(audio_path, language=language)
        triage = TriageEngine().triage_text(asr["transcript"], patient or {})
        return {"asr": asr, "triage": triage}


def quantization_plan() -> Dict:
    """Documented on-device plan for the Flutter app (2GB-RAM Android target)."""
    return {
        "server_or_4G": {"model": "whisper-small int8 (CTranslate2)", "approx_size_mb": 480,
                         "note": "Best accuracy; use when the ASHA phone has connectivity."},
        "offline_phone": {"model": "whisper-base/tiny int8 or IndicWhisper-distilled", "approx_size_mb": 75,
                          "note": "Runs on mid-range Android; pair with the lexicon corrector to recover accuracy."},
        "distillation_target": {"model": "distilled IndicWhisper (4-6 layers)", "approx_size_mb": 120,
                                "note": "Train with the Whisper-small teacher on IndicVoices-Hindi + your "
                                        "recorded rural-accent set (1-2 hours is enough to matter)."},
        "vocab_biasing": "initial_prompt + post-hoc lexicon corrector (ml_services/asha/vocab_corrector.py)",
    }


if __name__ == "__main__":
    print("ASR backend status:")
    svc = ASRService()
    try:
        svc._load()
        print("  backend:", svc.backend, "-> ready")
    except RuntimeError as exc:
        print("  not installed:", str(exc).splitlines()[0])
    print("\nOn-device quantization plan:")
    for k, v in quantization_plan().items():
        print(f"  {k}: {v}")
    print("\nVocab corrector demo (what saves accuracy on rural accents):")
    c = MedicalVocabCorrector()
    for t in ["cloth of a girl", "pil jaundice", "war farin"]:
        print("  ", t, "->", c.suggest(t.split()[-1] if " " not in t else t)[:2] or "no suggestion")
