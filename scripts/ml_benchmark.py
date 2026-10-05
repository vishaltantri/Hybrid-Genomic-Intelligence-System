"""Phase 19: measure the ML components on the data that exists in the repo and write the model registry + benchmark report.

Run: GENOMIND_EMBED_MODEL=none python -m scripts.ml_benchmark
Outputs: models/registry.json, docs/ML_BENCHMARK.md. Every number below is measured by this script; nothing is hard-coded.
Evaluations that cannot be done honestly are recorded as "not evaluated" with the reason.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from backend.app.services import registry as svc
from ml_services.config import MODELS_DIR, SEEDS_DIR
from ml_services.graph_ai.gnn_diagnosis import DifferentialDiagnosisEngine

ROOT = Path(__file__).resolve().parents[1]


def jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def rank_metrics(engine, cases, ks=(1, 3, 5, 10)):
    hits = {k: 0 for k in ks}
    rr = 0.0
    n = 0
    for c in cases:
        res = engine.diagnose(c["hpo"], patient_context=c, top_k=max(ks), explain=False, uncertainty=False)
        ids = [d.get("disease_id") for d in res.get("results", [])]
        gold = engine.baseline.canonical_id(c["confirmed_diagnosis"])
        n += 1
        if gold in ids:
            r = ids.index(gold) + 1
            rr += 1 / r
            for k in ks:
                hits[k] += r <= k
    return {"n_cases": n, **{f"hits@{k}": round(hits[k] / n, 4) for k in ks}, "mrr": round(rr / n, 4)}


def fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def main() -> dict:
    out: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "components": {}}
    syn, seed = jsonl(SEEDS_DIR / "synthetic_cases.jsonl"), jsonl(SEEDS_DIR / "seed_cases.jsonl")

    # ---- differential diagnosis (default deterministic path, GNN off) ---------------------------------------
    eng = svc.diagnosis
    import tempfile
    from ml_services.etl.generate_synthetic_cases import generate
    canon = set(eng.baseline.canonical_diseases())
    evaluable = [c for c in syn if eng.baseline.canonical_id(c["confirmed_diagnosis"]) in canon]
    gen_path = Path(tempfile.mkdtemp()) / "gen.jsonl"
    generate(n=400, seed=42, out_path=gen_path)
    syn_cur = jsonl(gen_path)                       # regenerated from the CURRENT graph (seeded, circular by construction)
    t = time.perf_counter()
    syn_m, seed_m = rank_metrics(eng, syn_cur), rank_metrics(eng, seed)
    shipped_m = rank_metrics(eng, evaluable) if evaluable else "not evaluated: no shipped case matches the current graph"
    dt = time.perf_counter() - t
    # reproducibility: same inputs, two runs
    sample = syn[:50]
    run = lambda: [[d["disease_id"] for d in eng.diagnose(c["hpo"], patient_context=c, top_k=10, explain=False, uncertainty=False)["results"]] for c in sample]
    reproducible = fingerprint(run()) == fingerprint(run())
    # GNN comparison measured, NOT enabled
    gnn_state = {"checkpoint_present": (MODELS_DIR / "gnn_han.pt").exists(), "enabled_by_default": bool(getattr(eng, "use_gnn", False))}
    try:
        g = DifferentialDiagnosisEngine(svc.graph, use_gnn=True)
        if not g._maybe_load_gnn():
            gnn_state["loadable"] = False
            gnn_state["measured_when_enabled_on_synthetic"] = ("Not evaluated - the GNN could not be loaded in this environment "
                "(checkpoint present but load_han failed, e.g. torch_geometric not installed); enabling it falls back to the deterministic path, so no GNN-specific number exists.")
        else:
            gnn_state["loadable"] = True
            gnn_state["measured_when_enabled_on_synthetic"] = rank_metrics(g, syn_cur)
    except Exception as ex:  # noqa: BLE001
        gnn_state["measured_when_enabled_on_synthetic"] = f"not evaluated: {type(ex).__name__}: {ex}"
    out["components"]["diagnosis_engine"] = {
        "default_config": {"use_gnn": gnn_state["enabled_by_default"]},
        "synthetic_400": syn_m, "curated_seed_12": seed_m, "eval_seconds": round(dt, 2),
        "shipped_synthetic_file": {"cases": len(syn), "gold_disease_present_in_current_graph": len(evaluable), "metrics_on_those": shipped_m,
                                   "note": "data/seeds/synthetic_cases.jsonl was generated against a larger graph; most of its diseases and phenotypes do not exist in the current graph, so it cannot be used to score it."},
        "reproducible_two_runs": reproducible, "gnn": gnn_state,
        "caveats": [
            "synthetic_400 is regenerated from the current graph (seed 42) using the same disease annotations the scorer uses: circular, an upper bound, not clinical accuracy.",
            "The documented 'hits@5 0.92 on 400 cases' (docs/TRAINING_RECIPES.md) was measured on a larger graph and cannot be reproduced on this checkout's graph (see shipped_synthetic_file).",
            "curated_seed_12 has 12 cases: far too few for confidence intervals; indicative only.",
            "No real patient outcome data exists: real-world accuracy is NOT evaluated.",
        ],
    }

    # ---- HPO mapper: map each curated HPO label back to its id ----------------------------------------------
    pairs = [(n, h) for c in seed for n, h in zip(c.get("hpo_names", []), c["hpo"])]
    top1 = top5 = 0
    for name, hid in pairs:
        r = svc.hpo_mapper.map_phrase(name, top_k=5)
        ids = [x.get("hpo_id") for x in r]
        top1 += bool(ids) and ids[0] == hid
        top5 += hid in ids
    out["components"]["hpo_mapper"] = {
        "n_phrases": len(pairs), "top1": round(top1 / len(pairs), 4) if pairs else None, "top5": round(top5 / len(pairs), 4) if pairs else None,
        "embedding_rerank_active": bool(getattr(svc.hpo_mapper, "_embedder", None)),
        "caveats": ["Phrases are exact HPO labels from the seed cases: this measures lookup of canonical names, not free-text or Hinglish robustness."],
    }

    # ---- NER: symptom-span recall/precision on the hand-labelled seed ---------------------------------------
    ner = svc.ner
    tp = fp = fn = 0
    for ex in jsonl(SEEDS_DIR / "clinical_ner_seed.jsonl"):
        gold = {(e["start"], e["end"]) for e in ex["entities"] if e["label"] == "SYMPTOM"}
        pred = {(e["start"], e["end"]) for e in ner.extract(ex["text"])["entities"] if e["label"] == "SYMPTOM"}
        tp += len(gold & pred); fp += len(pred - gold); fn += len(gold - pred)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    seed_texts = {e["text"] for e in jsonl(SEEDS_DIR / "clinical_ner_seed.jsonl")}
    aug_texts = {e["text"] for e in jsonl(SEEDS_DIR / "clinical_ner_augmented.jsonl")}
    out["components"]["clinical_ner"] = {
        "backend": type(ner).__name__, "label": "SYMPTOM exact-span match", "n_sentences": len(seed_texts),
        "precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
        "seed_aug_text_overlap": len(seed_texts & aug_texts),
        "caveats": ["The seed set is also the lexicon/training source: this is NOT a held-out evaluation and overstates generalisation.",
                    "MuRIL checkpoint present: " + str((MODELS_DIR / "clinical_ner_muril" / "config.json").exists())],
    }

    # ---- variant prioritisation: demo trio smoke + determinism ----------------------------------------------
    vcf = (SEEDS_DIR / "clinical_sample_trio.vcf").read_text(encoding="utf-8")
    a1 = svc.variants.analyze_vcf(vcf, filename="bench.vcf", created_by="benchmark")
    a2 = svc.variants.analyze_vcf(vcf, filename="bench.vcf", created_by="benchmark")
    key = lambda a: [(v["variant_id"], v["acmg_classification"], v["priority_tier"]) for v in a["variants"]]
    top_genes = [v["gene_symbol"] for v in a1["variants"][:5]]
    expected = {"ATP7B", "HBB", "BRCA1"}
    out["components"]["variant_prioritization"] = {
        "n_variants": len(a1["variants"]), "top5_genes": top_genes,
        "expected_genes_in_top5": sorted(expected & set(top_genes)), "deterministic_two_runs": key(a1) == key(a2),
        "caveats": ["One verified trio (n=1): a smoke test and determinism check, NOT an accuracy estimate. Sensitivity/specificity: not evaluated - no labelled variant benchmark."],
    }

    # ---- components that cannot be benchmarked honestly -----------------------------------------------------
    for cid, why in {
        "digital_twin": "Rule/derivation based; scenario outputs are recomputations of the diagnosis and variant engines. No outcome ground truth: not evaluated.",
        "reproductive_risk": "Deterministic Mendelian/Bayesian arithmetic validated by unit tests against known ratios; no outcome data: not evaluated.",
        "pharmacogenomics": "CPIC rule lookup (deterministic); concordance with a lab gold standard unavailable: not evaluated.",
        "hpo_embeddings": f"Optional sentence embedding re-ranker; disabled in this run (GENOMIND_EMBED_MODEL=none), so not evaluated.",
        "kg_models": "Knowledge-graph build is ETL, not a trained model; graph size reported by /platform/status.",
    }.items():
        out["components"][cid] = {"evaluation": "Not evaluated - ground truth unavailable", "reason": why}
    out["graph"] = {"nodes": len(svc.graph.nodes), "edges": len(svc.graph.edges)}
    return out


def write_outputs(res: dict) -> None:
    c = res["components"]
    d = c["diagnosis_engine"]
    registry = {"generated_utc": res["generated_utc"], "models": [
        {"id": "diagnosis_engine", "version": "resnik-bayes-deterministic", "status": "active", "default_on": True, "metrics": {"synthetic_400": d["synthetic_400"], "curated_seed_12": d["curated_seed_12"]}, "reproducible": d["reproducible_two_runs"]},
        {"id": "gnn_han_reranker", "version": "gnn_han.pt", "status": "available_disabled", "default_on": False, "metrics": d["gnn"].get("measured_when_enabled_on_synthetic"), "note": "Disabled by default. Not evaluated here unless loadable; see benchmark.json."},
        {"id": "hpo_mapper", "version": "lexical+fuzzy", "status": "active", "default_on": True, "metrics": {k: c["hpo_mapper"][k] for k in ("n_phrases", "top1", "top5")}},
        {"id": "clinical_ner", "version": c["clinical_ner"]["backend"], "status": "active", "default_on": True, "metrics": {k: c["clinical_ner"][k] for k in ("precision", "recall", "f1")}, "note": "not held out"},
        {"id": "variant_prioritizer", "version": "acmg-composite", "status": "active", "default_on": True, "metrics": "Not evaluated - ground truth unavailable", "deterministic": c["variant_prioritization"]["deterministic_two_runs"]},
        *[{"id": k, "status": "active", "default_on": True, "metrics": "Not evaluated - ground truth unavailable"} for k in ("digital_twin", "reproductive_risk", "pharmacogenomics")],
    ]}
    (MODELS_DIR / "registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    (MODELS_DIR / "benchmark.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    g = d["gnn"].get("measured_when_enabled_on_synthetic")
    md = [f"# ML benchmark (generated {res['generated_utc']})", "",
          "Produced by `python -m scripts.ml_benchmark`. All numbers measured on repo data. Caveats matter more than the numbers.", "",
          "## Differential diagnosis (default: GNN off)", "",
          "| Set | n | hits@1 | hits@3 | hits@5 | hits@10 | MRR |", "|---|---|---|---|---|---|---|"]
    for name, m in (("synthetic regenerated from current graph (circular)", d["synthetic_400"]), ("curated seed", d["curated_seed_12"])):
        md.append(f"| {name} | {m['n_cases']} | {m['hits@1']} | {m['hits@3']} | {m['hits@5']} | {m['hits@10']} | {m['mrr']} |")
    if isinstance(g, str):
        md.append(f"| synthetic, GNN enabled | - | {g} |")
    if isinstance(g, dict):
        md.append(f"| synthetic, GNN **enabled** (not default) | {g['n_cases']} | {g['hits@1']} | {g['hits@3']} | {g['hits@5']} | {g['hits@10']} | {g['mrr']} |")
    sh = d["shipped_synthetic_file"]
    md += ["", f"Shipped `synthetic_cases.jsonl`: {sh['gold_disease_present_in_current_graph']} of {sh['cases']} cases have their gold disease in the current graph (graph: {res['graph']['nodes']} nodes). {sh['note']}"]
    md += ["", f"Reproducible across two runs: **{d['reproducible_two_runs']}**.", ""]
    md += [f"- {x}" for x in d["caveats"]]
    h, n_ = c["hpo_mapper"], c["clinical_ner"]
    md += ["", "## HPO mapper", f"top-1 {h['top1']}, top-5 {h['top5']} on {h['n_phrases']} canonical labels. " + h["caveats"][0],
           "", "## Clinical NER (SYMPTOM spans)", f"backend {n_['backend']}: precision {n_['precision']}, recall {n_['recall']}, F1 {n_['f1']} on {n_['n_sentences']} sentences. " + n_["caveats"][0],
           "", "## Variant prioritisation", f"{c['variant_prioritization']['caveats'][0]} Top-5 genes: {', '.join(c['variant_prioritization']['top5_genes'])}; deterministic: {c['variant_prioritization']['deterministic_two_runs']}.",
           "", "## Not evaluated (no ground truth)"]
    md += [f"- **{k}**: {v['reason']}" for k, v in c.items() if isinstance(v, dict) and v.get("evaluation")]
    (ROOT / "docs" / "ML_BENCHMARK.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    r = main()
    write_outputs(r)
    print(json.dumps({k: v for k, v in r["components"].items() if k in ("diagnosis_engine", "hpo_mapper", "clinical_ner", "variant_prioritization")}, indent=1, default=str)[:4000])
