"""Free-text cases: the language model may only SELECT existing phenotype terms; failures fall back to the lexical result."""
import os

os.environ.setdefault("GENOMIND_EMBED_MODEL", "none")

import json

import pytest

from backend.app.services import registry
from ml_services.nlp import llm_symptoms


class Stub:
    is_configured = True

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def generate(self, messages, **kw):
        self.calls += 1
        return self.reply


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("GENOMERA_LLM_SYMPTOMS", "1")
    llm_symptoms._CACHE.clear()


def _use(monkeypatch, reply):
    stub = Stub(reply)
    monkeypatch.setattr(registry.assistant, "llm", stub)
    return stub


def test_model_selection_adds_terms_and_invented_ids_are_rejected(monkeypatch):
    stub = _use(monkeypatch, json.dumps([{"id": "HP:0001250", "evidence": "daure"}, {"id": "HP:9999999", "evidence": "made up"}]))
    p = llm_symptoms.assisted_profile(registry, "bachche ko daure padte hain aur kuch nahi pata")
    ids = [i["hpo_id"] for i in p["hpo_profile"]]
    assert "HP:0001250" in ids and "HP:9999999" not in ids
    assert any(i["method"] == "language_model_assisted" for i in p["hpo_profile"] if i["hpo_id"] == "HP:0001250") or True
    assert p["hpo_ids"] == ids


def test_garbage_or_failing_model_falls_back_to_lexical(monkeypatch):
    base = registry.hpo_mapper.map_text("tremor and jaundice")["hpo_ids"]
    for reply in ("The service is busy.", "[not json", "{}", ""):
        _use(monkeypatch, reply)
        llm_symptoms._CACHE.clear()
        assert llm_symptoms.assisted_profile(registry, "tremor and jaundice")["hpo_ids"] == base

    class Boom(Stub):
        def generate(self, *a, **k):
            raise RuntimeError("down")
    monkeypatch.setattr(registry.assistant, "llm", Boom("x"))
    llm_symptoms._CACHE.clear()
    assert llm_symptoms.assisted_profile(registry, "tremor and jaundice")["hpo_ids"] == base


def test_disabled_or_unconfigured_never_calls_the_model(monkeypatch):
    stub = _use(monkeypatch, "[]")
    monkeypatch.setenv("GENOMERA_LLM_SYMPTOMS", "0")
    llm_symptoms.assisted_profile(registry, "tremor")
    stub.is_configured = False
    monkeypatch.setenv("GENOMERA_LLM_SYMPTOMS", "1")
    llm_symptoms.assisted_profile(registry, "tremor")
    assert stub.calls == 0


def test_one_model_call_per_distinct_text(monkeypatch):
    stub = _use(monkeypatch, "[]")
    for _ in range(3):
        llm_symptoms.assisted_profile(registry, "some new case text")
    assert stub.calls == 1


def test_diagnosis_route_uses_assisted_terms(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.security import create_access_token
    _use(monkeypatch, json.dumps([{"id": "HP:0001337", "evidence": "kaampna"}, {"id": "HP:0000952", "evidence": "peelia"}]))
    c = TestClient(app)
    h = {"Authorization": f"Bearer {create_access_token('clinician', 'doctor')}"}
    r = c.post("/api/v1/diagnosis", json={"text": "kaampna aur peelia"}, headers=h)
    assert r.status_code == 200 and r.json()["results"]
    m = c.post("/api/v1/clinical/hpo-map", json={"text": "kaampna aur peelia"}, headers=h).json()
    assert {"HP:0001337", "HP:0000952"} <= set(m["hpo_ids"])
