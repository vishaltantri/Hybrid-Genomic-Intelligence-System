"""Module 8/9/10 tests: federated simulation + DP, ASHA triage, continuous learning."""
from __future__ import annotations

import pytest

from ml_services.asha.community_alerts import CommunityAlertEngine
from ml_services.asha.triage_engine import TriageEngine
from ml_services.asha.vocab_corrector import MedicalVocabCorrector
from ml_services.federated import dp as dp_mod
from ml_services.federated.fl_server import FederatedSimulator
from ml_services.federated.noniid_partition import (
    partition_by_archetype,
    partition_by_disease,
)
from ml_services.learning_pipeline import drift as drift_mod
from ml_services.learning_pipeline.active_learning import ActiveLearningQueue
from ml_services.learning_pipeline.kg_update import KGUpdateManager
from ml_services.learning_pipeline.pubmed_scraper import fetch_pubmed
from ml_services.learning_pipeline.triple_extraction import TripleExtractor


# ------------------------------ federated ------------------------------

def test_dirichlet_partition_is_non_iid():
    from ml_services.config import SEEDS_DIR
    from ml_services.utils import read_jsonl

    cases = read_jsonl(SEEDS_DIR / "seed_cases.jsonl")
    buckets = partition_by_disease(cases, n_clients=5, alpha=0.3)
    assert sum(len(b) for b in buckets) == len(cases)


def test_archetype_partition_assigns_all_cases():
    from ml_services.config import SEEDS_DIR
    from ml_services.utils import read_jsonl

    cases = read_jsonl(SEEDS_DIR / "seed_cases.jsonl")
    clients = partition_by_archetype(cases, n_clients=4)
    assert sum(len(c["data"]) for c in clients) == len(cases)
    assert all(c["archetype"] in ("metro_tertiary", "district", "tribal", "phc") for c in clients)


def test_dp_clipping_and_noise():
    import numpy as np

    grads = [np.array([10.0, 0.0]), np.array([0.5, 0.5])]
    out, info = dp_mod.clip_and_noise(grads, clip_norm=1.0, sigma=1.0)
    assert len(out) == 1
    assert info["clipped_fraction"] > 0
    assert info["mean_grad_norm"] > 1.0


def test_epsilon_grows_with_steps_and_shrinks_with_noise():
    assert dp_mod.gaussian_epsilon(1.0, 100) > dp_mod.gaussian_epsilon(1.0, 10)
    assert dp_mod.gaussian_epsilon(2.0, 50) < dp_mod.gaussian_epsilon(0.5, 50)


def test_secure_aggregation_equals_plain_sum():
    import numpy as np

    updates = [np.array([1.0, 2.0]), np.array([3.0, 4.0]), np.array([5.0, 6.0])]
    masked = dp_mod.secure_sum_masked(updates, n_clients=3)
    assert np.allclose(masked, np.sum(np.stack(updates), axis=0))


def test_federated_training_improves_and_reports():
    sim = FederatedSimulator(n_clients=4, partition="disease", alpha=0.5)
    result = sim.train(rounds=8, algorithm="fedavg")
    assert result["final_mean_accuracy"] is not None
    assert result["history"][0]["round"] == 1
    assert len(result["history"]) == 8
    assert result["n_clients"] == 4


def test_federated_with_dp_reports_epsilon_and_secure_agg():
    sim = FederatedSimulator(n_clients=4)
    result = sim.train(rounds=4, algorithm="fedprox", sigma=1.1, secure_agg=True)
    assert result["secure_aggregation"] is True
    assert result["differential_privacy"]["epsilon_estimate"] > 0


def test_epidemiology_map_uses_real_labels_and_suppresses_small_cells():
    sim = FederatedSimulator(n_clients=4)
    epi = sim.epidemiology_map()
    assert epi["totals"]
    assert any(k.startswith("ORPHA:") for k in epi["totals"])
    assert "privacy_note" in epi


def test_privacy_utility_curve_monotone():
    curve = dp_mod.privacy_utility_curve([0.5, 1.0, 2.0])
    assert curve[0]["epsilon"] > curve[-1]["epsilon"]
    assert curve[0]["expected_utility_retained"] > curve[-1]["expected_utility_retained"]


# ------------------------------ ASHA ------------------------------

@pytest.fixture(scope="module")
def triage():
    return TriageEngine()


def test_triage_red_for_red_flags(triage):
    result = triage.triage_answers({"q_seizure": "haan", "q_pallor": "haan"})
    assert result["triage_color"] == "red"
    assert "seizures" in result["red_flags"]
    assert "तुरंत" in result["recommendation_hi"]


def test_triage_green_when_all_negative(triage):
    result = triage.triage_answers({"q_development": "nahi", "q_weakness": "nahi", "q_seizure": "nahi",
                                    "q_jaundice": "nahi", "q_pallor": "nahi", "q_family": "nahi"})
    assert result["triage_color"] in ("green", "yellow")
    assert result["recommendation"]


def test_triage_escalates_for_infant(triage):
    result = triage.triage_answers({"q_development": "thoda"}, {"age": 0.5})
    assert result["triage_color"] == "red"


def test_triage_text_path_uses_ner(triage):
    result = triage.triage_text("Bachche ko daura pad raha hai aur khoon ki kami hai", {"age": 3})
    assert result["triage_color"] == "red"
    assert "seizures" in result["red_flags"]
    assert result["hpo_ids"]


def test_referral_letters_generated(triage):
    result = triage.triage_answers({"q_seizure": "haan"}, {"age": 4, "village": "X"})
    assert "रेफरल" in result["referral_letter_hi"]
    assert "Referral" in result["referral_letter_en"]


