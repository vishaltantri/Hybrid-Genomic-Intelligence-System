"""KG update manager (Module 10).

Closes the loop: PubMed -> triple proposals -> expert review -> knowledge graph.
Additions are appended to data/processed/kg_updates.jsonl with reviewer, timestamp and
evidence, so any graph edge can be traced back to a sentence in a paper. Nothing is
auto-inserted: `auto_accept_threshold` only *ranks* proposals for review.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from ml_services.config import PROCESSED_DIR
from ml_services.etl.graph_store import GraphData, load_processed, save_processed
from ml_services.utils import read_json, write_json

UPDATES_PATH = PROCESSED_DIR / "kg_updates.jsonl"
REVIEW_PATH = PROCESSED_DIR / "kg_review_state.json"


class KGUpdateManager:
    def __init__(self, graph: Optional[GraphData] = None):
        self.graph = graph or load_processed()

    def rank_for_review(self, proposals: List[dict]) -> List[dict]:
        """Prioritise proposals: high confidence + entity already in graph + Indian relevance."""
        ranked = []
        for p in proposals:
            score = float(p.get("confidence", 0.0))
            if self.graph:
                if p.get("subject_type") == "Gene" and self.graph.node("Gene", p["subject"]):
                    score += 0.15
                if self.graph.node("Disease", p.get("object", "")):
                    score += 0.15
            if p.get("subject_type") == "Population":
                score += 0.10
            evidence = (p.get("evidence_sentence") or "").lower()
            if any(k in evidence for k in ("india", "indian", "consanguin", "tribal", "state")):
                score += 0.10
            q = dict(p)
            q["review_priority"] = round(min(score, 1.0), 4)
            ranked.append(q)
        ranked.sort(key=lambda x: -x["review_priority"])
        return ranked

    def apply_review(self, proposals: List[dict], reviewer: str,
                     accepts: Optional[List[str]] = None, persist: bool = True,
                     record_audit: bool = True) -> dict:
        """Accept/reject proposals. accepts=None accepts everything above 0.8 priority.

        persist=False keeps the in-memory graph updated without overwriting
        data/processed/kg.json (used by tests and by dry-run review sessions).
        """
        if accepts is None:
            accepts = [p["proposal_id"] for p in proposals if p.get("review_priority", 0) >= 0.8]
        accepted, rejected = [], []
        for p in proposals:
            (accepted if p["proposal_id"] in accepts else rejected).append(p)

        added_edges = 0
        if self.graph:
            for p in accepted:
                st, ot = p.get("subject_type", "Gene"), p.get("object_type", "Disease")
                if not self.graph.node(st, p["subject"]):
                    self.graph.add_node({"id": p["subject"], "type": st, "name": p["subject"],
                                         "source": f"literature:{p.get('pmid', '')}"})
                if not self.graph.node(ot, p["object"]):
                    self.graph.add_node({"id": p["object"], "type": ot, "name": p["object"],
                                         "source": f"literature:{p.get('pmid', '')}"})
                self.graph.add_edge(p["subject"], p["object"], p["predicate"], st, ot,
                                    evidence_sentence=(p.get("evidence_sentence") or "")[:300],
                                    pmid=p.get("pmid", ""), reviewer=reviewer,
                                    confidence=p.get("confidence", 0.0))
                added_edges += 1
            if persist:
                save_processed(self.graph)

        state = read_json(REVIEW_PATH) if (REVIEW_PATH.exists() and record_audit) else {"history": []}
        entry = {
            "reviewed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reviewer": reviewer,
            "n_accepted": len(accepted),
            "n_rejected": len(rejected),
            "added_edges": added_edges,
            "accepted_ids": [p["proposal_id"] for p in accepted],
            "rejected_ids": [p["proposal_id"] for p in rejected],
        }
        if record_audit:
            state["history"].append(entry)
            write_json(REVIEW_PATH, state)

            UPDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(UPDATES_PATH, "a", encoding="utf-8") as f:
                import json

                for p in accepted:
                    f.write(json.dumps({**p, "reviewer": reviewer,
                                        "applied_utc": entry["reviewed_utc"]},
                                       ensure_ascii=False) + "\n")

        return {"summary": entry,
                "audit_trail": str(UPDATES_PATH),
                "note": "Every added edge carries its evidence sentence and PMID for auditability."}

    def pending_count(self) -> int:
        if not UPDATES_PATH.exists():
            return 0
        with open(UPDATES_PATH, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())


if __name__ == "__main__":
    from ml_services.learning_pipeline.triple_extraction import TripleExtractor

    articles = [{
        "pmid": "99990002",
        "title": "G6PD Mahidol variant in Northeast Indian tribal populations",
        "abstract": ("G6PD Mahidol was found in 3% of Northeast Indian tribal individuals. "
                     "The G6PD variant causes hemolytic anemia after primaquine. "
                     "Consanguinity was reported in 8% of families in the region."),
        "journal": "Indian J Med Res", "year": "2025",
        "url": "https://pubmed.ncbi.nlm.nih.gov/99990002/",
    }]
    proposals = TripleExtractor().extract_batch(articles)["proposals"]
    mgr = KGUpdateManager()
    ranked = mgr.rank_for_review(proposals)
    print(f"Proposals ranked: {len(ranked)}")
    for p in ranked[:5]:
        print(f"  priority={p['review_priority']:.2f}  {p['subject']} --{p['predicate']}--> {p['object']}")
    result = mgr.apply_review(ranked, reviewer="curator_1")
    print("\nReview summary:", result["summary"])
