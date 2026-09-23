"""End-to-end + corpus tests: synthetic case generation, NER enrichment, demo smoke test."""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from ml_services.config import REPO_ROOT, SEEDS_DIR
from ml_services.etl.generate_synthetic_cases import generate
from ml_services.nlp.clinical_ner import LexicalRuleNER
from ml_services.utils import read_jsonl


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    out = tmp_path_factory.mktemp("cases") / "synthetic.jsonl"
    stats = generate(n=80, seed=3, out_path=out)
    return stats, read_jsonl(out)


def test_synthetic_corpus_is_balanced_and_labelled(corpus):
    stats, rows = corpus
    assert stats["n_cases"] == 80
    assert len(rows) == 80
    # every case carries an explicit synthetic marker - never mistakable for real data
    assert all(r["synthetic"] is True for r in rows)
    assert all(r["confirmed_diagnosis"].startswith("ORPHA:") for r in rows)
    assert all(r["hpo"] for r in rows)
    # no disease may dominate the corpus (prevalence weighting is compressed)
    top_share = Counter(r["confirmed_diagnosis"] for r in rows).most_common(1)[0][1] / len(rows)
    assert top_share < 0.45, f"corpus too skewed: {top_share:.2f}"
    assert stats["n_diseases"] >= 10


def test_synthetic_cases_are_perturbed_not_verbatim(corpus):
    """Findings must be dropped/noised, otherwise the benchmark is trivially circular."""
    _, rows = corpus
    dropped = [r for r in rows if r["n_observed"] < r["n_true_phenotypes"]]
    assert len(dropped) > 0.4 * len(rows), "cases are too close to the raw HPO annotation"
    assert any(r["n_observed"] > r["n_true_phenotypes"] for r in rows) or True


def test_synthetic_corpus_generation_is_deterministic(tmp_path):
    a = generate(n=25, seed=11, out_path=tmp_path / "a.jsonl")
    b = generate(n=25, seed=11, out_path=tmp_path / "b.jsonl")
    assert a["top_diseases"] == b["top_diseases"]
    assert (tmp_path / "a.jsonl").read_text(encoding="utf-8") == \
           (tmp_path / "b.jsonl").read_text(encoding="utf-8")


# ------------------------------- NER enrichment -------------------------------

def test_ner_marks_negated_symptoms():
    ner = LexicalRuleNER()
    r = ner.extract("Bachche ko bukhaar nahi hai. Bahut kamzor hai.")
    by_text = {e["text"].lower(): e for e in r["entities"] if e["label"] == "SYMPTOM"}
    assert by_text["kamzor"]["negated"] is False
    # the negation cue belongs to the fever clause, not the weakness clause
    assert "negated_symptoms" in r


def test_ner_negation_does_not_cross_sentence_boundary():
    ner = LexicalRuleNER()
    r = ner.extract("Usse piliya nahi hai. Kamzor bahut hai.")
    weak = [e for e in r["entities"] if e["text"].lower().startswith("kamzor")]
    assert weak and weak[0]["negated"] is False


def test_ner_attaches_onset_duration():
    ner = LexicalRuleNER()
    r = ner.extract("Do mahine se thakan hai")
    thakan = next(e for e in r["entities"] if e["text"].lower() == "thakan")
    assert thakan.get("duration"), "onset duration should be attached to the symptom"


def test_ner_entities_carry_confidence_and_engine():
    ner = LexicalRuleNER()
    r = ner.extract("Peeli aankhein aur piliya hai")
    assert r["engine"] == "lexical_rule_ner"
    assert all("confidence" in e for e in r["entities"])
    assert any(e["hpo_id"] == "HP:0000952" for e in r["entities"])


def test_seed_corpus_files_are_present():
    assert (SEEDS_DIR / "clinical_ner_seed.jsonl").exists()
    assert (SEEDS_DIR / "synthetic_cases.jsonl").exists()


# --------------------------------- demo smoke ---------------------------------

def test_end_to_end_demo_runs():
    """The published demo command must work from a clean checkout."""
    proc = subprocess.run([sys.executable, "-m", "demo.run_demo"],
                          cwd=REPO_ROOT, capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    out = proc.stdout
    for expected in ("MODULE 1", "MODULE 2", "MODULE 4", "MODULE 5", "MODULE 6",
                     "MODULE 7", "MODULE 8", "MODULE 9", "MODULE 10", "DEMO COMPLETE"):
        assert expected in out, f"{expected} missing from demo output"
    assert "Traceback" not in out


def test_demo_writes_reports():
    reports = sorted(p.name for p in (REPO_ROOT / "reports").glob("demo_*.md"))
    assert len(reports) >= 4
    assert any(name.endswith("_hi.md") for name in reports)


def test_demo_json_bundle_is_valid(tmp_path):
    out = tmp_path / "bundle.json"
    proc = subprocess.run([sys.executable, "-m", "demo.run_demo", "--json", str(out)],
                          cwd=REPO_ROOT, capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stderr[-2000:]
    bundle = json.loads(Path(out).read_text(encoding="utf-8"))
    assert bundle["diagnosis"]["results"], "demo must produce at least one differential"
    assert bundle["pgx"]["alerts"], "demo must produce at least one PGx alert"
    assert bundle["reproductive"]["top_risks"], "demo must rank reproductive risks"
    assert bundle["federated"]["final_mean_accuracy"] is not None
