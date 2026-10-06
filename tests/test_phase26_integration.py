"""Phase 26: one platform, not isolated pages. Two patients run through every module over real HTTP; context, identifiers and
authorization must stay correct at each hand-off. Patient A has a Wilson-disease story, patient B a PAH story."""
import json
import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import hash_password
from backend.app.services import registry
from ml_services.config import SEEDS_DIR

API = "/api/v1"


def _vcf_for(*genes):
    lines = (SEEDS_DIR / "clinical_sample_trio.vcf").read_text(encoding="utf-8").split("\n")
    keep = [l for l in lines if l.startswith("#") or any(f"GENE={g};" in l for g in genes)]
    return "\n".join(keep) + "\n"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "p26.sqlite3")
    store.init_db()
    registry.variants._analyses.clear()
    for u, role in (("doc", "doctor"), ("doc2", "doctor"), ("pat", "patient"), ("asha1", "asha"), ("adm", "admin")):
        store.create_user(u, role, hash_password("changeme"))
    c = TestClient(app)

    def hdr(u):
        t = c.post(f"{API}/auth/token", data={"username": u, "password": "changeme"}).json()["access_token"]
        return {"Authorization": f"Bearer {t}"}
    return c, hdr


def _build_case(c, H, state, hpos, genes):
    pid = c.post(f"{API}/patients", json={"age_years": 9, "sex": "F", "state": state, "community": "Reddy", "consanguineous": True}, headers=H).json()["patient_id"]
    assert c.post(f"{API}/phenotype/case/{pid}/import", json={"items": [{"hpo_id": h, "assertion": "present"} for h in hpos]}, headers=H).status_code == 200
    up = c.post(f"{API}/variants/upload", files={"file": ("t.vcf", _vcf_for(*genes))}, data={"patient_id": pid}, headers=H)
    assert up.status_code == 200, up.text
    assert c.post(f"{API}/pedigree/{pid}/demo-family", headers=H).status_code == 200
    return pid, up.json()


def test_patient_to_case_to_modules_keep_the_right_identity(env):
    c, hdr = env
    H = hdr("doc")
    a, up_a = _build_case(c, H, "Andhra Pradesh", ("HP:0001337", "HP:0000952", "HP:0002240"), ("ATP7B", "HBB", "CYP2C19"))
    b, up_b = _build_case(c, H, "Tamil Nadu", ("HP:0001250", "HP:0001263"), ("PAH",))
    assert a != b
    ids_a = [v["variant_id"] for v in up_a["variants"]]          # the patient's own variants (gene names also appear as disease candidates)
    ids_b = [v["variant_id"] for v in up_b["variants"]]
    assert ids_a and ids_b and not set(ids_a) & set(ids_b)
    leaks = lambda text, ids: [i for i in ids if i in text]

    # analyses stay attached to their own patient
    listing = {x["analysis_id"]: x["patient_id"] for x in c.get(f"{API}/variants/analyses", headers=H).json()}
    assert listing[up_a["analysis_id"]] == a and listing[up_b["analysis_id"]] == b

    # phenotypes: stored once per case, normalised HPO ids, not shared
    ph_a = {o["hpo_id"] for o in c.get(f"{API}/phenotype/case/{a}", headers=H).json()["observed"]}
    ph_b = {o["hpo_id"] for o in c.get(f"{API}/phenotype/case/{b}", headers=H).json()["observed"]}
    assert ph_a == {"HP:0001337", "HP:0000952", "HP:0002240"} and ph_b == {"HP:0001250", "HP:0001263"}

    # diagnosis is driven by that patient's phenotypes
    dx_a = c.get(f"{API}/dx/case/{a}", headers=H).json()
    assert dx_a["available"] and dx_a["case_id"] == a if "case_id" in dx_a else dx_a["available"]
    assert any("Wilson" in d["disease_name"] for d in dx_a["differential"][:3])
    dx_b = c.get(f"{API}/dx/case/{b}", headers=H).json()
    # B's differential comes from B's two phenotypes, not A's: different scores (the engine is a ranking, not a diagnosis)
    assert [d["probability"] for d in dx_a["differential"]] != [d["probability"] for d in dx_b["differential"]]

    # digital twin carries only this case's genes and phenotypes
    twin_a = json.dumps(c.get(f"{API}/digital-twin/{a}", headers=H).json())
    assert "ATP7B" in twin_a and not leaks(twin_a, ids_b)
    twin_b = json.dumps(c.get(f"{API}/digital-twin/{b}", headers=H).json())
    assert "PAH" in twin_b and not leaks(twin_b, ids_a)

    # pedigree genotypes come from this case's analysis only
    ped_a = json.dumps(c.get(f"{API}/pedigree/{a}/overview", headers=H).json())
    assert "ATP7B" in ped_a and not leaks(ped_a, ids_b)

    # pgx and reproductive answer for the same case
    assert c.get(f"{API}/pgx/case/{a}", headers=H).status_code == 200
    pgx_a = json.dumps(c.get(f"{API}/pgx/case/{a}", headers=H).json())
    assert "CYP2C19" in pgx_a
    repro = c.get(f"{API}/repro/case/{a}", headers=H)
    assert repro.status_code == 200 and json.dumps(repro.json()).count(b) == 0

    # reports: correct case, no leakage of the other patient
    ra = c.post(f"{API}/reports/case/{a}", json={}, headers=H).json()
    rb = c.post(f"{API}/reports/case/{b}", json={}, headers=H).json()
    ja = json.dumps(c.get(f"{API}/reports/{ra['report_id']}/json", headers=H).json())
    jb = json.dumps(c.get(f"{API}/reports/{rb['report_id']}/json", headers=H).json())
    assert a in ja and b not in ja and not leaks(ja, ids_b) and "ATP7B" in ja
    assert b in jb and a not in jb and not leaks(jb, ids_a) and "PAH" in jb

    # FHIR export references only this patient
    bundle = c.get(f"{API}/emr/fhir/case/{a}", headers=H).json()
    text = json.dumps(bundle)
    assert a in text and b not in text
    assert bundle["validation"]["valid"] is True


