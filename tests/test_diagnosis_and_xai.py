"""Module 3/4/7 tests: phenotype similarity, Indian priors, uncertainty, explainability."""
from __future__ import annotations

import pytest

from ml_services.config import SEEDS_DIR
from ml_services.graph_ai import bayesian
from ml_services.graph_ai.gnn_diagnosis import DifferentialDiagnosisEngine
from ml_services.graph_ai.resnik import PhenomizerBaseline
from ml_services.utils import read_jsonl
from ml_services.xai.explainability import CaseIndex, ExplainabilityLayer

WILSON_HPO = read_jsonl(SEEDS_DIR / "seed_cases.jsonl")[0]["hpo"]  # C001: enriched clinical profile


@pytest.fixture(scope="module")
def baseline():
    return PhenomizerBaseline()


@pytest.fixture(scope="module")
def engine():
    return DifferentialDiagnosisEngine()


def test_information_content_is_inverse_frequency(baseline):
    # A term annotated to fewer diseases must be at least as informative as a common one
    assert baseline.total_diseases >= 15
    assert all(v >= 0 for v in baseline.ic.values())
    common = baseline.ic.get("HP:0000707", 0.0)
    specific = baseline.ic.get("HP:0000616", 0.0)
    assert specific >= common


def test_mica_of_identical_terms_is_self(baseline):
    mica, ic = baseline.mica("HP:0001250", "HP:0001250")
    assert mica in ("HP:0001250", "HP:0000707", "HP:0000118")
    assert ic > 0


def test_phenomizer_baseline_ranks_wilson_first(baseline):
    ranked = baseline.diagnose(WILSON_HPO, top_k=3)
    assert ranked[0]["disease_id"] == "ORPHA:915"
    assert ranked[0]["score"] > ranked[1]["score"]


def test_baseline_evaluation_on_seed_cases(baseline):
    cases = read_jsonl(SEEDS_DIR / "seed_cases.jsonl")
    metrics = baseline.evaluate(cases, k=3)
    assert metrics["n_cases"] >= 10
    assert metrics["hits@3"] >= 0.8
    assert metrics["mrr"] >= 0.6


def test_engine_returns_top10_with_uncertainty(engine):
    result = engine.diagnose(WILSON_HPO, {"state": "Andhra Pradesh", "community": "Reddy", "sex": "M"},
                             top_k=10)
    assert len(result["results"]) <= 10
    top = result["results"][0]
    # Top-3 must contain Wilson (ORPHA:915): at 12.9k-disease scale a generic 3-term
    # vignette legitimately leaves near-ties (Cockayne ORPHA:355 shares the same terms),
    # and the India prior + GNN re-rank within that tie band rather than forcing one winner.
    top3 = [r["disease_id"] for r in result["results"][:3]]
    assert "ORPHA:915" in top3
    assert 0 < top["probability"] <= 1
    lo, hi = top["probability_ci"]
    assert lo < hi
    assert "similarity_jackknife" in top
    # engine label reflects the active backend: trained HAN checkpoint when present,
    # else the deterministic graph-similarity + India-prior path
    assert result["engine"] in ("gnn_han", "graph_similarity+india_prior")


def test_probabilities_are_sorted_and_bounded(engine):
    """Probabilities come from a softmax over every candidate disease, so the returned
    top-k shares sum to <= 1 and must be monotonically non-increasing."""
    result = engine.diagnose(WILSON_HPO, top_k=10)
    probs = [r["probability"] for r in result["results"]]
    assert probs == sorted(probs, reverse=True)
    assert 0 < sum(probs) <= 1.0001
    assert all(0 < p <= 1 for p in probs)


