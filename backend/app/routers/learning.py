"""Module 10 endpoints: active learning queue, clinician feedback, PubMed KG updates, drift."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.app.models import FeedbackIn, KgProposalReviewIn
from backend.app.security import require
from backend.app.services import registry
from ml_services.learning_pipeline import drift as drift_mod
from ml_services.learning_pipeline.pubmed_scraper import run_pipeline_queries

router = APIRouter(prefix="/api/v1/learning", tags=["continuous-learning"])


@router.get("/queue")
def review_queue(user: dict = Depends(require("xai:read"))):
    """Cases the model was unsure about (uncertainty sampling + query-by-committee)."""
    return {"stats": registry.active_learning.stats(), "items": registry.active_learning.items[-50:]}


@router.post("/feedback")
def submit_feedback(payload: FeedbackIn, user: dict = Depends(require("feedback:write"))):
    """Doctor confirms/corrects a suggestion; corrections become training data."""
    try:
        result = registry.active_learning.record_feedback(
            payload.queue_index, reviewer=user["username"], decision=payload.decision,
            corrected_hpo=payload.corrected_hpo, corrected_diagnosis=payload.corrected_diagnosis,
            comment=payload.comment,
        )
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


@router.get("/training-export")
def training_export(user: dict = Depends(require("xai:read"))):
    return registry.active_learning.training_export()


@router.post("/kg-proposals")
def kg_proposals(payload: KgProposalReviewIn, user: dict = Depends(require("kg:propose"))):
    """Scrape PubMed, extract triples, and rank proposals for curator review."""
    articles = run_pipeline_queries(queries=[payload.query] if payload.query else None,
                                    retmax=10, offline=payload.offline)["articles"]
    proposals = registry.triple_extractor.extract_batch(articles)
    ranked = registry.kg_update.rank_for_review(proposals["proposals"])
    return {"n_articles": len(articles), "n_proposals": len(ranked),
            "proposals": ranked[:30],
            "review_note": ("Approve with POST /learning/kg-proposals/apply. Nothing is written to the "
                            "knowledge graph without an explicit review action.")}


@router.post("/kg-proposals/apply")
def apply_proposals(payload: KgProposalReviewIn = KgProposalReviewIn(),
                    proposals: Optional[List[dict]] = None,
                    user: dict = Depends(require("kg:propose"))):
    if not proposals:
        raise HTTPException(status_code=400, detail="provide the proposals list returned by /kg-proposals")
    ranked = registry.kg_update.rank_for_review(proposals)
    accepts = [p["proposal_id"] for p in ranked if p["review_priority"] >= payload.auto_accept_priority]
    result = registry.kg_update.apply_review(ranked, reviewer=user["username"], accepts=accepts)
    registry.reload_graph()
    return result


@router.get("/drift")
def drift_status(user: dict = Depends(require("xai:read"))):
    """Concept-drift monitor over recent vs reference streams (synthetic demo when no feed)."""
    report = drift_mod.simulate_drift_example()
    return {"demo": True, "report": report,
            "note": ("Wire real streams (symptom counts, confidence, disease mix) from the clinical "
                     "events table for production drift monitoring.")}


@router.get("/kg-history")
def kg_history(user: dict = Depends(require("kg:read"))):
    """Audit trail of literature-driven KG edits."""
    from ml_services.config import PROCESSED_DIR
    from ml_services.utils import read_json

    path = PROCESSED_DIR / "kg_review_state.json"
    if not path.exists():
        return {"history": [], "note": "No KG reviews applied yet."}
    return read_json(path)
