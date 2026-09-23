"""Module 9: voice-guided triage engine (Green / Yellow / Red).

Patent claim #9: voice-driven genomic triage for rural Indian dialects on offline mobile.

Design notes
------------
* The questionnaire is data-driven (data/seeds/asha_questionnaire.json) so field teams can
  revise wording without code changes.
* Triage is rule-based and explainable on purpose: an ASHA worker must be able to justify
  a RED referral to a family, and the district health officer must be able to audit it.
* Model-based symptom extraction (Module 1 NER over the ASR transcript) is layered on top
  of the rules rather than replacing them — the rules stay the safety net.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ml_services.config import SEEDS_DIR
from ml_services.reproductive.report_generator import generate_triage_referral
from ml_services.utils import read_json

TRIAGE_ORDER = {"green": 0, "yellow": 1, "red": 2}
TRIAGE_ACTIONS = {
    "green": {
        "en": "Monitor at home. ASHA follow-up visit in 2 weeks. Teach danger signs.",
        "hi": "घर पर निगरानी रखें। 2 हफ्ते में ASHA दोबारा मिलें। खतरे के संकेत समझाएँ।",
        "facility": "None - community follow-up",
    },
    "yellow": {
        "en": "Refer to the Primary Health Centre (PHC) within 3 days with this referral slip.",
        "hi": "3 दिन के अंदर नज़दीकी प्राथमिक स्वास्थ्य केंद्र (PHC) जाएँ और यह पर्ची दिखाएँ।",
        "facility": "Primary Health Centre (PHC)",
    },
    "red": {
        "en": "Urgent referral TODAY to a district hospital or genetic specialist centre.",
        "hi": "आज ही जिला अस्पताल या आनुवंशिक विशेषज्ञ केंद्र में तुरंत रेफर करें।",
        "facility": "District Hospital / Genetic Specialist Centre",
    },
}


class TriageEngine:
    def __init__(self, questionnaire_path: Optional[str] = None, ner=None, mapper=None):
        qpath = questionnaire_path or (SEEDS_DIR / "asha_questionnaire.json")
        self.questionnaire = read_json(qpath)
        self.questions = {q["id"]: q for q in self.questionnaire["questions"]}
        self.red_flag_rules = self.questionnaire.get("red_flag_rules", {})
        self.ner = ner
        self.mapper = mapper

    # --------------------------- questionnaire-driven path ---------------------------

    def triage_answers(self, answers: Dict[str, str], patient: Optional[dict] = None) -> dict:
        """answers: {question_id: "haan"/"nahi"/"thoda"/number/...}"""
        patient = patient or {}
        symptoms: List[str] = []
        flagged: List[dict] = []
        hpo_ids: List[str] = []

        for qid, q in self.questions.items():
            if qid not in answers:
                continue
            ans = str(answers[qid]).strip().lower()
            positive = ans in ("haan", "yes", "y", "1", "true", "thoda", "kabhi_kabhi", "sometimes")
            negative = ans in ("nahi", "no", "n", "0", "false")

            sym = None
            if positive and q.get("symptom_if_positive"):
                sym = q["symptom_if_positive"]
            elif negative and q.get("symptom_if_negative"):
                sym = q["symptom_if_negative"]
            if sym:
                symptoms.append(sym)
                if q.get("hpo_id"):
                    hpo_ids.append(q["hpo_id"])
                if q.get("red_flag"):
                    rule = self.red_flag_rules.get(q["red_flag"], {})
                    flagged.append({
                        "red_flag": q["red_flag"],
                        "question_id": qid,
                        "question_hi": q.get("hi", ""),
                        "answer": ans,
                        "triage": rule.get("triage", "yellow"),
                        "why": rule.get("why", ""),
                    })

        return self._finalize(symptoms, flagged, hpo_ids, patient, source="questionnaire")

    # --------------------------- free-text / ASR path ---------------------------

    def triage_text(self, transcript: str, patient: Optional[dict] = None, lang: str = "hi") -> dict:
        """Run Module 1+2 over an ASR transcript, then apply the red-flag rules."""
        patient = patient or {}
        from ml_services.nlp.clinical_ner import get_ner

        ner = self.ner or get_ner()
        extracted = ner.extract(transcript)
        symptoms = [e["text"] for e in extracted["entities"] if e["label"] == "SYMPTOM"]
        hpo_ids = [e["hpo_id"] for e in extracted["entities"] if e.get("hpo_id")]

        flagged: List[dict] = []
        red_flag_triggers = {
            "seizures": ["daura", "jhatke", "fits", "seizure", "mirgi"],
            "progressive_weakness": ["kamzori", "weakness", "uth nahi", "gir"],
            "severe_pallor": ["safed", "pale", "khoon ki kami"],
            "hemolysis_suspected": ["peshaab", "urine", "laal", "dark urine"],
            "jaundice": ["pila", "peela", "piliya", "jaundice"],
            "delayed_development": ["der se", "nahi bola", "nahi chala", "delay"],
            "family_history": ["rishtedaar", "cousin", "parivaar"],
        }
        low = transcript.lower()
        for flag, needles in red_flag_triggers.items():
            if any(n in low for n in needles):
                rule = self.red_flag_rules.get(flag, {})
                flagged.append({"red_flag": flag, "trigger_text": next(n for n in needles if n in low),
                                "triage": rule.get("triage", "yellow"), "why": rule.get("why", "")})

        result = self._finalize(symptoms, flagged, hpo_ids, patient, source="asr_transcript")
        result["transcript"] = transcript
        result["extracted_entities"] = extracted["entities"]
        result["is_code_mixed"] = extracted.get("is_code_mixed", False)
        return result

    # --------------------------- scoring ---------------------------

    def _finalize(self, symptoms: List[str], flagged: List[dict], hpo_ids: List[str],
                  patient: dict, source: str) -> dict:
        color = "green"
        for f in flagged:
            if TRIAGE_ORDER.get(f["triage"], 1) > TRIAGE_ORDER[color]:
                color = f["triage"]
        # symptom-count escalation when no explicit flag fired
        if color == "green" and len(set(symptoms)) >= 3:
            color = "yellow"
        if color == "yellow" and len(set(symptoms)) >= 5:
            color = "red"

        action = TRIAGE_ACTIONS[color]
        age = patient.get("age")
        # very young infants with any flagged sign escalate
        if age is not None and isinstance(age, (int, float)) and age < 1 and color == "yellow":
            color = "red"
            action = TRIAGE_ACTIONS["red"]

        referral_facility = self._pick_facility(patient, color)
        result = {
            "triage_color": color,
            "source": source,
            "reported_symptoms": sorted(set(symptoms)),
            "hpo_ids": sorted(set(hpo_ids)),
            "red_flags": [f["red_flag"] for f in flagged],
            "red_flag_details": flagged,
            "recommendation": action["en"],
            "recommendation_hi": action["hi"],
            "referral_facility": referral_facility,
            "patient_name": patient.get("name", "गोपनीय / confidential"),
            "age": age,
            "village": patient.get("village", ""),
            "district": patient.get("district", ""),
            "state": patient.get("state", ""),
            "asha_id": patient.get("asha_id", ""),
            "disclaimer": ("Rule-based triage for ASHA referral support only. Not a diagnosis; "
                           "a clinician must confirm."),
        }
        result["referral_letter_hi"] = generate_triage_referral(result, lang="hi")["markdown"]
        result["referral_letter_en"] = generate_triage_referral(result, lang="en")["markdown"]
        return result

    def _pick_facility(self, patient: dict, color: str) -> str:
        if color == "green":
            return "Community follow-up (no facility referral)"
        from ml_services.etl.graph_store import load_processed

        graph = load_processed()
        state = patient.get("state", "")
        if graph and color == "red":
            labs = [n for n in graph.by_type("Lab") if n.get("state") == state]
            if labs:
                return f"{labs[0]['name']} ({labs[0]['city']}) - genetic testing available"
        return TRIAGE_ACTIONS[color]["facility"]

    # --------------------------- offline sync payload ---------------------------

    def to_offline_record(self, triage_result: dict) -> dict:
        """Compact record the Flutter app stores in SQLite and syncs when online."""
        return {
            "local_id": f"{triage_result.get('asha_id', 'asha')}-{abs(hash(str(triage_result.get('reported_symptoms')))) % 10**8}",
            "triage_color": triage_result["triage_color"],
            "symptoms": triage_result["reported_symptoms"],
            "hpo_ids": triage_result["hpo_ids"],
            "village": triage_result.get("village", ""),
            "district": triage_result.get("district", ""),
            "state": triage_result.get("state", ""),
            "age": triage_result.get("age"),
            "sync_state": "pending",
            "schema_version": 1,
        }


if __name__ == "__main__":
    engine = TriageEngine()
    demo_answers = {"q_age": 2, "q_weakness": "haan", "q_seizure": "nahi", "q_pallor": "haan",
                    "q_development": "thoda", "q_family": "haan"}
    res = engine.triage_answers(demo_answers, {"age": 2, "village": "Bijapur", "district": "Bijapur",
                                              "state": "Chhattisgarh", "asha_id": "ASHA-001"})
    print(f"Triage: {res['triage_color'].upper()}")
    print("Symptoms:", res["reported_symptoms"])
    print("Red flags:", res["red_flags"])
    print("Action (hi):", res["recommendation_hi"])
    print("Facility:", res["referral_facility"])
    print("\n--- ASR transcript path ---")
    t = engine.triage_text("Bachche ko teen din se bukhaar hai aur daura pad raha hai, khoon ki kami bhi hai",
                           {"age": 3, "village": "Kondagaon", "state": "Chhattisgarh"})
    print("Triage:", t["triage_color"].upper(), "| flags:", t["red_flags"])
    print("Offline record:", engine.to_offline_record(t))