def test_workflow_and_notifications_match_real_events(env):
    c, hdr = env
    H, H2 = hdr("doc"), hdr("doc2")
    pid, _ = _build_case(c, H, "Andhra Pradesh", ("HP:0001337", "HP:0000952"), ("ATP7B",))
    assert c.post(f"{API}/workflow/case/{pid}/assign", json={"assignee": "doc2"}, headers=H).status_code == 200
    assert c.post(f"{API}/workflow/case/{pid}/status", json={"status": "in_review"}, headers=H).status_code == 200
    rid = c.post(f"{API}/reports/case/{pid}", json={}, headers=H).json()["report_id"]
    assert c.post(f"{API}/reports/{rid}/finalize", headers=H).status_code == 200
    notes = c.get(f"{API}/workflow/notifications", headers=H2).json()
    assert {"assignment", "report_final"} <= {n["kind"] for n in notes}
    assert all(n.get("case_id") in (pid, None) for n in notes)
    # the other doctor's inbox has nothing about events on cases that were not assigned to them
    other = c.post(f"{API}/patients", json={"age_years": 3, "sex": "M", "state": "Kerala"}, headers=H).json()["patient_id"]
    c.post(f"{API}/workflow/case/{other}/status", json={"status": "in_review"}, headers=H)
    assert all(n.get("case_id") != other for n in c.get(f"{API}/workflow/notifications", headers=H2).json())


def test_search_results_open_real_entities(env):
    c, hdr = env
    H = hdr("doc")
    pid, up = _build_case(c, H, "Andhra Pradesh", ("HP:0001337",), ("ATP7B",))
    rid = c.post(f"{API}/reports/case/{pid}", json={}, headers=H).json()["report_id"]
    for q, kind in ((pid, "cases"), (rid, "reports"), ("ATP7B", "variants"), ("wilson", "diseases")):
        hits = c.get(f"{API}/search", params={"q": q}, headers=H).json()["results"][kind]
        assert hits, (q, kind)
        h = hits[0]
        assert h["route"] and h["id"]
        ctx = h["context"]
        if kind == "cases":
            assert c.get(f"{API}/patients/{h['id']}", headers=H).status_code == 200
        elif kind == "reports":
            assert c.get(f"{API}/reports/{h['id']}", headers=H).status_code == 200 and ctx["patient_id"] == pid
        elif kind == "variants":
            assert c.get(f"{API}/variants/analyses/{ctx['analysis_id']}", headers=H).status_code == 200
        else:
            assert c.get(f"{API}/diseases/{h['id']}", headers=H).status_code == 200


def test_authorization_across_modules(env):
    c, hdr = env
    H = hdr("doc")
    pid, up = _build_case(c, H, "Andhra Pradesh", ("HP:0001337",), ("ATP7B",))
    # a patient-role user cannot read someone else's case through the clinical modules or the assistant
    P = hdr("pat")
    assert c.get(f"{API}/patients/{pid}", headers=P).status_code == 403
    assert c.post(f"{API}/assistant/chat", json={"message": "Summarise this case", "patient_id": pid}, headers=P).status_code == 403
    # an analysis owned by another user is not usable as assistant context (same 404 as a missing id)
    # (analyses attached to a case are clinician-wide by design; an unattached upload is private to its uploader)
    H2 = hdr("doc2")
    private = c.post(f"{API}/variants/upload", files={"file": ("t.vcf", _vcf_for("ATP7B"))}, headers=H).json()["analysis_id"]
    r = c.post(f"{API}/assistant/chat", json={"message": "Summarise", "analysis_id": private}, headers=H2)
    assert r.status_code == 404
    assert c.get(f"{API}/variants/analyses/{private}", headers=H2).status_code == 404
    # asha workers have no access to variant or report data
    A = hdr("asha1")
    assert c.get(f"{API}/variants/analyses", headers=A).status_code == 403
    assert c.post(f"{API}/reports/case/{pid}", json={}, headers=A).status_code == 403
    # unauthenticated is rejected everywhere
    for path in (f"/emr/fhir/case/{pid}", f"/reports/case/{pid}", f"/digital-twin/{pid}", f"/pgx/case/{pid}", f"/repro/case/{pid}", f"/dx/case/{pid}"):
        assert c.get(API + path).status_code == 401, path


def test_assistant_uses_the_selected_case_context(env):
    c, hdr = env
    H = hdr("doc")
    a, up_a = _build_case(c, H, "Andhra Pradesh", ("HP:0001337", "HP:0000952"), ("ATP7B",))
    b, up_b = _build_case(c, H, "Tamil Nadu", ("HP:0001250",), ("PAH",))
    ctx_a = c.get(f"{API}/assistant/context", params={"patient_id": a}, headers=H).json()
    ctx_b = c.get(f"{API}/assistant/context", params={"patient_id": b}, headers=H).json()
    assert ctx_a["has_sufficient_context"] and ctx_b["has_sufficient_context"]
    ra = registry.assistant.retriever.retrieve(query="Which gene is involved?", patient_id=a, analysis_id=up_a["analysis_id"])
    rb = registry.assistant.retriever.retrieve(query="Which gene is involved?", patient_id=b, analysis_id=up_b["analysis_id"])
    assert "ATP7B" in str(ra.__dict__) and "PAH" not in str(ra.__dict__)
    assert "PAH" in str(rb.__dict__) and "ATP7B" not in str(rb.__dict__)
