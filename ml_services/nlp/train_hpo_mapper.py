"""Fine-tune the HPO phenotype-mapper bi-encoder — Module 2 (patent claim #2).

    .venv/bin/python -m ml_services.nlp.train_hpo_mapper               # train + eval
    .venv/bin/python -m ml_services.nlp.train_hpo_mapper --epochs 5

Training pairs (positives for MultipleNegativesRankingLoss):
  1. Real-ontology self-supervision: every HPO term's official synonyms paired with
     its name (hp.obo carries ~60k such pairs; we cap for the 6GB GPU budget).
  2. Indian synonym dictionary: colloquial phrase -> HPO term (data/seeds/indian_synonyms.csv).
  3. Lexicon-confirmed symptom spans from the seed NER sentences.

Holdout evaluation: unseen synonym pairs must retrieve the right term among ALL
20k+ ontology terms (Recall@1 / Recall@5 / MRR) — the same metric the clinical
mapper is judged on.

Output: models/hpo_biencoder/ — HPOMapper picks it up automatically, falling back
to the raw multilingual-e5-base when absent. Inference switches to a FAISS index
over all terms when faiss-cpu is installed (linear scan otherwise).
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List, Tuple

from ml_services.config import MODELS_DIR, SEEDS_DIR
from ml_services.etl.graph_store import load_processed

BASE_MODEL = "intfloat/multilingual-e5-base"
DEFAULT_OUT = MODELS_DIR / "hpo_biencoder"
MAX_ONTOLOGY_PAIRS = 40000


# ------------------------------- data -------------------------------

def _term_text(node: dict) -> str:
    syn = "; ".join((node.get("synonyms") or [])[:3])
    return f"{node['name']}. {node.get('definition', '')} {syn}".strip()


def build_pairs(graph=None, max_ontology_pairs: int = MAX_ONTOLOGY_PAIRS) -> List[Tuple[str, str]]:
    """(mention text, HPO term text) positive pairs from all available sources."""
    graph = graph or load_processed()
    pairs: List[Tuple[str, str]] = []

    terms = {n["id"]: n for n in graph.by_type("Hpo")} if graph else {}
    term_text = {tid: _term_text(n) for tid, n in terms.items()}

    # 1) ontology self-supervision: official synonym -> term
    onto: List[Tuple[str, str]] = []
    for n in terms.values():
        for s in n.get("synonyms") or []:
            s = s.strip()
            if len(s) >= 3 and s.lower() != n["name"].lower():
                onto.append((s, n["name"]))
    random.shuffle(onto)
    pairs.extend(onto[:max_ontology_pairs])

    # 2) Indian colloquial synonyms
    from ml_services.utils import read_csv_rows

    syn_path = SEEDS_DIR / "indian_synonyms.csv"
    for r in read_csv_rows(syn_path):
        phrase, tid = (r.get("phrase") or "").strip(), r.get("hpo_id", "")
        if phrase and tid in term_text:
            pairs.append((phrase, terms[tid]["name"]))

    # 3) lexicon-confirmed spans in the seed sentences
    from ml_services.utils import read_jsonl

    for row in read_jsonl(SEEDS_DIR / "clinical_ner_seed.jsonl"):
        for ent in row.get("entities", []):
            tid = ent.get("hpo_id") or ""
            if not tid and ent.get("label") == "SYMPTOM":
                continue
            if tid in term_text:
                pairs.append((row["text"][ent["start"]:ent["end"]], terms[tid]["name"]))

    # dedupe
    seen, out = set(), []
    for mention, term in pairs:
        key = (mention.lower(), term.lower())
        if key in seen or not mention or not term:
            continue
        seen.add(key)
        out.append((mention, term))
    return out


# ------------------------------- training -------------------------------

def train(out_dir: Path = DEFAULT_OUT, base_model: str = BASE_MODEL, epochs: int = 3,
          batch_size: int = 8, seed: int = 13, holdout: int = 300) -> dict:
    import numpy as np
    import torch
    from sentence_transformers import InputExample, SentenceTransformer, losses
    from torch.utils.data import DataLoader

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    pairs = build_pairs()
    if len(pairs) < 50:
        raise SystemExit("Not enough training pairs — is the KG built?")
    random.shuffle(pairs)
    test_pairs, train_pairs = pairs[:holdout], pairs[holdout:]

    # Low-VRAM recipe: frozen e5 encoder + trainable Dense projection (768->768).
    # Full fine-tune does not fit a 6GB card (AdamW states alone are ~1.7GB), and
    # e5's mean-pooling head has no parameters of its own — so the projection head
    # is the trainable part. Native ST modules: saves/loads with model.save().
    from sentence_transformers import models

    word = models.Transformer(base_model, max_seq_length=96)
    pooling = models.Pooling(word.get_word_embedding_dimension(), pooling_mode="mean")
    dense = models.Dense(in_features=word.get_word_embedding_dimension(),
                         out_features=word.get_word_embedding_dimension(),
                         activation_function=torch.nn.Tanh())
    for p in word.auto_model.parameters():
        p.requires_grad = False
    model = SentenceTransformer(modules=[word, pooling, dense])

    def _fit(loader, loss, epochs: int):
        """sentence-transformers >= 5 removed the .fit shim; fall back to the Trainer API."""
        warmup = int(len(loader) * epochs * 0.1)
        try:
            model.fit(train_objectives=[(loader, loss)], epochs=epochs,
                      warmup_steps=warmup, show_progress_bar=False)
        except (AttributeError, TypeError):
            from datasets import Dataset as HFDataset
            from sentence_transformers import SentenceTransformerTrainer
            from sentence_transformers.training_args import SentenceTransformerTrainingArguments

            ds = HFDataset.from_list([{"anchor": a, "positive": p} for a, p in
                                      (e.texts for e in loader.dataset)])
            st_args = SentenceTransformerTrainingArguments(
                output_dir=str(MODELS_DIR / "hpo_biencoder_trainer"),
                per_device_train_batch_size=batch_size,
                gradient_accumulation_steps=max(1, 32 // batch_size),
                num_train_epochs=epochs,
                warmup_ratio=0.1, fp16=bool(torch.cuda.is_available()),
                gradient_checkpointing=True,  # 6GB VRAM: activations don't fit unclipped
                report_to=[], seed=seed, save_strategy="no", logging_steps=50,
            )
            st_trainer = SentenceTransformerTrainer(model=model, train_dataset=ds,
                                                    loss=loss, args=st_args)
            st_trainer.train()

    loader = DataLoader(
        [InputExample(texts=[m, t]) for m, t in train_pairs],
        batch_size=batch_size, shuffle=True,
    )
    loss = losses.MultipleNegativesRankingLoss(model)
    _fit(loader, loss, epochs)

    # -------- retrieval evaluation over ALL ontology terms --------
    graph = load_processed()
    terms = {n["id"]: n for n in graph.by_type("Hpo")}
    ids = list(terms)
    corpus = [_term_text(terms[i]) for i in ids]

    # tag the holdout terms with their CORPUS POSITION for honest in-corpus eval
    # (ids are HPO-ID strings; the similarity matrix is indexed by position)
    id_pos = {tid: k for k, tid in enumerate(ids)}
    name_to_idx = {terms[tid]["name"].lower(): id_pos[tid] for tid in ids}
    eval_mentions, eval_gold = [], []
    for mention, term_name in test_pairs:
        idx = name_to_idx.get(term_name.lower())
        if idx is not None:
            eval_mentions.append(mention)
            eval_gold.append(idx)

    # free training memory before the big encode; fall back to CPU if the GPU is tight
    import torch as _t

    if _t.cuda.is_available():
        _t.cuda.empty_cache()
    enc_kwargs = {"normalize_embeddings": True, "show_progress_bar": False, "batch_size": 64}
    try:
        corpus_emb = model.encode([f"passage: {c}" for c in corpus] if "e5" in base_model else corpus,
                                  **enc_kwargs)
        mention_emb = model.encode([f"query: {m}" for m in eval_mentions] if "e5" in base_model else eval_mentions,
                                   **enc_kwargs)
    except Exception:
        model = model.to("cpu")
        _t.cuda.empty_cache()
        corpus_emb = model.encode([f"passage: {c}" for c in corpus] if "e5" in base_model else corpus,
                                  **enc_kwargs)
        mention_emb = model.encode([f"query: {m}" for m in eval_mentions] if "e5" in base_model else eval_mentions,
                                   **enc_kwargs)

    # save FIRST so a crash in evaluation never loses the trained checkpoint
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save(str(out_dir))

    print(f"eval: {len(eval_mentions)} mentions / {len(eval_gold)} gold / corpus {len(ids)}")
    if not eval_gold:
        metrics = {"base_model": base_model, "train_pairs": len(train_pairs),
                   "eval_pairs": 0, "corpus_terms": len(ids),
                   "note": "no resolvable holdout pairs — eval skipped",
                   "device": "cuda" if torch.cuda.is_available() else "cpu"}
    else:
        hits1 = hits5 = 0
        rr_sum = 0.0
        sims = mention_emb @ corpus_emb.T
        for row, gold in zip(sims, eval_gold):
            order = np.argsort(-row)
            rank = int(np.where(order == gold)[0][0])
            hits1 += rank == 0
            hits5 += rank < 5
            rr_sum += 1.0 / (rank + 1)
        n = len(eval_gold)
        metrics = {
            "base_model": base_model, "train_pairs": len(train_pairs), "eval_pairs": n,
            "corpus_terms": len(ids), "recall_at_1": round(hits1 / n, 3),
            "recall_at_5": round(hits5 / n, 3), "mrr": round(rr_sum / n, 3),
            "device": "cuda" if torch.cuda.is_available() else "cpu",
        }
    with open(out_dir / "train_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=1)
    return metrics


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--base", default=BASE_MODEL)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=8)
    args = ap.parse_args()
    try:
        metrics = train(out_dir=Path(args.out), base_model=args.base,
                        epochs=args.epochs, batch_size=args.batch_size)
    except ImportError as exc:
        print(f"Training needs torch + sentence-transformers ({exc}).")
        print("  pip install torch sentence-transformers")
        return 1
    print("HPO mapper training complete:")
    for k, v in metrics.items():
        print(f"  {k:14s} {v}")
    print("HPOMapper will load this checkpoint automatically (falls back to e5-base).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
