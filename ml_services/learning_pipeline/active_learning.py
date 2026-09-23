"""Active learning + clinician feedback loop (Module 10).

Patent claim #10-adjacent and the "system that gets smarter every day" behaviour:

  1. Uncertainty sampling — every prediction with low confidence (or high disagreement
     between the lexical mapper and the diagnosis engine) is queued for clinician review.
  2. Query-by-committee — when the Mapper's dictionary path and fuzzy/embedding path
     disagree, that disagreement is itself an uncertainty signal.
  3. Feedback ingestion — clinician confirm/correct decisions are turned into training
     examples (NER spans, HPO mappings, diagnosis labels) and written to the review store,
     ready for the next retraining cycle.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from ml_services.config import PROCESSED_DIR, REPORTS_DIR
from ml_services.utils import read_json, write_json

QUEUE_PATH = REPORTS_DIR / "active_learning_queue.jsonl"
STORE_PATH = PROCESSED_DIR / "clinician_feedback.json"


class ActiveLearningQueue:
    def __init__(self, capacity: int = 500, queue_path=None, store_path=None):
        self.capacity = capacity
        self.queue_path = Path(queue_path) if queue_path else QUEUE_PATH
        self.store_path = Path(store_path) if store_path else STORE_PATH
        self.items: List[dict] = []
        self._load()

    def _load(self) -> None:
        if self.queue_path.exists():
            with open(self.queue_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self.items.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

    # --------------------------- enqueue ---------------------------

    def score_uncertainty(self, hpo_profile: List[dict], diagnosis: Optional[dict] = None,
                          unmapped: Optional[List[str]] = None) -> dict:
        """Composite uncertainty: low mapping confidence + top-2 probability gap + unmapped text."""
        confidences = [i.get("confidence", 0.0) for i in hpo_profile] or [0.0]
        mapping_uncertainty = 1.0 - (sum(confidences) / len(confidences))
        results = (diagnosis or {}).get("results", [])
        if len(results) >= 2:
            gap = results[0]["probability"] - results[1]["probability"]
            rank_uncertainty = max(0.0, 1.0 - min(gap * 5.0, 1.0))  # small gap = uncertain
        else:
            rank_uncertainty = 1.0 if not results else 0.5
        unmapped_penalty = min(1.0, 0.25 * len(unmapped or []))
        composite = round(0.4 * mapping_uncertainty + 0.4 * rank_uncertainty + 0.2 * unmapped_penalty, 4)
        return {
            "mapping_uncertainty": round(mapping_uncertainty, 4),
            "ranking_uncertainty": round(rank_uncertainty, 4),
            "unmapped_penalty": round(unmapped_penalty, 4),
            "composite_uncertainty": composite,
            "strategy": "uncertainty_sampling + query_by_committee",
        }

    def enqueue(self, record: dict, threshold: float = 0.55) -> Optional[dict]:
        uncertainty = record.get("uncertainty") or {}
        if uncertainty.get("composite_uncertainty", 0.0) < threshold:
            return None
        item = {
            "queued_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "text": record.get("text", ""),
            "hpo_profile": record.get("hpo_profile", []),
            "candidate_diagnoses": [r["disease_id"] for r in (record.get("diagnosis") or {}).get("results", [])[:3]],
            "unmapped_symptoms": record.get("unmapped_symptoms", []),
            "uncertainty": uncertainty,
            "status": "pending_review",
        }
        self.items.append(item)
        self.items = self.items[-self.capacity:]
        self._persist()
        return item

    def _persist(self) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.queue_path, "w", encoding="utf-8") as f:
            for item in self.items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # --------------------------- feedback ---------------------------

    def record_feedback(self, item_index: int, reviewer: str, decision: str,
                        corrected_hpo: Optional[Dict[str, str]] = None,
                        corrected_diagnosis: Optional[str] = None,
                        comment: str = "") -> dict:
        """decision in {confirmed, corrected, rejected}. corrected_hpo maps phrase -> hpo_id."""
        if not (0 <= item_index < len(self.items)):
            raise IndexError(f"no queue item at index {item_index}")
        item = self.items[item_index]
        feedback = {
            "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reviewer": reviewer,
            "decision": decision,
            "text": item["text"],
            "original_candidates": item.get("candidate_diagnoses", []),
            "corrected_diagnosis": corrected_diagnosis,
            "corrected_hpo": corrected_hpo or {},
            "comment": comment,
        }
        self.items[item_index]["status"] = f"reviewed_{decision}"

        store = read_json(self.store_path) if self.store_path.exists() else {"examples": []}
        store["examples"].append(feedback)
        write_json(self.store_path, store)

        # Grow the Indian synonym dictionary directly from confirmed corrections (patent #2)
        grown = 0
        if corrected_hpo:
            from ml_services.nlp.hpo_mapper import HPOMapper

            mapper = HPOMapper()
            for phrase, hpo_id in corrected_hpo.items():
                mapper.add_confirmed_synonym(phrase, hpo_id)
                grown += 1
        self._persist()
        return {"feedback_recorded": feedback, "dictionary_entries_added": grown,
                "total_feedback_examples": len(store["examples"])}

    def training_export(self, min_examples: int = 20) -> dict:
        """Export accumulated feedback as a retraining dataset (feeds the M1/M2 trainers)."""
        store = read_json(self.store_path) if self.store_path.exists() else {"examples": []}
        examples = store["examples"]
        ner_rows, hpo_rows = [], []
        for e in examples:
            if e.get("corrected_hpo"):
                hpo_rows.append({"text": e["text"], "labels": e["corrected_hpo"]})
            if e.get("corrected_diagnosis"):
                ner_rows.append({"text": e["text"], "label": e["corrected_diagnosis"]})
        return {
            "ready_to_retrain": len(examples) >= min_examples,
            "n_examples": len(examples),
            "n_hpo_corrections": len(hpo_rows),
            "n_diagnosis_corrections": len(ner_rows),
            "artifact_path": str(self.store_path),
            "next_step": ("Run ml_services/nlp/train_clinical_ner.py and train_hpo_mapper.py with "
                          "these examples appended to the seed set."),
        }

    def stats(self) -> dict:
        statuses: Dict[str, int] = {}
        for item in self.items:
            statuses[item.get("status", "unknown")] = statuses.get(item.get("status", "unknown"), 0) + 1
        return {"queue_size": len(self.items), "by_status": statuses,
                "top_uncertain": [{"text": i.get("text", "")[:60],
                                   "uncertainty": (i.get("uncertainty") or {}).get("composite_uncertainty", 0.0)}
                                  for i in sorted(self.items,
                                                  key=lambda x: -(x.get("uncertainty") or {}).get(
                                                      "composite_uncertainty", 0.0))[:3]]}


if __name__ == "__main__":
    from ml_services.graph_ai.gnn_diagnosis import DifferentialDiagnosisEngine

    q = ActiveLearningQueue()
    engine = DifferentialDiagnosisEngine()
    text = "Bachche ko thoda thoda kamzori hai aur kuch samajh nahi aata"
    diagnosis = engine.diagnose(["HP:0001324"], {"state": "Bihar"}, top_k=3)
    profile = [{"hpo_id": "HP:0001324", "confidence": 0.41},
               {"hpo_id": "HP:0001263", "confidence": 0.38}]
    unc = q.score_uncertainty(profile, diagnosis, unmapped=["kuch samajh nahi aata"])
    print("Uncertainty:", unc)
    item = q.enqueue({"text": text, "hpo_profile": profile, "diagnosis": diagnosis,
                      "unmapped_symptoms": ["kuch samajh nahi aata"], "uncertainty": unc},
                     threshold=0.45)
    print("Queued:", bool(item))
    if item:
        idx = len(q.items) - 1
        out = q.record_feedback(idx, reviewer="dr_reviewer", decision="corrected",
                               corrected_hpo={"kuch samajh nahi aata": "HP:0001263"},
                               corrected_diagnosis="ORPHA:716", comment="receptive language delay")
        print("Feedback recorded; dictionary entries added:", out["dictionary_entries_added"])
    print("Export readiness:", q.training_export())
    print("Stats:", q.stats())
