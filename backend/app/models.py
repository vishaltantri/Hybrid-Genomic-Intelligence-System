"""API request/response schemas (Pydantic v2)."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_in_minutes: int


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=8, max_length=128)
    role: Literal["doctor", "patient", "asha", "admin", "researcher"] = Field(description="doctor | patient | asha | admin | researcher")
    full_name: str = Field(default="", max_length=120)


class UserOut(BaseModel):
    username: str
    role: str
    full_name: str = ""


class PatientCreate(BaseModel):
    patient_id: Optional[str] = None
    age_years: Optional[int] = Field(default=None, ge=0, le=120)
    sex: Optional[str] = Field(default=None, pattern="^[MFUmf]$")
    state: Optional[str] = None
    district: Optional[str] = None
    community: Optional[str] = None
    consanguineous: bool = False
    abha_id: Optional[str] = None
    family_history: Dict[str, str] = Field(default_factory=dict)
    known_carrier: Dict[str, bool] = Field(default_factory=dict)
    known_affected: Dict[str, bool] = Field(default_factory=dict)
    notes: str = ""


class PatientOut(BaseModel):
    patient_id: str
    age_years: Optional[int] = None
    sex: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    community: Optional[str] = None
    consanguineous: bool = False
    created_utc: Optional[str] = None
    demo: bool = False


class ClinicalNoteIn(BaseModel):
    text: str = Field(min_length=3, description="Free-text or ASR transcript, any Indian language/code-mixed")
    patient_id: Optional[str] = None
    language: Optional[str] = None


class HpoProfileOut(BaseModel):
    text: str
    hpo_profile: List[dict]
    hpo_ids: List[str]
    unmapped_symptoms: List[str]
    low_confidence_count: int
    is_code_mixed: bool
    lid_counts: Dict[str, int] = Field(default_factory=dict)


class DiagnosisRequest(BaseModel):
    hpo_ids: Optional[List[str]] = None
    text: Optional[str] = None
    patient_id: Optional[str] = None
    state: Optional[str] = None
    community: Optional[str] = None
    sex: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=20)
    explain: bool = False


class PgxRequest(BaseModel):
    drugs: List[str]
    state: Optional[str] = None
    ethnicity: Optional[str] = None
    sex: Optional[str] = None
    age: Optional[int] = None
    known_genotypes: Dict[str, str] = Field(default_factory=dict)
    lang: str = "hi"


class PartnerIn(BaseModel):
    state: Optional[str] = None
    community: Optional[str] = None
    sex: Optional[str] = None
    age: Optional[int] = None
    relationship: Optional[str] = Field(default=None, description="first_cousins | uncle_niece | ...")
    family_history: Dict[str, str] = Field(default_factory=dict)
    known_carrier: Dict[str, bool] = Field(default_factory=dict)
    known_affected: Dict[str, bool] = Field(default_factory=dict)


class CoupleRequest(BaseModel):
    partner_a: PartnerIn
    partner_b: PartnerIn
    top_n: int = 15
    lang: str = "hi"


class LabReportIn(BaseModel):
    text: str
    patient_id: Optional[str] = None


class TriageAnswersIn(BaseModel):
    answers: Dict[str, str]
    age: Optional[int] = None
    state: Optional[str] = None
    district: Optional[str] = None
    village: Optional[str] = None
    asha_id: Optional[str] = None


class TriageTextIn(BaseModel):
    transcript: str
    age: Optional[int] = None
    state: Optional[str] = None
    district: Optional[str] = None
    village: Optional[str] = None
    asha_id: Optional[str] = None


class FeedbackIn(BaseModel):
    queue_index: int = Field(ge=0)
    decision: str = Field(pattern="^(confirmed|corrected|rejected)$")
    corrected_hpo: Dict[str, str] = Field(default_factory=dict)
    corrected_diagnosis: Optional[str] = None
    comment: str = ""


class KgProposalReviewIn(BaseModel):
    query: Optional[str] = None
    offline: bool = True
    auto_accept_priority: float = Field(default=0.85, ge=0.0, le=1.0)


class HealthOut(BaseModel):
    status: str
    graph_nodes: int
    graph_edges: int
    modules: List[str]
