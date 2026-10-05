import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_registry_file_shape():
    reg = json.loads((ROOT / "models" / "registry.json").read_text(encoding="utf-8"))
    ids = {m["id"] for m in reg["models"]}
    assert {"diagnosis_engine", "gnn_han_reranker", "hpo_mapper", "clinical_ner", "variant_prioritizer"} <= ids
    for m in reg["models"]:
        assert "status" in m and "default_on" in m


def test_gnn_not_default_and_unmeasured_states_honest():
    reg = json.loads((ROOT / "models" / "registry.json").read_text(encoding="utf-8"))
    by = {m["id"]: m for m in reg["models"]}
    assert by["gnn_han_reranker"]["default_on"] is False
    assert "Not evaluated" in str(by["variant_prioritizer"]["metrics"])
    from ml_services.graph_ai.gnn_diagnosis import DifferentialDiagnosisEngine
    assert DifferentialDiagnosisEngine.__init__.__defaults__[-1] is False


def test_model_cards_exist():
    assert len(list((ROOT / "docs" / "model_cards").glob("*.md"))) >= 5


def test_registry_api_requires_auth():
    c = TestClient(app)
    assert c.get("/api/v1/ml/registry").status_code in (401, 403)
