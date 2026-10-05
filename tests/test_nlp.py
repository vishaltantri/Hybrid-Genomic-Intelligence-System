"""Phase 5: clinical text intelligence, tested on labelled synthetic notes (no patient data)."""
import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.security import create_access_token
from backend.app.services import registry
from ml_services.nlp.clinical_text import assess_context


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


def run(text):
    return registry.clinical_text.analyze(text)


def by(res, label, text=None):
    return [e for e in res["entities"] if e["label"] == label and (text is None or e["text"].lower() == text.lower())]


NOTE = ("12 year old girl with tremor and jaundice since 6 months. No fever, seizures or tremor. Mother has Wilson disease; "
        "ATP7B c.3207C>A found. Hb: 9.2. Wilson disease ruled out in brother. Started clopidogrel.")


def test_phenotype_present_with_hpo_and_onset():
    r = run(NOTE)
    j = by(r, "PHENOTYPE", "jaundice")[0]
    assert j["assertion"] == "present" and j["normalized"]["id"] == "HP:0000952" and j["normalized"]["system"] == "HPO"
    assert j["onset"]["amount"] == 6 and j["onset"]["unit"].startswith("month")
    assert by(r, "AGE")[0]["text"] == "12 year old"


def test_negation_list_and_clause_scope():
    r = run("No fever, seizures or tremor.")
    assert {e["text"]: e["assertion"] for e in by(r, "PHENOTYPE")} == {"fever": "absent", "seizures": "absent", "tremor": "absent"}
    r = run("No fever, but tremor present.")
    assert {e["text"]: e["assertion"] for e in by(r, "PHENOTYPE")} == {"fever": "absent", "tremor": "present"}


def test_negation_does_not_cross_sentences():
    r = run("Denies seizures. Has tremor.")
    assert {e["text"]: e["assertion"] for e in by(r, "PHENOTYPE")} == {"seizures": "absent", "tremor": "present"}


def test_post_negation_and_ruled_out():
    t = "Seizures not present. Tremor ruled out."
    r = run(t)
    assert all(e["assertion"] == "absent" for e in by(r, "PHENOTYPE"))
    assert by(r, "PHENOTYPE", "tremor")[0]["ruled_out"] is True


def test_uncertainty_and_history():
    r = run("Possible seizures. Suspected tremor. History of jaundice.")
    got = {e["text"]: e["assertion"] for e in by(r, "PHENOTYPE")}
    assert got == {"seizures": "possible", "tremor": "possible", "jaundice": "historical"}
    assert run("Possible seizures.")["summary"]["possible_phenotypes"][0]["hpo_id"] == "HP:0001250"


def test_family_context_is_not_the_patient():
    r = run(NOTE)
    d = by(r, "DISEASE", "Wilson disease")
    assert d[0]["experiencer"] == "family" and d[0]["family_relation"] == "mother"
    assert d[1]["experiencer"] == "family" and d[1]["family_relation"] == "brother" and d[1]["assertion"] == "absent"
    rel = {f["relation"]: f["assertion"] for f in r["summary"]["family_findings"]}
    assert rel == {"mother": "present", "brother": "absent"}
    # family phenotypes never enter the patient's HPO lists
    r2 = run("Her mother has tremor.")
    assert r2["summary"]["hpo_ids_present"] == [] and r2["summary"]["family_findings"][0]["relation"] == "mother"


def test_gene_variant_link_only_when_unambiguous():
    r = run(NOTE)
    v = by(r, "VARIANT")[0]
    assert v["value"]["gene"] == "ATP7B" and v["value"]["kind"] == "hgvs_c"
    r = run("ATP7B and VHL were tested and c.3207C>A was seen.")
    v = by(r, "VARIANT")[0]
    assert v["value"]["gene"] is None and "ambiguous" in v["value"]["gene_link"]
    assert by(run("rs12345 noted."), "VARIANT")[0]["normalized"]["system"] == "dbSNP"


def test_genes_need_graph_membership_and_uppercase():
    r = run("The ATP7B gene, and ICU stay, and nothing else like Tremor.")
    assert [e["text"] for e in by(r, "GENE")] == ["ATP7B"]


def test_drug_normalised_only_when_known():
    d = by(run("Started clopidogrel."), "DRUG")[0]
    assert d["normalized"]["id"] == "clopidogrel" and d["normalized"]["status"] == "normalized"


