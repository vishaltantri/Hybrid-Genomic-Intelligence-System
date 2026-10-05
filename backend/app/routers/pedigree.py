"""Genomera Pedigree & Inheritance API (Phase 3E).

All routes are authenticated and need `pedigree:read` / `pedigree:write` (doctor, admin). A case is a patient record;
every query is scoped by `case_id`, and a member/relationship/variant id from another case is a 404. Every mutation is
audit-logged with the acting user.

  GET    /api/v1/pedigree/{case}                              pedigree, derived relations, generations, validation
  POST   /api/v1/pedigree/{case}/members                      add member (optionally linked to an existing member)
  PATCH  /api/v1/pedigree/{case}/members/{id}                 edit member (validated; refuses new structural errors)
  DELETE /api/v1/pedigree/{case}/members/{id}                 delete (cascades its edges/genotypes; proband protected)
  POST   /api/v1/pedigree/{case}/members/{id}/proband         designate the proband
  PUT    /api/v1/pedigree/{case}/members/{id}/phenotypes      HPO ids (validated against the knowledge graph)
  POST   /api/v1/pedigree/{case}/relationships                connect members (parent | child | partner)
  DELETE /api/v1/pedigree/{case}/relationships/{rel_id}
  POST   /api/v1/pedigree/{case}/members/{id}/genotypes       assign genotype (analysis variant or manual variant)
  POST   /api/v1/pedigree/{case}/members/{id}/genotypes/import import genotypes from a VCF sample column
  DELETE /api/v1/pedigree/{case}/members/{id}/genotypes/{variant_key}
  GET    /api/v1/pedigree/{case}/analysis?variant_key=        inheritance, segregation, de novo, phase, PP1
  GET    /api/v1/pedigree/{case}/overview                     per-variant inheritance summary
  GET    /api/v1/pedigree/{case}/prioritization               base score + transparent family adjustments
  GET    /api/v1/pedigree/{case}/reproductive-context         recurrence risk via the existing reproductive engine
  POST   /api/v1/pedigree/{case}/demo-family                  synthetic/test trio from the verified demo VCF
  GET    /api/v1/pedigree/hpo-search?q=                       HPO term lookup (existing knowledge graph)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.security import require
from backend.app.services import registry
from ml_services.pedigree.service import PedigreeError, PedigreeNotFound

router = APIRouter(prefix="/api/v1/pedigree", tags=["pedigree"])


class RelationIn(BaseModel):
    to: str
    type: str = Field(description="parent | child | partner — what the NEW member is to `to`")


class MemberIn(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    sex: str = "U"
    age_years: Optional[int] = Field(default=None, ge=0, le=120)
    deceased: bool = False
    affected: str = "unknown"
    is_proband: bool = False
    vcf_sample: Optional[str] = None
    hpo_ids: List[str] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, max_length=500)
    relation: Optional[RelationIn] = None


class MemberPatch(BaseModel):
    label: Optional[str] = Field(default=None, max_length=60)
    sex: Optional[str] = None
    age_years: Optional[int] = Field(default=None, ge=0, le=120)
    deceased: Optional[bool] = None
    affected: Optional[str] = None
    is_proband: Optional[bool] = None
    vcf_sample: Optional[str] = None
    hpo_ids: Optional[List[str]] = None
    notes: Optional[str] = Field(default=None, max_length=500)
    layout_x: Optional[float] = None
    layout_y: Optional[float] = None
    clear_layout: bool = False


class RelationshipIn(BaseModel):
    type: str = Field(description="parent (a is parent of b) | child (a is child of b) | partner")
    member_a: str
    member_b: str


class PhenotypesIn(BaseModel):
    hpo_ids: List[str]


class GenotypeIn(BaseModel):
    genotype: str
    variant_key: Optional[str] = None
    analysis_id: Optional[str] = None
    variant_id: Optional[str] = None
    gene: Optional[str] = None
    hgvs: Optional[str] = None
    classification: Optional[str] = None
    inheritance: Optional[str] = None


class ImportIn(BaseModel):
    analysis_id: str
    sample: str


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except PedigreeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PedigreeError as exc:
        raise HTTPException(status_code=exc.status, detail={"message": str(exc), "issues": exc.issues}) from exc


@router.get("/hpo-search")
def hpo_search(q: str = Query(min_length=2), user: dict = Depends(require("pedigree:read"))):
    return registry.pedigree.search_hpo(q)


@router.get("/{case_id}")
def get_pedigree(case_id: str, user: dict = Depends(require("pedigree:read"))):
    return _run(registry.pedigree.get, case_id)


@router.post("/{case_id}/members")
def add_member(case_id: str, payload: MemberIn, user: dict = Depends(require("pedigree:write"))):
    data = payload.model_dump()
    data["relation"] = payload.relation.model_dump() if payload.relation else None
    return _run(registry.pedigree.add_member, case_id, data, user["username"])


@router.patch("/{case_id}/members/{member_id}")
def patch_member(case_id: str, member_id: str, payload: MemberPatch, user: dict = Depends(require("pedigree:write"))):
    data = payload.model_dump(exclude_unset=True)
    if data.pop("clear_layout", False):
        data["layout_x"], data["layout_y"] = None, None
    return _run(registry.pedigree.update_member, case_id, member_id, data, user["username"])


@router.delete("/{case_id}/members/{member_id}")
def delete_member(case_id: str, member_id: str, user: dict = Depends(require("pedigree:write"))):
    return _run(registry.pedigree.delete_member, case_id, member_id, user["username"])


@router.post("/{case_id}/members/{member_id}/proband")
def set_proband(case_id: str, member_id: str, user: dict = Depends(require("pedigree:write"))):
    return _run(registry.pedigree.set_proband, case_id, member_id, user["username"])


@router.put("/{case_id}/members/{member_id}/phenotypes")
def set_phenotypes(case_id: str, member_id: str, payload: PhenotypesIn, user: dict = Depends(require("pedigree:write"))):
    return _run(registry.pedigree.set_phenotypes, case_id, member_id, payload.hpo_ids, user["username"])


@router.post("/{case_id}/relationships")
def add_relationship(case_id: str, payload: RelationshipIn, user: dict = Depends(require("pedigree:write"))):
    return _run(registry.pedigree.add_relationship, case_id, payload.type, payload.member_a, payload.member_b, user["username"])


@router.delete("/{case_id}/relationships/{rel_id}")
def delete_relationship(case_id: str, rel_id: str, user: dict = Depends(require("pedigree:write"))):
    _run(registry.pedigree.delete_relationship, case_id, rel_id, user["username"])
    return {"status": "deleted", "rel_id": rel_id}


@router.post("/{case_id}/members/{member_id}/genotypes")
def set_genotype(case_id: str, member_id: str, payload: GenotypeIn, user: dict = Depends(require("pedigree:write"))):
    return _run(registry.pedigree.set_genotype, case_id, member_id, payload.model_dump(), user["username"])


@router.post("/{case_id}/members/{member_id}/genotypes/import")
def import_genotypes(case_id: str, member_id: str, payload: ImportIn, user: dict = Depends(require("pedigree:write"))):
    return _run(registry.pedigree.import_vcf_genotypes, case_id, member_id, payload.analysis_id, payload.sample, user["username"])


@router.delete("/{case_id}/members/{member_id}/genotypes/{variant_key:path}")
def delete_genotype(case_id: str, member_id: str, variant_key: str, user: dict = Depends(require("pedigree:write"))):
    _run(registry.pedigree.delete_genotype, case_id, member_id, variant_key, user["username"])
    return {"status": "deleted"}


@router.get("/{case_id}/analysis")
def analysis(case_id: str, variant_key: str = Query(...), user: dict = Depends(require("pedigree:read"))):
    return _run(registry.pedigree.analyse, case_id, variant_key)


@router.get("/{case_id}/overview")
def overview(case_id: str, user: dict = Depends(require("pedigree:read"))):
    return _run(registry.pedigree.overview, case_id)


@router.get("/{case_id}/prioritization")
def prioritization(case_id: str, user: dict = Depends(require("pedigree:read"))):
    return _run(registry.pedigree.prioritisation, case_id)


@router.get("/{case_id}/reproductive-context")
def reproductive_context(case_id: str, partner_a: Optional[str] = None, partner_b: Optional[str] = None,
                         user: dict = Depends(require("pedigree:read"))):
    return _run(registry.pedigree.reproductive_context, case_id, partner_a, partner_b)


@router.post("/{case_id}/demo-family")
def demo_family(case_id: str, user: dict = Depends(require("pedigree:write"))):
    return _run(registry.pedigree.demo_family, case_id, user["username"])
