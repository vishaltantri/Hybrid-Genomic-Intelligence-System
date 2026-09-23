"""HPO ontology + phenotype.hpoa parser (Module 2/3 data spine).

Production: download hp.obo and phenotype.hpoa into data/raw/hpo/.
Falls back to data/seeds/hp_mini.obo + phenotype_hpoa_mini.tsv.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from ml_services.config import PROCESSED_DIR, RAW_DIR, SEEDS_DIR
from ml_services.utils import read_csv_rows

OBO_PATHS = [RAW_DIR / "hpo" / "hp.obo", SEEDS_DIR / "hp_mini.obo"]
HPOA_PATHS = [RAW_DIR / "hpo" / "phenotype.hpoa", SEEDS_DIR / "phenotype_hpoa_mini.tsv"]


def _first_existing(paths):
    for p in paths:
        if p.exists():
            return p
    raise FileNotFoundError(f"None of these exist: {paths}")


def parse_obo(path) -> List[dict]:
    """Parse OBO format into HPO term node dicts."""
    terms: List[dict] = []
    cur: Dict[str, object] | None = None
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line == "[Term]":
                if cur:
                    terms.append(cur)
                cur = {"id": "", "name": "", "def": "", "is_a": [], "synonyms": []}
                continue
            if line.startswith("[") and line.endswith("]") and cur is not None:
                # [Typedef] etc: flush current term only on next [Term]; skip other stanzas
                if not line.startswith("[Term]"):
                    if cur and cur.get("id"):
                        terms.append(cur)
                    cur = None
                continue
            if cur is None or not line:
                continue
            if ": " not in line:
                continue
            key, _, value = line.partition(": ")
            if key == "id":
                cur["id"] = value.strip()
            elif key == "name":
                cur["name"] = value.strip()
            elif key == "def":
                cur["def"] = value.split('"')[1] if '"' in value else value
            elif key == "is_a":
                cur["is_a"].append(value.split("{")[0].split("!")[0].strip())  # strip {xref=...} qualifier blocks
            elif key == "synonym":
                syn = value.split('"')[1] if '"' in value else value
                cur["synonyms"].append(syn)
    if cur and cur.get("id"):
        terms.append(cur)
    return [t for t in terms if t.get("id")]


def parse_hpoa(path) -> List[dict]:
    """Parse phenotype.hpoa TSV -> disease-HPO annotation rows (skipping comments/headers)."""
    rows: List[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip() and not ln.startswith("#")]
    if not lines:
        return rows
    header = lines[0].split("\t")
    for ln in lines[1:]:
        parts = ln.split("\t")
        row = dict(zip(header, parts))
        rows.append(
            {
                "disease_id": row.get("disease_id") or row.get("database_id", ""),
                "disease_name": row.get("disease_name", ""),
                "hpo_id": row.get("hpo_id", ""),
                "hpo_name": row.get("hpo_name", ""),
                "frequency": row.get("frequency", ""),
                "evidence": row.get("evidence", ""),
                "aspect": row.get("aspect", ""),
            }
        )
    return rows


def run() -> dict:
    obo_path = _first_existing(OBO_PATHS)
    hpoa_path = _first_existing(HPOA_PATHS)
    terms = parse_obo(obo_path)
    hpoa = parse_hpoa(hpoa_path)

    hpo_nodes = [
        {"id": t["id"], "type": "Hpo", "name": t["name"], "definition": t.get("def", ""), "synonyms": t.get("synonyms", [])}
        for t in terms
    ]
    parent_edges = [
        {"src": t["id"], "dst": parent, "type": "IS_A", "attrs": {}} for t in terms for parent in t.get("is_a", []) if parent
    ]
    disease_edges = [
        {
            "src": r["disease_id"],
            "dst": r["hpo_id"],
            "type": "HAS_PHENOTYPE",
            "attrs": {"frequency": r["frequency"], "evidence": r["evidence"], "hpo_name": r["hpo_name"]},
        }
        for r in hpoa
        if r["hpo_id"]
    ]
    # Ensure disease nodes referenced by hpoa exist even if orphanet file lacks them
    disease_nodes = [
        {"id": d, "type": "Disease", "name": n, "source": "hpoa"}
        for d, n in {r["disease_id"]: r["disease_name"] for r in hpoa if r["disease_id"]}.items()
    ]
    out = {"hpo_nodes": hpo_nodes, "parent_edges": parent_edges, "disease_nodes": disease_nodes, "disease_edges": disease_edges}
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    return out


if __name__ == "__main__":
    result = run()
    print(f"HPO terms: {len(result['hpo_nodes'])}, hpoa annotations: {len(result['disease_edges'])}")
