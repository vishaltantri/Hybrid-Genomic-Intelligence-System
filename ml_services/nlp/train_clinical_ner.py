"""Fine-tune MuRIL for code-mixed clinical NER — Module 1 (patent claim #1).

    .venv/bin/python -m ml_services.nlp.train_clinical_ner            # train + save
    .venv/bin/python -m ml_services.nlp.train_clinical_ner --epochs 60

Data: data/seeds/clinical_ner_seed.jsonl (hand-labelled Hinglish clinical sentences,
BIO-converted here from char spans). Pass --data to add larger corpora later
(e.g. the Telugu-English medical dialogs or 10k synthetic notes, converted to the
same JSONL schema {text, entities:[{start,end,label}]}).

Output: models/clinical_ner_muril/ — picked up automatically by get_ner(), so the
API, demo and ASHA pipeline switch to the trained backend with no code changes.
The lexical NER stays available as a deterministic fallback (tests use it directly).

Sized for a 6GB GPU: muril-base-cased + fp16 + batch 4 + gradient checkpointing.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List, Tuple

from ml_services.config import MODELS_DIR, SEEDS_DIR

BASE_MODEL = "google/muril-base-cased"
DEFAULT_OUT = MODELS_DIR / "clinical_ner_muril"


# ------------------------------- data -------------------------------

def char_spans_to_word_labels(text: str, entities: List[dict]) -> List[Tuple[str, str]]:
    """Convert char-span entities to per-whitespace-token labels (BIO)."""
    tokens = text.split()
    starts = []
    pos = 0
    for w in tokens:
        starts.append(pos)
        pos += len(w) + 1
    labels: List[str] = ["O"] * len(tokens)
    for ent in sorted(entities, key=lambda e: e["start"]):
        idxs = [i for i, s in enumerate(starts) if s < ent["end"] and s + len(tokens[i]) > ent["start"]]
        if not idxs:
            continue
        labels[idxs[0]] = f"B-{ent['label']}"
        for i in idxs[1:]:
            labels[i] = f"I-{ent['label']}"
    return list(zip(tokens, labels))


def load_examples(paths: List[Path]) -> List[dict]:
    rows: List[dict] = []
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                tagged = char_spans_to_word_labels(r["text"], r.get("entities", []))
                if any(lab != "O" for _, lab in tagged):
                    rows.append({"id": r.get("id", ""), "words": [w for w, _ in tagged],
                                 "labels": [l for _, l in tagged]})
    return rows


def collect_labels(examples: List[dict]) -> List[str]:
    labs = sorted({l for ex in examples for l in ex["labels"] if l != "O"})
    return ["O"] + labs


# ------------------------------- training -------------------------------

def train(data_paths: List[Path], out_dir: Path = DEFAULT_OUT, base_model: str = BASE_MODEL,
          epochs: int = 40, batch_size: int = 4, lr: float = 5e-5, seed: int = 13,
          holdout: int = 40) -> dict:
    import numpy as np
    import torch
    from torch.utils.data import Dataset
    from transformers import (AutoModelForTokenClassification, AutoTokenizer,
                              Trainer, TrainingArguments)

    from ml_services.utils import token_language

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    examples = load_examples(data_paths)
    if len(examples) < 5:
        raise SystemExit("Not enough labelled sentences to train on.")
    label_list = collect_labels(examples)
    label2id = {l: i for i, l in enumerate(label_list)}

    random.shuffle(examples)
    test, trainset = examples[:holdout], examples[holdout:]

    tokenizer = AutoTokenizer.from_pretrained(base_model)

    class NERDataset(Dataset):
        def __init__(self, rows):
            self.rows = rows

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, i):
            ex = self.rows[i]
            enc = tokenizer(ex["words"], is_split_into_words=True, truncation=True,
                            max_length=128, padding="max_length")
            word_ids = enc.word_ids(0)
            prev, labels = None, []
            for wid in word_ids:
                if wid is None:
                    labels.append(-100)
                elif wid != prev:
                    labels.append(label2id[ex["labels"][wid]])
                else:
                    lab = ex["labels"][wid]
                    labels.append(label2id.get("I" + lab[1:], label2id[lab]) if lab.startswith("B-") else label2id[lab])
                prev = wid
            enc["labels"] = labels
            return {k: torch.tensor(v) for k, v in enc.items()}

    model = AutoModelForTokenClassification.from_pretrained(base_model, num_labels=len(label_list))
    use_cuda = torch.cuda.is_available()

    args = TrainingArguments(
        output_dir=str(out_dir / "_trainer"),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        learning_rate=lr,
        weight_decay=0.01,
        logging_steps=25,
        save_strategy="no",
        fp16=use_cuda,
        gradient_checkpointing=use_cuda,
        report_to=[],
        seed=seed,
    )
    trainer = Trainer(model=model, args=args, train_dataset=NERDataset(trainset))
    trainer.train()

    # -------- span-level evaluation on the holdout --------
    model.eval()

    def predict(words: List[str]) -> List[str]:
        enc = tokenizer(words, is_split_into_words=True, return_tensors="pt", truncation=True)
        enc.to(next(model.parameters()).device)  # keeps word_ids; moves tensors
        with torch.no_grad():
            logits = model(**enc).logits[0]
        # word-indexed output: the FIRST subtoken of each word carries its label
        out = ["O"] * len(words)
        prev = None
        for i, wid in enumerate(enc.word_ids(0)):
            if wid is None or wid == prev:
                continue  # special token or continuation piece
            out[wid] = label_list[int(logits[i].argmax(-1))]
            prev = wid
        return out

    def spans(labels: List[str]) -> set:
        cur, out = None, set()
        for i, l in enumerate(labels):
            if l.startswith("B-"):
                cur = (i, l[2:])
            elif l == "O":
                if cur:
                    out.add((cur[0], i, cur[1]))
                cur = None
        if cur:
            out.add((cur[0], len(labels), cur[1]))
        return out

    tp = fp = fn = 0
    for ex in test:
        gold, pred = spans(ex["labels"]), spans(predict(ex["words"]))
        tp += len(gold & pred)
        fp += len(pred - gold)
        fn += len(gold - pred)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))
    with open(out_dir / "labels.json", "w", encoding="utf-8") as f:
        json.dump(label_list, f, indent=1)
    metrics = {
        "base_model": base_model, "train_sentences": len(trainset), "holdout": len(test),
        "labels": len(label_list), "span_precision": round(precision, 3),
        "span_recall": round(recall, 3), "span_f1": round(f1, 3),
        "device": "cuda" if use_cuda else "cpu", "checkpoint": str(out_dir),
    }
    with open(out_dir / "train_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=1)
    return metrics


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", action="append", default=[],
                    help="extra JSONL files (repeatable); seed + augmented corpus are always included")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--base", default=BASE_MODEL)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=4)
    args = ap.parse_args()

    paths = [SEEDS_DIR / "clinical_ner_seed.jsonl"]
    aug = SEEDS_DIR / "clinical_ner_augmented.jsonl"
    if aug.exists():
        paths.append(aug)
    paths += [Path(p) for p in args.data]
    try:
        metrics = train(paths, out_dir=Path(args.out), base_model=args.base,
                        epochs=args.epochs, batch_size=args.batch_size)
    except ImportError as exc:
        print(f"Training needs torch + transformers installed ({exc}).")
        print("  pip install torch transformers")
        return 1
    print("Clinical NER training complete:")
    for k, v in metrics.items():
        print(f"  {k:16s} {v}")
    print("get_ner() will now load this checkpoint automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
