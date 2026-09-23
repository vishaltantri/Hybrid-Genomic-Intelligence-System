"""Small IO + math helpers shared across all modules."""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List


def read_jsonl(path: str | Path) -> List[dict]:
    rows: List[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, obj: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def read_csv_rows(path: str | Path) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_rows(path: str | Path, rows: List[Dict[str, Any]], fieldnames: List[str] | None = None) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: Dict[str, None] = {}
        for r in rows:
            for k in r:
                keys.setdefault(k, None)
        fieldnames = list(keys)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def softmax(xs: List[float]) -> List[float]:
    if not xs:
        return []
    m = max(xs)
    exps = [math.exp(x - m) for x in xs]
    s = sum(exps) or 1.0
    return [e / s for e in exps]


_WORD_RE = re.compile(r"[A-Za-z]+")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")
_TELUGU_RE = re.compile(r"[\u0C00-\u0C7F]")

# Romanised Hindi/Hinglish tokens that appear in real Indian clinical notes but are written
# in Latin script. Detecting these is the core of the token-level LID patent claim: without
# it, every Hinglish note looks like English and code-mixing goes unnoticed.
ROMANIZED_HINDI_TOKENS = {
    "hai", "hain", "ho", "hua", "hui", "hoga", "hota", "hoti", "ho", "raha", "rahi", "rahe",
    "ko", "ka", "ki", "ke", "se", "mein", "me", "par", "aur", "bhi", "nahi", "nahin", "tha",
    "thi", "the", "din", "raat", "mahina", "mahine", "hafte", "hafsa", "saal", "saalon", "sal",
    "bukhar", "khaansi", "khansi", "zukam", "dukh", "dard", "kamzori", "kamjori", "sujan",
    "piliya", "peela", "peeli", "aankh", "aankhein", "aankhon", "chehra", "pet", "sar", "sir",
    "haath", "pair", "pairon", "khoon", "daura", "jhatke", "mirgi", "bacha", "bachche", "bacche",
    "ladka", "ladki", "beta", "beti", "maa", "papa", "pitaji", "dada", "dadi", "chacha", "bua",
    "parivaar", "rishtedaar", "shadi", "dawa", "goli", "injection", "doctor", "bimar", "tabiyat",
    "bhookh", "vajan", "wajan", "thakan", "soojan", "khujli", "ulti", "dast", "peshaab", "peshab",
    "dikkat", "pareshani", "bahut", "zyada", "thoda", "kam", "accha", "theek", "jaldi", "der",
}


def token_language(token: str, extra_vocab: set[str] | None = None) -> str:
    """Token-level language ID (Module 1 patent claim).

    Returns HI/TA/TE for Indic scripts, HI-LATN for romanised Hindi/Hinglish words, and EN
    for everything else in Latin script. "HI-LATN" is what makes a typed Hinglish clinical
    note recognisably code-mixed.
    """
    if _DEVANAGARI_RE.search(token):
        return "HI"
    if _TAMIL_RE.search(token):
        return "TA"
    if _TELUGU_RE.search(token):
        return "TE"
    bare = re.sub(r"[^A-Za-z]", "", token).lower()
    if not bare:
        return "EN"
    if bare in ROMANIZED_HINDI_TOKENS or (extra_vocab and bare in extra_vocab):
        return "HI-LATN"
    return "EN"


def l2norm(v: List[float]) -> List[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return num / (da * db) if da and db else 0.0