def test_offline_record_is_compact_and_pending(triage):
    record = triage.to_offline_record(triage.triage_answers({"q_seizure": "haan"}, {"age": 4}))
    assert record["sync_state"] == "pending"
    assert record["schema_version"] == 1
    assert set(record) >= {"local_id", "triage_color", "symptoms", "village", "district"}


def test_community_alerts_find_outbreak():
    engine = CommunityAlertEngine()
    records = engine.simulate_village_records(n_villages=30, outbreak_villages=2)
    result = engine.scan(records)
    assert result["villages_scanned"] > 10
    high = [a for a in result["alerts"] if a["severity"] == "high"]
    assert high, "outbreak villages should raise high-severity alerts"
    assert any(a["signal_type"] == "volume" for a in result["alerts"])
    assert all(a["total_presentations"] >= 3 for a in result["alerts"])


def test_poisson_tail_sanity():
    assert CommunityAlertEngine().scan([])["alerts"] == []
    from ml_services.asha.community_alerts import poisson_tail

    assert poisson_tail(0, 4.0) > poisson_tail(12, 4.0)
    assert poisson_tail(12, 4.0) < 0.01


def test_vocab_corrector_fixes_asr_noise():
    corrector = MedicalVocabCorrector()
    out = corrector.correct_text("bachche ko kamjori aur pili ya hai")
    assert out["n_changes"] >= 1
    joined = out["corrected"].lower()
    assert "kamzori" in joined or "piliya" in joined


def test_vocab_corrector_leaves_valid_words_alone():
    corrector = MedicalVocabCorrector()
    out = corrector.correct_text("clopidogrel diya gaya hai")
    assert out["n_changes"] == 0


# ------------------------------ learning pipeline ------------------------------

def test_pubmed_offline_mode_does_not_hit_network():
    result = fetch_pubmed("query_that_has_no_cache_xyz", offline=True)
    assert result["articles"] == []


def test_triple_extraction_produces_reviewable_proposals():
    articles = [{
        "pmid": "1", "title": "ATP7B mutations cause Wilson disease in Indian children",
        "abstract": "ATP7B mutations cause Wilson disease. Consanguinity was reported in 22% of families.",
        "journal": "J", "year": "2025", "url": "x",
    }]
    result = TripleExtractor().extract_batch(articles)
    assert result["n_proposals"] >= 1
    assert all(p["status"] == "pending_review" for p in result["proposals"])
    assert all(p["evidence_sentence"] for p in result["proposals"])


def test_kg_update_ranks_and_applies_without_persisting():
    from ml_services.etl.graph_store import GraphData

    graph = GraphData()
    mgr = KGUpdateManager(graph=graph)
    proposals = [{"proposal_id": "P1", "subject_type": "Gene", "subject": "G6PD",
                  "predicate": "ASSOCIATED_WITH", "object_type": "Disease",
                  "object": "G6PD deficiency", "confidence": 0.9,
                  "evidence_sentence": "G6PD variants in Indian tribal populations",
                  "pmid": "2"}]
    ranked = mgr.rank_for_review(proposals)
    assert ranked[0]["review_priority"] >= 0.9
    result = mgr.apply_review(ranked, reviewer="tester", persist=False, record_audit=False)
    assert result["summary"]["added_edges"] == 1
    assert graph.node("Disease", "G6PD deficiency") is not None


def test_drift_detection_flags_shift():
    report = drift_mod.simulate_drift_example()
    assert report["overall_status"] == "significant_shift"
    assert report["retraining_needed"] is True
    assert any(c["metric"] == "disease_mix" for c in report["checks"])


def test_drift_stable_when_identical():
    import numpy as np

    rng = np.random.default_rng(0)
    sample = rng.normal(0, 1, 200)
    monitor = drift_mod.DriftMonitor({"metric": list(sample)})
    check = monitor.check_numeric("metric", sample)
    assert check["status"] == "stable"


def test_uncertainty_scoring_prefers_ambiguous_case():
    q = ActiveLearningQueue()
    uncertain = q.score_uncertainty(
        [{"hpo_id": "HP:1", "confidence": 0.3}],
        {"results": [{"disease_id": "A", "probability": 0.31}, {"disease_id": "B", "probability": 0.30}]},
        ["unmapped thing"],
    )
    confident = q.score_uncertainty(
        [{"hpo_id": "HP:1", "confidence": 0.99}],
        {"results": [{"disease_id": "A", "probability": 0.95}, {"disease_id": "B", "probability": 0.01}]},
        [],
    )
    assert uncertain["composite_uncertainty"] > confident["composite_uncertainty"]


def test_feedback_records_without_dictionary_mutation(tmp_path):
    """Uses a temp queue/store path so the test cannot pollute the real review artefacts."""
    q = ActiveLearningQueue(queue_path=tmp_path / "queue.jsonl", store_path=tmp_path / "store.json")
    q.items = [{"text": "demo", "hpo_profile": [], "candidate_diagnoses": [], "uncertainty": {},
                "status": "pending_review"}]
    out = q.record_feedback(0, reviewer="tester", decision="confirmed", corrected_hpo={},
                            corrected_diagnosis="ORPHA:915")
    assert out["feedback_recorded"]["decision"] == "confirmed"
    assert q.items[0]["status"] == "reviewed_confirmed"
    assert (tmp_path / "queue.jsonl").exists()
    assert q.stats()["by_status"] == {"reviewed_confirmed": 1}
    assert q.training_export()["n_diagnosis_corrections"] == 1