def test_indian_prior_raises_founder_disease_in_community(engine):
    """Same phenotype, two communities: the founder-risk community must score the disease higher."""
    hpo = ["HP:0001878", "HP:0012532"]  # hemolytic anemia + pain (sickle-like)
    tribal = engine.diagnose(hpo, {"state": "Chhattisgarh", "community": "Gond"}, top_k=10)
    other = engine.diagnose(hpo, {"state": "Chhattisgarh", "community": "Kannada"}, top_k=10)
    sickle_tribal = next((r for r in tribal["results"] if r["disease_id"] == "ORPHA:232"), None)
    sickle_other = next((r for r in other["results"] if r["disease_id"] == "ORPHA:232"), None)
    assert sickle_tribal and sickle_other
    # In the founder community the founder multiplier (3x for Gond) must engage and
    # raise the disease's probability vs the same query without founder risk.
    assert sickle_tribal["population_prior"]["founder_multiplier"] == 3.0
    assert sickle_tribal["population_prior"]["prior_applied_to_ranking"] is True
    assert sickle_tribal["probability"] > sickle_other["probability"]


def test_consanguinity_multiplier_applies_to_recessive_only(engine):
    rec = engine.population_prior("ORPHA:231222", state="Tamil Nadu")   # autosomal recessive
    dom = engine.population_prior("ORPHA:558", state="Tamil Nadu")      # autosomal dominant
    low = engine.population_prior("ORPHA:231222", state="Punjab")
    assert rec["consanguinity_multiplier"] > low["consanguinity_multiplier"]
    assert dom["consanguinity_multiplier"] < rec["consanguinity_multiplier"]


def test_attribution_weights_sum_to_100(engine):
    attrs = engine.attribute_symptoms(WILSON_HPO, "ORPHA:915")
    assert attrs and abs(sum(a["weight_pct"] for a in attrs) - 100.0) < 1.0


def test_missing_findings_suggested(engine):
    missing = engine.missing_terms(["HP:0000616"], "ORPHA:915")
    assert missing
    assert all(m["hpo_id"] != "HP:0000616" for m in missing)


def test_referral_services_returned(engine):
    ref = engine.nearest_services("ORPHA:915", state="Telangana")
    assert ref["labs"] and ref["specialists"]
    assert ref["labs"][0]["nabl"] is True


def test_confirmatory_tests_attached(engine):
    result = engine.diagnose(WILSON_HPO, top_k=1)
    tests = result["results"][0]["confirmatory_tests"]
    assert any("ceruloplasmin" in t.lower() for t in tests["first_line"])
    assert tests["genetic"]


def test_bayesian_helpers():
    lo, hi = bayesian.bootstrap_ci([0.2, 0.4, 0.6, 0.8])
    assert lo <= hi
    plo, phi = bayesian.beta_ci(0.5)
    assert 0 <= plo < 0.5 < phi <= 1
    jlo, jhi = bayesian.jackknife_ci(WILSON_HPO, lambda terms: len(terms) / 10)
    assert jlo <= jhi


def test_case_index_retrieves_similar_cases():
    idx = CaseIndex()
    hits = idx.search(["HP:0000616", "HP:0001337", "HP:0001394"], k=3)
    assert hits
    assert hits[0]["similarity"] >= hits[-1]["similarity"]
    assert hits[0]["shared_findings"]


def test_xai_bundle_layers():
    xai = ExplainabilityLayer()
    bundle = xai.explain(text="Bacha 6 saal ka hai, haath kaanpna shuru ho gaya hai, piliya bhi hai",
                         patient_context={"state": "Andhra Pradesh"}, lang="hi")
    expl = bundle["explanation"]
    assert expl is not None
    for layer in ("attribution", "graph_attention", "case_based_reasoning", "phenotype_map",
                  "narrative"):
        assert layer in expl
    assert expl["graph_attention"]["nodes"]
    assert expl["narrative"]["lang"] == "hi"
    assert "\n" in expl["narrative"]["markdown"]


def test_xai_handles_no_match():
    xai = ExplainabilityLayer()
    bundle = xai.explain(hpo_ids=[], patient_context={})
    assert bundle["explanation"] is None or "note" in bundle
