"""Module 5 endpoints: population-stratified pharmacogenomic risk."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app import store
from backend.app.models import PgxRequest
from backend.app.security import require
from backend.app.services import registry
from ml_services.pharmacogenomics.case_pgx import PgxCaseError
from ml_services.reproductive.report_generator import generate_pgx_report

router = APIRouter(prefix="/api/v1/pgx", tags=["pharmacogenomics"])


@router.post("/check")
def check_prescription(payload: PgxRequest, user: dict = Depends(require("pgx:read"))):
    """Screen a prescription for drug-gene risk using Indian allele frequencies."""
    result = registry.pgx.check_drugs(
        payload.drugs, state=payload.state or "", ethnicity=payload.ethnicity or "",
        known_genotypes=payload.known_genotypes, age=payload.age, sex=payload.sex or "",
    )
    result["report"] = generate_pgx_report(result, lang=payload.lang)
    store.audit(user["username"], "pgx.check", "", f"drugs={','.join(payload.drugs)}")
    return result


@router.get("/coverage")
def coverage(user: dict = Depends(require("pgx:read"))):
    """Drug-gene coverage table with Indian allele frequencies (dashboard tile)."""
    rows = registry.pgx.drug_gene_table()
    critical = [r for r in rows if r.get("severity") == "critical"]
    return {"n_pairs": len(rows), "n_critical": len(critical), "rows": rows}


@router.get("/allele-frequencies")
def allele_frequencies(gene: str | None = None, state: str | None = None,
                       user: dict = Depends(require("pgx:read"))):
    engine = registry.pgx
    if gene:
        return engine.allele_frequency(gene, state=state or "")
    return {"rows": engine.af_rows}


@router.get("/genes/{gene}/metabolizer-inference")
def metabolizer_inference(gene: str, state: str | None = None, ethnicity: str | None = None,
                          sex: str | None = None, user: dict = Depends(require("pgx:read"))):
    """Hardy-Weinberg inference of metabolizer phenotype probabilities from population AF."""
    x_linked = gene.upper() == "G6PD"
    return registry.pgx.infer_metabolizer_probabilities(gene, state=state or "",
                                                        ethnicity=ethnicity or "",
                                                        x_linked=x_linked, sex=sex or "")


# ----------------------- Phase 9: case-level PGx (genotype -> phenotype -> drug) -----------------------

def _case(fn, *a):
    try:
        return fn(*a)
    except PgxCaseError as ex:
        raise HTTPException(status_code=404, detail=str(ex))


@router.get("/case/{patient_id}")
def case_workspace(patient_id: str, user: dict = Depends(require("pgx:read"))):
    """Genotype, diplotype, predicted phenotype and gene->drug matrix derived from the case's variant analysis."""
    out = _case(registry.case_pgx.workspace, patient_id)
    store.audit(user["username"], "pgx.case_view", patient_id, "")
    return out


@router.get("/case/{patient_id}/drug")
def case_drug(patient_id: str, name: str = Query(..., min_length=2, max_length=60), user: dict = Depends(require("pgx:read"))):
    return _case(registry.case_pgx.drug, patient_id, name)


@router.get("/case/{patient_id}/report-section")
def case_report_section(patient_id: str, user: dict = Depends(require("pgx:read"))):
    return _case(registry.case_pgx.report_section, patient_id)
