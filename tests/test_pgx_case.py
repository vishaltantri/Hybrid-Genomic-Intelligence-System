"""Phase 9: case-level pharmacogenomics (genotype -> diplotype -> phenotype -> drug rule -> evidence)."""
import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import create_access_token
from backend.app.services import registry
from ml_services.config import SEEDS_DIR
from ml_services.pharmacogenomics.case_pgx import SAFETY


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "pgx_case.sqlite3")
    store.init_db()


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


def make_case(client, vcf=True):
    pid = client.post("/api/v1/patients", json={"age_years": 9, "sex": "M", "state": "Andhra Pradesh", "community": "Reddy"},
                      headers=hdr()).json()["patient_id"]
    if vcf:
        content = (SEEDS_DIR / "clinical_sample_trio.vcf").read_text(encoding="utf-8")
        r = client.post("/api/v1/variants/upload", files={"file": ("t.vcf", content)}, data={"patient_id": pid, "hpo_ids_json": json.dumps([])}, headers=hdr())
        assert r.status_code == 200
    return pid


def test_genotype_is_derived_from_case_variants(client):
    pid = make_case(client)
    ws = client.get(f"/api/v1/pgx/case/{pid}", headers=hdr()).json()
    assert ws["available"] and ws["safety"] == SAFETY
    core = registry.twin.load_core(pid)
    called = {v["gene_symbol"] for v in core["variants"] if v.get("pgx_star_allele")}
    assert {g["gene"] for g in ws["genes"]} == called                       # nothing invented, nothing dropped
    for g in ws["genes"]:
        assert all(a["variant_id"] in {v["variant_id"] for v in core["variants"]} for a in g["alleles"])


def test_phenotype_follows_allele_function_and_zygosity(client):
    pid = make_case(client)
    ws = client.get(f"/api/v1/pgx/case/{pid}", headers=hdr()).json()
    from ml_services.twin.twin_state import metabolizer_status
    for g in ws["genes"]:
        if len(g["alleles"]) == 1:
            a = g["alleles"][0]
            exp = metabolizer_status(g["gene"], a["function"], a["zygosity"])
            if exp:
                assert g["status"] == exp
            else:
                assert g["phenotype"] is None or g["gene"] == "CYP2C19"
        else:
            assert g["diplotype"] is None and "phase" in (g["diplotype_note"] or "").lower()


def test_matrix_rows_come_from_configured_rules_with_sources(client):
    pid = make_case(client)
    ws = client.get(f"/api/v1/pgx/case/{pid}", headers=hdr()).json()
    rules = registry.pgx.guidelines
    for r in ws["matrix"]:
        assert r["sources"]
        if r["status"] == "Recommendation configured":
            code = {"Poor metabolizer": "PM", "Intermediate metabolizer": "IM", "Ultrarapid metabolizer": "UM"}.get(r["phenotype"], r["phenotype"])
            assert any(x["drug"] == r["drug"] and r["gene"] in x["gene"] and x["recommendation"] == r["recommendation"] and x["metabolizer_status"] == code for x in rules)
        else:
            assert r["recommendation"] is None                                 # no rule -> no recommendation


def test_hwe_population_context_is_labelled_not_individual(client):
    pid = make_case(client)
    ws = client.get(f"/api/v1/pgx/case/{pid}", headers=hdr()).json()
    pops = [g["population"] for g in ws["genes"] if g["population"]]
    assert pops
    for p in pops:
        assert abs(sum(p["hwe_expected"].values()) - 1) < 1e-3
        assert "not this patient's genotype" in p["note"]


def test_missing_genotype_states(client):
    empty = make_case(client, vcf=False)
    ws = client.get(f"/api/v1/pgx/case/{empty}", headers=hdr()).json()
    assert ws["available"] is False and "unavailable" in ws["note"] and "Not analyzed" in ws["note"]
    assert client.get("/api/v1/pgx/case/PT-NOPE", headers=hdr()).status_code == 404


def test_drug_lookup_supported_and_unsupported(client):
    pid = make_case(client)
    ok = client.get(f"/api/v1/pgx/case/{pid}/drug", params={"name": "clopidogrel"}, headers=hdr()).json()
    assert ok["supported"] is True
    assert ok["rows"] or ok["genes_without_genotype"]
    bad = client.get(f"/api/v1/pgx/case/{pid}/drug", params={"name": "notadrugxyz"}, headers=hdr()).json()
    assert bad["supported"] is False and bad["rows"] == [] and "unsupported" in bad["note"]


def test_saved_evidence_attaches_to_matching_gene(client):
    pid = make_case(client)
    ws = client.get(f"/api/v1/pgx/case/{pid}", headers=hdr()).json()
    gene = ws["genes"][0]["gene"]
    store.evidence_save(pid, {"source": "pubmed", "source_id": "123", "pmid": "123", "title": f"{gene} guideline paper"}, "clinician")
    ws = client.get(f"/api/v1/pgx/case/{pid}", headers=hdr()).json()
    assert any(r["saved_evidence"] for r in ws["matrix"] if r["gene"] == gene)


def test_authorization_and_report_section(client):
    pid = make_case(client)
    assert client.get(f"/api/v1/pgx/case/{pid}").status_code == 401
    assert client.get(f"/api/v1/pgx/case/{pid}", headers=hdr("p", "patient")).status_code == 403
    sec = client.get(f"/api/v1/pgx/case/{pid}/report-section", headers=hdr()).json()
    assert sec["available"] and sec["findings"] and SAFETY in sec["limitations"]


def test_existing_population_engine_unchanged(client):
    r = client.post("/api/v1/pgx/check", json={"drugs": ["clopidogrel"], "state": "Gujarat", "known_genotypes": {"CYP2C19": "poor_metabolizer"}}, headers=hdr())
    assert r.status_code == 200 and r.json()["alerts"][0]["severity"] == "critical"


def test_assistant_grounds_on_pgx_and_twin_agrees(client):
    pid = make_case(client)
    ws = client.get(f"/api/v1/pgx/case/{pid}", headers=hdr()).json()
    twin = client.get(f"/api/v1/digital-twin/{pid}", headers=hdr()).json()["pgx"]
    assert {g["gene"] for g in ws["genes"]} == {o["gene"] for o in twin["observations"]}
    r = client.post("/api/v1/assistant/chat", json={"message": "What does this patient's PGx result mean?", "patient_id": pid, "include_pgx": True}, headers=hdr())
    assert r.status_code == 200
    assert any(c["source_type"] == "pgx" for c in r.json().get("citations", []))
    assert client.post("/api/v1/assistant/chat", json={"message": "x", "patient_id": pid, "include_pgx": True}, headers=hdr("r", "researcher")).status_code == 403
