"""Module for VCF Variant Intelligence & ACMG/AMP Clinical Workflows (Phase 3B).

Endpoints:
- POST /api/v1/variants/upload: Upload VCF (.vcf / .vcf.gz), parse, normalize, annotate, ACMG evaluate.
- GET  /api/v1/variants/analyses: List analyses for current session / history.
- GET  /api/v1/variants/analyses/{analysis_id}: Retrieve analysis summary, QC metrics, and prioritized variants.
- GET  /api/v1/variants/analyses/{analysis_id}/variants/{variant_id}: Retrieve full variant detail + ACMG matrix.
- GET  /api/v1/variants/demo-vcf: Return content and filename of verified clinical test trio VCF.
- POST /api/v1/variants/analyses/{analysis_id}/diagnosis-handoff: Pass prioritized genes/HPO to differential diagnosis.
- POST /api/v1/variants/analyses/{analysis_id}/report-handoff: Queue variant findings to clinical reporting.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from backend.app import store
from backend.app.security import current_user, require
from backend.app.services import registry
from ml_services.config import SEEDS_DIR

router = APIRouter(prefix="/api/v1/variants", tags=["variants"])


class VcfUploadResponse(BaseModel):
    analysis_id: str
    filename: str
    patient_id: Optional[str] = None
    qc_metrics: Dict[str, Any]
    variants_count: int
    duration_seconds: float


class DiagnosisHandoffRequest(BaseModel):
    variant_ids: List[str] = Field(default_factory=list)
    patient_id: Optional[str] = None
    hpo_ids: Optional[List[str]] = Field(default_factory=list)
    state: Optional[str] = None
    community: Optional[str] = None
    sex: Optional[str] = None


class ReportHandoffRequest(BaseModel):
    variant_ids: List[str] = Field(default_factory=list)
    patient_id: Optional[str] = None
    include_acmg_matrix: bool = True
    clinical_notes: Optional[str] = None


@router.post("/upload")
async def upload_vcf(
    file: UploadFile = File(...),
    patient_id: Optional[str] = Form(default=None),
    hpo_ids_json: Optional[str] = Form(default=None),
    user: dict = Depends(require("variants:write")),
):
    """Upload and process a clinical VCF file (.vcf or .vcf.gz)."""
    filename = file.filename or "unknown.vcf"
    if not (filename.endswith(".vcf") or filename.endswith(".vcf.gz") or filename.endswith(".txt")):
        raise HTTPException(status_code=400, detail="Uploaded file must be a VCF (.vcf or .vcf.gz)")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded VCF file is empty")

    patient_hpos: List[str] = []
    if hpo_ids_json:
        try:
            parsed = json.loads(hpo_ids_json)
            if isinstance(parsed, list):
                patient_hpos = [str(x) for x in parsed]
        except Exception:
            pass

    # If patient_id given and no HPOs passed, see if patient record has HPOs in store
    if patient_id and not patient_hpos:
        patient = store.get_patient(patient_id)
        if patient and patient.get("hpo_ids"):
            patient_hpos = patient.get("hpo_ids", [])

    analysis = registry.variants.analyze_vcf(
        vcf_content=content,
        filename=filename,
        patient_id=patient_id,
        patient_hpo_ids=patient_hpos,
        created_by=user.get("username", "clinician"),
    )

    # Audit and record event
    if patient_id:
        store.add_event(patient_id, "vcf_analysis", {
            "analysis_id": analysis["analysis_id"],
            "filename": filename,
            "qc_metrics": analysis["qc_metrics"],
        })
    store.audit(user["username"], "variants.upload", patient_id or "", f"file={filename}, total={analysis['qc_metrics']['total_variants']}")

    return analysis


@router.get("/analyses")
def list_analyses(user: dict = Depends(require("variants:read"))):
    """List recent VCF analyses in this session."""
    return registry.variants.list_analyses()


@router.get("/analyses/{analysis_id}")
def get_analysis_detail(analysis_id: str, user: dict = Depends(require("variants:read"))):
    """Get full prioritized variant results and QC metrics for an analysis."""
    analysis = registry.variants.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")
    return analysis


@router.get("/analyses/{analysis_id}/variants/{variant_id:path}")
def get_variant_detail(analysis_id: str, variant_id: str, user: dict = Depends(require("variants:read"))):
    """Retrieve deep clinical detail, ACMG evidence breakdown, and population frequencies."""
    analysis = registry.variants.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")
    
    # Locate variant
    for v in analysis["variants"]:
        if v["variant_id"] == variant_id or v["hgvs"] == variant_id:
            return v
            
    raise HTTPException(status_code=404, detail=f"Variant '{variant_id}' not found in analysis '{analysis_id}'")


@router.get("/demo-vcf")
def get_demo_vcf(user: dict = Depends(require("variants:read"))):
    """Return pre-packaged verified clinical trio VCF for 1-click evaluation."""
    demo_path = SEEDS_DIR / "clinical_sample_trio.vcf"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="Demo clinical VCF file not found")
    content = demo_path.read_text(encoding="utf-8")
    return {
        "filename": "clinical_sample_trio.vcf",
        "content": content,
        "sample_description": "Verified clinical trio with pathogenic ATP7B (Wilson Disease), HBB (Sickle Cell/HbS), and BRCA1 variants.",
    }


@router.post("/analyses/{analysis_id}/diagnosis-handoff")
def handoff_to_diagnosis(analysis_id: str, payload: DiagnosisHandoffRequest, user: dict = Depends(require("diagnosis:run"))):
    """Pass prioritized variants/genes into differential diagnosis engine."""
    analysis = registry.variants.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")

    # Collect genes from selected or top variants
    target_variants = []
    if payload.variant_ids:
        target_variants = [v for v in analysis["variants"] if v["variant_id"] in payload.variant_ids]
    else:
        target_variants = analysis["variants"][:3]

    candidate_genes = list({v["gene_symbol"] for v in target_variants if v.get("gene_symbol")})

    # Combine HPOs
    hpos = list(set((payload.hpo_ids or []) + analysis.get("patient_hpo_ids", [])))

    # If no HPOs provided, infer standard phenotypes for the candidate genes from KG
    if not hpos and registry.graph:
        for gene in candidate_genes:
            diseases = registry.graph.neighbors(gene, "ASSOCIATED_WITH")
            for d in diseases:
                for edge in registry.graph.edges_from(d["id"], "HAS_PHENOTYPE"):
                    hpos.append(edge["dst"])
                    if len(hpos) >= 5:
                        break

    context = {"state": payload.state, "community": payload.community, "sex": payload.sex}
    diag_result = registry.diagnosis.diagnose(hpos, context, top_k=5, explain=True) if hpos else {"differential": []}

    return {
        "analysis_id": analysis_id,
        "candidate_genes": candidate_genes,
        "variants_forwarded": [v["variant_id"] for v in target_variants],
        "hpo_ids": hpos,
        "diagnosis_result": diag_result,
    }


@router.post("/analyses/{analysis_id}/report-handoff")
def handoff_to_report(analysis_id: str, payload: ReportHandoffRequest, user: dict = Depends(require("clinical:write"))):
    """Queue variant findings and ACMG evidence into clinical report summary."""
    analysis = registry.variants.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")

    target_variants = []
    if payload.variant_ids:
        target_variants = [v for v in analysis["variants"] if v["variant_id"] in payload.variant_ids]
    else:
        target_variants = [v for v in analysis["variants"] if v["priority_tier"].startswith("Tier 1")]

    report_bundle = {
        "analysis_id": analysis_id,
        "patient_id": payload.patient_id or analysis.get("patient_id"),
        "timestamp": analysis.get("timestamp"),
        "total_analyzed": analysis["qc_metrics"]["total_variants"],
        "reported_variants": target_variants,
        "clinical_notes": payload.clinical_notes or "Prioritized by Genomera ACMG/AMP variant pipeline.",
        "status": "ready_for_review",
    }

    if payload.patient_id:
        store.add_event(payload.patient_id, "variant_report_bundle", report_bundle)

    return report_bundle
