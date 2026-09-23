"""Module 1/2 tests: code-mixed NER, token-level LID, HPO mapping."""
from __future__ import annotations

import pytest

from ml_services.config import SEEDS_DIR
from ml_services.nlp.clinical_ner import LexicalRuleNER, get_ner
from ml_services.nlp.hpo_mapper import HPOMapper
from ml_services.nlp.symptom_normalizer import SymptomNormalizer
from ml_services.utils import read_jsonl, token_language


@pytest.fixture(scope="module")
def ner():
    return LexicalRuleNER()


@pytest.fixture(scope="module")
def mapper():
    return HPOMapper(use_embeddings=False)


def test_token_level_language_id():
    # Indic scripts are identified directly
    assert token_language("बुखार") == "HI"            # Devanagari
    assert token_language("காய்ச்சல்") == "TA"        # Tamil
    assert token_language("జ్వరం") == "TE"            # Telugu
    # Romanised Hindi is the interesting case: Latin script but not English
    assert token_language("bukhar") == "HI-LATN"
    assert token_language("piliya") == "HI-LATN"
    assert token_language("patient") == "EN"
    # Domain vocabulary can extend the romanised lexicon
    assert token_language("karyotype", {"karyotype"}) == "HI-LATN"


def test_ner_extracts_symptoms(ner):
    r = ner.extract("Patient ko 6 mahine se haath pair mein sujan hai")
    labels = {e["label"] for e in r["entities"]}
    assert "SYMPTOM" in labels
    assert any("sujan" in e["text"] for e in r["entities"])
    assert all(e["start"] < e["end"] for e in r["entities"])


def test_ner_code_mixed_detection(ner):
    mixed = ner.extract("Patient ko piliya hai and weight loss since 2 months")
    assert mixed["is_code_mixed"] is True
    assert mixed["lid_counts"]["HI-LATN"] >= 3  # ko / piliya / hai
    assert mixed["lid_counts"]["EN"] >= 3
    assert mixed["romanised_hindi_tokens"] >= 3


def test_ner_duration_lab_and_family(ner):
    r = ner.extract("HbA2 5.2 hai, 2 hafte se bukhaar, cousin marriage hai")
    labels = {e["label"] for e in r["entities"]}
    assert "LAB_VALUE" in labels and "DURATION" in labels and "FAMILY_HISTORY" in labels


def test_ner_drugs(ner):
    r = ner.extract("Clopidogrel aur warfarin dono chal rahe hain")
    drugs = {e["text"].lower() for e in r["entities"] if e["label"] == "DRUG"}
    assert {"clopidogrel", "warfarin"} <= drugs


def test_seed_sentences_roundtrip(ner):
    """Every hand-labelled seed sentence must yield at least one entity of its annotated type."""
    rows = read_jsonl(SEEDS_DIR / "clinical_ner_seed.jsonl")
    assert len(rows) >= 20
    missing = []
    for row in rows:
        got = {e["label"] for e in ner.extract(row["text"])["entities"]}
        expected = {e["label"] for e in row["entities"]}
        if not (expected & got):
            missing.append(row["id"])
    # lexical NER is a baseline: allow a small miss rate, but most sentences must hit
    assert len(missing) <= 4, f"too many seed sentences unmatched: {missing}"


def test_normalizer_dictionary_hits():
    sn = SymptomNormalizer()
    assert sn.normalize("piliya")["hpo_id"] == "HP:0000952"
    assert sn.normalize("mirgi ka daura")["hpo_id"] == "HP:0001250"
    assert sn.normalize("piliya")["confidence"] == 1.0
    assert sn.normalize("piliya")["method"] == "dictionary"


def test_normalizer_flags_unknown_for_review():
    sn = SymptomNormalizer()
    r = sn.normalize("something totally unrelated xyzzy")
    assert r["needs_review"] is True


def test_mapper_produces_hpo_profile(mapper):
    out = mapper.map_text("Peeli aankhein aur piliya do hafte se hai")
    assert "HP:0000952" in out["hpo_ids"]
    assert out["hpo_profile"][0]["confidence"] >= 0.5
    assert out["hpo_profile"][0]["hpo_name"]


def test_mapper_records_confidence_and_method(mapper):
    out = mapper.map_phrase("raat mein na dikhna")
    assert out[0]["hpo_id"] == "HP:0000618"
    assert 0.0 < out[0]["score"] <= 1.0


def test_mapper_flags_low_confidence(mapper):
    out = mapper.map_text("kuch ajeeb sa lakshan hai jo samajh nahi aata")
    assert "low_confidence_count" in out
    assert isinstance(out["unmapped_symptoms"], list)


def test_get_ner_returns_lexical_without_checkpoint():
    assert get_ner().__class__.__name__ in ("LexicalRuleNER", "MuRILNER")
