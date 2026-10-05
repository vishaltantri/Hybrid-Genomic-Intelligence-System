"""Digital Twin (Phase 3D): construction, isolation, scenarios, persistence, integrations.

Runs against a throw-away SQLite file so no patient rows leak into the dev database.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import create_access_token
from backend.app.services import registry
from ml_services.config import SEEDS_DIR
from ml_services.variants.prioritizer import ACMG_POINTS, composite_score

WILSON_TEXT = "jaundice with hepatomegaly, tremor and difficulty walking"
ATP7B_VID = "chr13:51943246:C>G"
CTX = {"state": "Andhra Pradesh", "community": "Reddy", "sex": "M"}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "twin_test.sqlite3")
    store.init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


def make_patient(client, **extra):
    body = {"age_years": 9, "sex": "M", "state": "Andhra Pradesh", "community": "Reddy",
            "consanguineous": True, "family_history": {"sibling": "liver disease"}}
    body.update(extra)
    r = client.post("/api/v1/patients", json=body, headers=hdr())
    assert r.status_code == 200
    return r.json()["patient_id"]


def add_phenotypes(client, pid, text=WILSON_TEXT):
    r = client.post("/api/v1/clinical/hpo-map", json={"text": text, "patient_id": pid}, headers=hdr())
    assert r.status_code == 200 and r.json()["hpo_ids"]
    return r.json()["hpo_ids"]


def upload_vcf(client, pid, hpos):
    content = (SEEDS_DIR / "clinical_sample_trio.vcf").read_text(encoding="utf-8")
    r = client.post("/api/v1/variants/upload", files={"file": ("trio.vcf", content)},
                    data={"patient_id": pid, "hpo_ids_json": json.dumps(hpos)}, headers=hdr())
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def full_case(client):
    pid = make_patient(client)
    hpos = add_phenotypes(client, pid)
    analysis = upload_vcf(client, pid, hpos)
    return pid, hpos, analysis


def twin(client, pid, headers=None, **params):
    r = client.get(f"/api/v1/digital-twin/{pid}", params=params, headers=headers or hdr())
    assert r.status_code == 200, r.text
    return r.json()


def scenario(client, pid, stype, params, headers=None, expect=200, name=None):
    r = client.post(f"/api/v1/digital-twin/{pid}/scenarios", headers=headers or hdr(),
                    json={"type": stype, "params": params, "name": name})
    assert r.status_code == expect, r.text
    return r.json()


# ------------------------------- auth / RBAC -------------------------------

def test_requires_authentication(client):
    assert client.get("/api/v1/digital-twin/ANY").status_code == 401


@pytest.mark.parametrize("role", ["patient", "asha", "researcher"])
def test_roles_without_twin_permission_are_forbidden(client, role):
    pid = make_patient(client)
    assert client.get(f"/api/v1/digital-twin/{pid}", headers=hdr("someone", role)).status_code == 403


def test_unknown_patient_is_404(client):
    assert client.get("/api/v1/digital-twin/NOPE", headers=hdr()).status_code == 404


# ------------------------------- construction -------------------------------

def test_twin_state_is_derived_from_case_data(client, full_case):
    pid, hpos, analysis = full_case
    t = twin(client, pid)
    # phenotype state == the HPO ids stored for the patient, with provenance and no invented onset/severity
    assert sorted(o["hpo_id"] for o in t["phenotype"]["observed"]) == sorted(hpos)
    for o in t["phenotype"]["observed"]:
        assert o["onset"] is None and o["severity"] is None
        assert o["sources"] and o["sources"][0]["ref"].startswith("EV-")
    # genomic state == the Variant Intelligence QC for this patient's analysis
    qc = analysis["qc_metrics"]
    g = t["genomic"]
    assert g["analysis_id"] == analysis["analysis_id"]
    assert g["counts"]["total"] == qc["total_variants"]
    assert g["counts"]["pathogenic"] == qc["pathogenic_count"]
    assert g["counts"]["likely_pathogenic"] == qc["likely_pathogenic_count"]
    assert g["counts"]["vus"] == qc["vus_count"]
    # diagnosis state == a direct call to the existing engine
    direct = registry.diagnosis.diagnose(sorted(hpos), CTX, top_k=10, explain=True)["results"]
    assert [d["disease_id"] for d in t["diagnosis"]["differential"]] == [d["disease_id"] for d in direct]
    assert t["diagnosis"]["top_diagnosis"]["probability"] == direct[0]["probability"]
    # genomic support is computed from KG gene links, not hardcoded
    wilson = next(c for c in t["diagnosis"]["genomic_candidates"] if c["disease_name"] == "Wilson disease")
    assert ATP7B_VID in wilson["genomic_support"]["variant_ids"]
    # pgx state comes from star alleles in the analysis
    assert t["pgx"]["available"] and {o["gene"] for o in t["pgx"]["observations"]} >= {"CYP2C19"}
    assert t["family"]["family_history"] == {"sibling": "liver disease"}
    assert "Computational decision-support simulation" in t["disclaimer"]
    assert {p["section"] for p in t["provenance"]} >= {"identity", "phenotype", "genomic", "diagnosis", "timeline"}


def test_organ_systems_come_from_the_hpo_hierarchy(client, full_case):
    pid, _, _ = full_case
    systems = {s["system"] for s in twin(client, pid)["phenotype"]["organ_systems"]}
    assert "Abnormality of the nervous system" in systems  # tremor


def test_insufficient_data_is_explicit_not_fabricated(client):
    pid = make_patient(client, family_history={}, consanguineous=False)
    t = twin(client, pid)
    assert not t["phenotype"]["available"] and "Insufficient data" in t["phenotype"]["note"]
    assert not t["genomic"]["available"] and "Insufficient data" in t["genomic"]["note"]
    assert not t["diagnosis"]["available"] and t["diagnosis"]["differential"] == []
    assert t["pgx"]["note"] == "No PGx findings available for this case."
    assert t["family"]["note"] == "Family/inheritance information unavailable."
    assert "Longitudinal history is limited" in t["timeline"]["note"]
    assert t["snapshot"]["top_diagnosis"] is None and t["snapshot"]["variants"] == 0


def test_timeline_events_exist_in_storage(client, full_case):
    pid, _, analysis = full_case
    tl = client.get(f"/api/v1/digital-twin/{pid}/timeline", headers=hdr()).json()
    stored = {e["event_id"] for e in store.list_events(pid)} | {pid, analysis["analysis_id"]}
    assert tl["events"] and all(e["source"]["ref"] in stored for e in tl["events"])


# ------------------------------- isolation -------------------------------

def test_no_cross_patient_leakage(client, full_case):
    pid_a, _, analysis = full_case
    pid_b = make_patient(client, state="Kerala")
    add_phenotypes(client, pid_b, "seizures and anemia")
    tb = twin(client, pid_b)
    assert not tb["genomic"]["available"]
    assert tb["snapshot"]["analysis_id"] is None
    assert tb["identity"]["patient_id"] == pid_b
    # asking for A's analysis through B is refused
    r = client.get(f"/api/v1/digital-twin/{pid_b}", params={"analysis_id": analysis["analysis_id"]}, headers=hdr())
    assert r.status_code == 404
    # B's scenarios cannot use A's variants
    scenario(client, pid_b, "variant_exclusion", {"variant_ids": [ATP7B_VID]}, expect=422)


def test_snapshot_is_versioned_by_content(client, full_case):
    pid, _, _ = full_case
    v1 = client.get(f"/api/v1/digital-twin/{pid}/snapshot", headers=hdr()).json()
    v1b = client.get(f"/api/v1/digital-twin/{pid}/snapshot", headers=hdr()).json()
    assert v1["snapshot_version"] == v1b["snapshot_version"]
    assert v1["phenotypes"] == len(v1["hpo_ids"]) and v1["variants"] == 8
    add_phenotypes(client, pid, "seizures")
    v2 = client.get(f"/api/v1/digital-twin/{pid}/snapshot", headers=hdr()).json()
    assert v2["snapshot_version"] != v1["snapshot_version"] and v2["phenotypes"] > v1["phenotypes"]


def test_saved_snapshots_are_per_user(client, full_case):
    pid, _, _ = full_case
    s1 = client.post(f"/api/v1/digital-twin/{pid}/snapshot", headers=hdr()).json()
    s2 = client.post(f"/api/v1/digital-twin/{pid}/snapshot", headers=hdr()).json()
    assert (s1["sequence"], s2["sequence"]) == (1, 2) and s2["changed_since_previous"] is False
    mine = client.get(f"/api/v1/digital-twin/{pid}/snapshots", headers=hdr()).json()
    other = client.get(f"/api/v1/digital-twin/{pid}/snapshots", headers=hdr("dr_other")).json()
    assert len(mine) == 2 and other == []


# ------------------------------- scoring parity -------------------------------

def test_rescoring_helpers_reproduce_stored_priority(full_case):
    _, hpos, analysis = full_case
    for v in analysis["variants"]:
        assert composite_score(registry.graph, v, hpos) == v["priority_score"], v["variant_id"]


# ------------------------------- scenarios -------------------------------

def test_variant_exclusion_recomputes_genomic_state(client, full_case):
    pid, _, _ = full_case
    base = twin(client, pid)
    r = scenario(client, pid, "variant_exclusion", {"variant_ids": [ATP7B_VID]}, name="Exclude ATP7B")
    assert r["name"] == "Exclude ATP7B"
    b, s = r["baseline"], r["scenario"]
    assert s["variant_counts"]["total"] == b["variant_counts"]["total"] - 1
    assert b["variant_counts"]["total"] == base["genomic"]["counts"]["total"]
    assert all(v["variant_id"] != ATP7B_VID for v in s["variant_ranking"])
    wilson_b = next(c for c in b["genomic_candidates"] if c["disease_name"] == "Wilson disease")
    assert wilson_b["pathogenic_or_likely_variants"] >= 1
    assert not any(c["disease_name"] == "Wilson disease" for c in s["genomic_candidates"])
    assert r["diff"]["differential_order_changed"] is False          # phenotype ranking is variant-independent
    assert any("ATP7B" in line for line in r["explanation"])
    assert any("does not move it" in line for line in r["explanation"])
    rows = {row["label"]: row for row in r["comparison"]}
    assert rows["Relevant variants (top diagnosis)"]["baseline"] > rows["Relevant variants (top diagnosis)"]["scenario"]


def test_variant_reclassification_uses_acmg_points(client, full_case):
    pid, _, analysis = full_case
    before = next(v for v in analysis["variants"] if v["variant_id"] == ATP7B_VID)
    r = scenario(client, pid, "variant_reclassification",
                 {"variant_id": ATP7B_VID, "new_classification": "Uncertain significance"})
    new = next(v for v in r["scenario"]["variant_ranking"] if v["variant_id"] == ATP7B_VID)
    delta = ACMG_POINTS[before["acmg_classification"]] - ACMG_POINTS["Uncertain significance"]
    assert round(before["priority_score"] - new["priority_score"], 1) == delta
    assert new["classification"] == "Uncertain significance"
    wilson = next(c for c in r["scenario"]["genomic_candidates"] if c["disease_name"] == "Wilson disease")
    assert wilson["pathogenic_or_likely_variants"] == 0 and wilson["vus_variants"] >= 1
    assert any("does NOT re-run the ACMG" in x for x in r["limitations"])


def test_phenotype_removal_matches_direct_engine_run(client, full_case):
    pid, hpos, _ = full_case
    removed = hpos[0]
    r = scenario(client, pid, "phenotype_remove", {"hpo_ids": [removed]})
    direct = registry.diagnosis.diagnose(sorted(set(hpos) - {removed}), CTX, top_k=10)["results"]
    assert r["scenario"]["top_diagnosis"]["disease_id"] == direct[0]["disease_id"]
    assert r["scenario"]["top_diagnosis"]["probability"] == direct[0]["probability"]
    assert r["scenario"]["phenotype_count"] == len(hpos) - 1 == r["baseline"]["phenotype_count"] - 1
    assert removed not in r["scenario"]["hpo_ids"]


def test_phenotype_addition_matches_direct_engine_run(client, full_case):
    pid, hpos, _ = full_case
    r = scenario(client, pid, "phenotype_add", {"hpo_ids": ["HP:0000616"]})   # Kayser-Fleischer ring
    direct = registry.diagnosis.diagnose(sorted(set(hpos) | {"HP:0000616"}), CTX, top_k=10)["results"]
    assert r["scenario"]["top_diagnosis"]["probability"] == direct[0]["probability"]
    assert r["scenario"]["top_diagnosis"]["probability"] > r["baseline"]["top_diagnosis"]["probability"]
    assert (r["scenario"]["top_diagnosis"]["supporting_phenotypes"]
            == r["baseline"]["top_diagnosis"]["supporting_phenotypes"] + 1)
    scenario(client, pid, "phenotype_add", {"hpo_ids": [hpos[0]]}, expect=422)       # already present
    scenario(client, pid, "phenotype_add", {"hpo_ids": ["HP:9999999"]}, expect=422)  # unknown to graph


def test_phenotype_change_rescored_variant_phenotype_component(client, full_case):
    pid, _, _ = full_case
    # Anemia is not a Wilson-disease finding: overlap fraction drops 3/3 -> 3/4, so the ATP7B
    # phenotype component falls from 30 to 25 points.
    r = scenario(client, pid, "phenotype_add", {"hpo_ids": ["HP:0001903"]})
    changed = [c for c in r["diff"]["variant_changes"] if c["gene"] == "ATP7B"]
    assert changed and round(changed[0]["score_before"] - changed[0]["score_after"], 1) == 5.0
    # Adding findings that Wilson disease DOES have leaves the (already capped) component unchanged.
    r2 = scenario(client, pid, "phenotype_add", {"hpo_ids": ["HP:0000616", "HP:0001394"]})
    assert not [c for c in r2["diff"]["variant_changes"] if c["gene"] == "ATP7B"]


def test_diagnosis_focus_compares_against_top(client, full_case):
    pid, hpos, _ = full_case
    r = scenario(client, pid, "diagnosis_focus", {"disease_id": "ORPHA:716"})
    assert r["baseline"]["disease_name"] == "Wilson disease" and r["scenario"]["disease_name"] == "Phenylketonuria"
    assert r["scenario"]["pathogenic_or_likely_variants"] == 1          # PAH variant in the trio
    assert r["baseline"]["probability"] > r["scenario"]["probability"]
    scenario(client, pid, "diagnosis_focus", {"disease_id": r["baseline"]["disease_id"]}, expect=422)


def test_medication_uses_patient_genotype_when_available(client, full_case):
    pid, _, _ = full_case
    r = scenario(client, pid, "medication", {"drugs": ["clopidogrel"]})
    alert = r["scenario"]["findings"][0]
    assert alert["gene"] == "CYP2C19" and alert["inferred_status"] == "poor_metabolizer"
    assert alert["assumption"] == "known_genotype_override"        # CYP2C19*2 homozygous in the VCF
    assert r["baseline"]["alerts"] == 0
    assert any("NOT modelled" in x for x in r["limitations"])


@pytest.mark.parametrize("bad", ["disease_progression", "treatment_response", "survival", "lab_values"])
def test_unmodelled_simulations_are_rejected_with_limitation(client, full_case, bad):
    pid, _, _ = full_case
    r = scenario(client, pid, bad, {}, expect=422)
    assert "not available from the current clinical data/model" in r["detail"]


def test_invalid_scenarios_are_rejected(client, full_case):
    pid, _, _ = full_case
    scenario(client, pid, "variant_exclusion", {"variant_ids": []}, expect=422)
    scenario(client, pid, "variant_exclusion", {"variant_ids": ["chr0:1:A>T"]}, expect=422)
    scenario(client, pid, "variant_reclassification",
             {"variant_id": ATP7B_VID, "new_classification": "Maybe"}, expect=422)
    scenario(client, pid, "phenotype_remove", {"hpo_ids": ["HP:0000616"]}, expect=422)   # not in this twin
    scenario(client, pid, "medication", {"drugs": []}, expect=422)
    scenario(client, pid, "nonsense", {}, expect=422)


def test_scenarios_requiring_data_say_insufficient(client):
    pid = make_patient(client)
    r = scenario(client, pid, "phenotype_remove", {"hpo_ids": ["HP:0001250"]}, expect=422)
    assert "Insufficient data" in r["detail"]


# ------------------------------- persistence / isolation -------------------------------

def test_scenario_history_persists_and_is_private(client, full_case):
    pid, _, _ = full_case
    sc = scenario(client, pid, "variant_exclusion", {"variant_ids": [ATP7B_VID]}, name="Exclude ATP7B")
    mine = client.get(f"/api/v1/digital-twin/{pid}/scenarios", headers=hdr()).json()
    assert [m["scenario_id"] for m in mine] == [sc["scenario_id"]] and mine[0]["name"] == "Exclude ATP7B"
    stored = client.get(f"/api/v1/digital-twin/{pid}/scenarios/{sc['scenario_id']}", headers=hdr()).json()
    assert stored["comparison"] == sc["comparison"] and stored["explanation"] == sc["explanation"]
    other = hdr("dr_other")
    assert client.get(f"/api/v1/digital-twin/{pid}/scenarios", headers=other).json() == []
    assert client.get(f"/api/v1/digital-twin/{pid}/scenarios/{sc['scenario_id']}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/digital-twin/{pid}/scenarios/{sc['scenario_id']}", headers=other).status_code == 404
    pid_b = make_patient(client)
    assert client.get(f"/api/v1/digital-twin/{pid_b}/scenarios/{sc['scenario_id']}", headers=hdr()).status_code == 404
    assert client.delete(f"/api/v1/digital-twin/{pid}/scenarios/{sc['scenario_id']}", headers=hdr()).status_code == 200
    assert client.get(f"/api/v1/digital-twin/{pid}/scenarios", headers=hdr()).json() == []


def test_scenarios_are_not_exposed_through_patient_events(client, full_case):
    pid, _, _ = full_case
    scenario(client, pid, "variant_exclusion", {"variant_ids": [ATP7B_VID]})
    kinds = {e["kind"] for e in client.get(f"/api/v1/patients/{pid}", headers=hdr()).json()["events"]}
    assert not {k for k in kinds if "scenario" in k}


# ------------------------------- integrations -------------------------------

def test_report_handoff_transfers_snapshot_and_scenarios(client, full_case):
    pid, _, _ = full_case
    sc = scenario(client, pid, "variant_exclusion", {"variant_ids": [ATP7B_VID]})
    r = client.post(f"/api/v1/digital-twin/{pid}/report-handoff", headers=hdr(),
                    json={"scenario_ids": [sc["scenario_id"]], "clinical_notes": "for MDT"})
    assert r.status_code == 200
    bundle = r.json()
    events = client.get(f"/api/v1/patients/{pid}", headers=hdr()).json()["events"]
    stored = next(e for e in events if e["kind"] == "twin_report_bundle")
    assert stored["event_id"] == bundle["event_id"]
    assert stored["payload"]["snapshot"]["variants"] == 8
    assert stored["payload"]["scenarios"][0]["scenario_id"] == sc["scenario_id"]
    assert client.post(f"/api/v1/digital-twin/{pid}/report-handoff", headers=hdr(),
                       json={"scenario_ids": ["SCN-MISSING"]}).status_code == 404


class _CapturingLLM:
    is_configured = True

    def __init__(self):
        self.messages = None

    def generate(self, messages, **_):
        self.messages = messages
        return "stub answer"


def test_assistant_receives_twin_and_scenario_context(client, full_case):
    pid, _, _ = full_case
    sc = scenario(client, pid, "variant_exclusion", {"variant_ids": [ATP7B_VID]}, name="Exclude ATP7B")
    stub = _CapturingLLM()
    original = registry.assistant.llm
    registry.assistant.llm = stub
    try:
        r = client.post("/api/v1/assistant/chat", headers=hdr(), json={
            "message": "Why did the scenario change the genomic support?", "patient_id": pid,
            "include_twin": True, "twin_scenario_id": sc["scenario_id"]})
    finally:
        registry.assistant.llm = original
    assert r.status_code == 200, r.text
    body = r.json()
    prompt = json.dumps(stub.messages)
    assert "DIGITAL TWIN" in prompt and "Exclude ATP7B" in prompt and "Wilson disease" in prompt
    assert body["context_summary"]["twin"] is True and body["context_summary"]["twin_scenario"] == sc["scenario_id"]
    assert any(c["source_type"] == "Digital Twin Scenario" for c in body["citations"])


def test_assistant_twin_context_requires_twin_permission(client, full_case):
    pid, _, _ = full_case
    r = client.post("/api/v1/assistant/chat", headers=hdr("pat", "patient"),
                    json={"message": "explain", "patient_id": pid, "include_twin": True})
    assert r.status_code == 403
    r = client.post("/api/v1/assistant/chat", headers=hdr(), json={"message": "explain", "include_twin": True})
    assert r.status_code == 422


# ------------------------------- anatomy / genome layers (visual Twin) -------------------------------

def test_anatomy_systems_are_data_driven(client, full_case):
    pid, hpos, _ = full_case
    a = twin(client, pid)["anatomy"]
    systems = {s["id"]: s for s in a["systems"]}
    # patient phenotypes (tremor, hepatomegaly, jaundice) map to nervous + hepatic
    assert {p["name"] for p in systems["hepatic"]["phenotypes"]} >= {"Hepatomegaly", "Jaundice"}
    assert any(p["name"] == "Tremor" for p in systems["nervous"]["phenotypes"])
    # ATP7B (non-benign) -> Wilson disease (KG) -> documented hepatic manifestations
    assert "ATP7B" in systems["hepatic"]["genes"] and ATP7B_VID in systems["hepatic"]["variant_ids"]
    assert {"disease_id": "ORPHA:915", "name": "Wilson disease"} in systems["hepatic"]["diseases"]
    # nothing documented for these systems => neutral, with the explicit message and no invented findings
    for sid in ("reproductive", "renal", "cardiovascular"):
        assert not systems[sid]["has_case_data"] and not systems[sid]["variant_ids"]
        assert systems[sid]["note"] == "No case-specific genomic or phenotype findings mapped to this system."
    # benign variants never light up a system
    assert not any(v for s in systems.values() for v in s["variant_ids"] if v == "chr1:1234567:A>G")


def test_chromosome_layer_uses_vcf_coordinates_only(client, full_case):
    pid, _, analysis = full_case
    a = twin(client, pid)["anatomy"]
    chrom = {c["chrom"]: c for c in a["chromosomes"]}
    assert len(chrom) == 24 and chrom["chr13"]["length_bp"] == 114364328
    placed = chrom["chr13"]["variants"][0]
    src = next(v for v in analysis["variants"] if v["variant_id"] == ATP7B_VID)
    assert placed["pos"] == src["pos"] and placed["gene"] == "ATP7B"
    assert sum(len(c["variants"]) for c in chrom.values()) == len(analysis["variants"])
    assert a["variants_not_placed"] == []
    gene = next(g for g in a["genes"] if g["gene"] == "ATP7B")
    assert gene["diseases"][0]["name"] == "Wilson disease" and "hepatic" in gene["systems"]


def test_anatomy_is_empty_not_invented_without_data(client):
    pid = make_patient(client)
    a = twin(client, pid)["anatomy"]
    assert all(not s["has_case_data"] for s in a["systems"])
    assert all(c["variants"] == [] for c in a["chromosomes"])
    assert any("not imaging" in n or "not a scan" in n or "scan of the patient" in n for n in a["notes"])


def test_variant_evidence_fields_are_exposed(client, full_case):
    pid, _, _ = full_case
    v = next(x for x in twin(client, pid)["genomic"]["variants"] if x["variant_id"] == ATP7B_VID)
    assert v["chrom"] == "chr13" and v["pos"] and v["criteria_met_pathogenic"] and v["acmg_explanation"]


def test_scenario_reports_real_stages_and_system_impact(client, full_case):
    pid, _, _ = full_case
    registry.twin.engine._dx_cache.clear()   # make cache behaviour deterministic for this test
    r = scenario(client, pid, "variant_exclusion", {"variant_ids": [ATP7B_VID]})
    ids = [s["id"] for s in r["stages"]]
    assert ids == ["apply", "genomic", "phenotype", "compare"]
    timed = [s for s in r["stages"] if s["ms"] is not None]
    assert timed and all(s["ms"] >= 0 for s in timed)
    assert "re-run" not in next(s for s in r["stages"] if s["id"] == "phenotype")["detail"]
    impact = {i["system"]: i for i in r["system_impact"]}
    assert impact["hepatic"]["variants_before"] == 1 and impact["hepatic"]["variants_after"] == 0
    # phenotype scenario really re-runs the engine
    r2 = scenario(client, pid, "phenotype_add", {"hpo_ids": ["HP:0001903"]})
    assert "re-run" in next(s for s in r2["stages"] if s["id"] == "phenotype")["detail"]
    r3 = scenario(client, pid, "medication", {"drugs": ["clopidogrel"]})
    assert [s["id"] for s in r3["stages"]] == ["apply", "compute", "compare"] and r3["system_impact"] == []