def test_lab_value_parsed_not_normalised():
    lab = by(run("Hb: 9.2 g/dL."), "LAB")[0]
    assert lab["value"]["analyte"].lower() == "hb" and lab["value"]["value"] == 9.2 and lab["normalized"]["status"] == "unmapped"


def test_conflict_detected_only_from_explicit_text():
    r = run("Tremor is present. Later: no tremor.")
    assert [c["hpo_id"] for c in r["summary"]["conflicts"]] == ["HP:0001337"]
    assert run("Tremor present.")["summary"]["conflicts"] == []


def test_hindi_english_code_mixed():
    r = run("Bachche ko tremor hai aur seizures nahi hote.")
    got = {e["text"]: e["assertion"] for e in by(r, "PHENOTYPE")}
    assert got.get("tremor") == "present"


def test_unsupported_labels_declared_and_unproduced():
    r = run("MRI brain done. Biopsy of the liver was taken.")
    assert not by(r, "PROCEDURE") and not by(r, "ANATOMICAL_SITE")
    assert set(r["engine"]["unsupported_labels"]) == {"PROCEDURE", "ANATOMICAL_SITE"}


def test_assess_context_unit():
    t = "no fever"
    a = assess_context(t, 3, 8, (0, len(t)))
    assert a["negated"] and a["assertion"] == "absent"


def test_no_text_invented():
    r = run("Routine follow-up visit. Nothing to report.")
    assert r["summary"]["hpo_ids_present"] == [] and r["summary"]["possible_phenotypes"] == []


# --------------------------------- API ---------------------------------

def test_analyze_endpoint_and_audit(client):
    r = client.post("/api/v1/nlp/analyze", json={"text": NOTE}, headers=hdr())
    assert r.status_code == 200
    j = r.json()
    assert j["entities"] and j["summary"]["hpo_ids_present"] and "disclaimer" in j
    assert client.post("/api/v1/nlp/entities", json={"text": NOTE}, headers=hdr()).json()["counts"]["PHENOTYPE"] >= 3


def test_normalize_endpoint(client):
    r = client.post("/api/v1/nlp/normalize", json={"phrases": ["tremor", "qwertyzzz"]}, headers=hdr()).json()["results"]
    assert r[0]["candidates"][0]["hpo_id"] == "HP:0001337" and r[0]["status"] == "mapped"
    assert r[1]["status"] in ("unmapped", "needs_review")


def test_validation_and_auth(client):
    assert client.post("/api/v1/nlp/analyze", json={"text": "   "}, headers=hdr()).status_code == 422
    assert client.post("/api/v1/nlp/analyze", json={"text": "x" * 20001}, headers=hdr()).status_code == 422
    assert client.post("/api/v1/nlp/analyze", json={"text": "tremor", "patient_id": "NOPE"}, headers=hdr()).status_code == 404
    assert client.post("/api/v1/nlp/analyze", json={"text": "tremor"}).status_code in (401, 403)
    assert client.post("/api/v1/nlp/analyze", json={"text": "tremor"}, headers=hdr("p", "patient")).status_code == 403
    assert client.post("/api/v1/nlp/normalize", json={"phrases": []}, headers=hdr()).status_code == 422


def test_capabilities(client):
    j = client.get("/api/v1/nlp/capabilities", headers=hdr()).json()
    assert "PHENOTYPE" in j["supported_labels"] and "PROCEDURE" in j["unsupported_labels"]


def test_assistant_receives_nlp_context(client, monkeypatch):
    seen = {}
    svc = registry.assistant
    orig = svc.handle_message if hasattr(svc, "handle_message") else None
    ctx = registry.clinical_text.ai_context(NOTE)
    assert "Explicitly absent" in ctx["text"] and "Family (mother)" in ctx["text"]
    assert ctx["citations"][0]["source_type"] == "clinical_text_nlp"
    r = client.post("/api/v1/assistant/chat", json={"message": "Summarise this note", "clinical_text": NOTE}, headers=hdr())
    assert r.status_code == 200
    assert any(c.get("source_type") == "clinical_text_nlp" for c in r.json()["citations"])
    assert client.post("/api/v1/assistant/chat", json={"message": "x", "clinical_text": NOTE}, headers=hdr("p", "patient")).status_code in (403,)
    del seen, orig
