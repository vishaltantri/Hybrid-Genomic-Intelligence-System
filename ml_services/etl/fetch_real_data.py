"""Download the real, openly licensed datasets the pipeline is built to consume.

Every parser in ``ml_services.etl`` prefers ``data/raw/<source>/`` and falls back to
the hand-built mini seeds. Running this script replaces the seeds with the genuine
upstream files, so the knowledge graph is built from real data.

Sources and licences
--------------------
HPO (hp.obo, phenotype.hpoa)      open, attribution requested       -> data/raw/hpo/
Orphanet Orphadata (XML/CSV)      free registration, CC-BY-4.0      -> data/raw/orphanet/
ClinVar (variant_summary.txt.gz)  public domain (NCBI)              -> data/raw/clinvar/
PharmGKB clinical annotations     CC-BY-SA-4.0 (registration)       -> data/raw/pharmgkb/
CPIC guideline tables             CC0 / free                        -> data/raw/cpic/
gnomAD v4 South Asian AFs         open                              -> data/raw/gnomad/
IndicVoices / Common Voice (ASR)  CC-by / CC0                       -> data/raw/speech/
MedDRA-free resources only: this script never fetches anything requiring a
click-through licence it cannot accept on your behalf. Files marked ``manual``
print instructions instead, so licensing stays an explicit human decision.

Usage:
    python -m ml_services.etl.fetch_real_data --list
    python -m ml_services.etl.fetch_real_data hpo clinvar cpic
    python -m ml_services.etl.fetch_real_data --all --include-manual
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from ml_services.config import RAW_DIR

UA = {"User-Agent": "GENOMIND-INDIA/0.1 (research prototype; contact: local)"}

SOURCES: dict[str, dict] = {
    # ---------------------------------------------------------------- Module 2/4
    "hpo": {
        "dir": "hpo",
        "licence": "HPO licence - free use, attribution requested",
        "files": [
            ("hp.obo", "https://purl.obolibrary.org/obo/hp.obo"),
            ("hp.json", "https://purl.obolibrary.org/obo/hp.json"),
            ("phenotype.hpoa", "https://purl.obolibrary.org/obo/hp/hpoa/phenotype.hpoa"),
            ("genes_to_phenotype.txt",
             "https://purl.obolibrary.org/obo/hp/hpoa/genes_to_phenotype.txt"),
        ],
    },
    # ---------------------------------------------------------------- Module 3/6
    "orphanet": {
        "dir": "orphanet",
        "licence": "Orphadata - free for academic use, CC-BY-4.0",
        "manual": ("Orphadata requires accepting terms at https://www.orphadata.com/ "
                   "then downloading the XML/CSV packs into data/raw/orphanet/. "
                   "Files expected: en_product4 (disease-phenotype), en_product6 "
                   "(disease-gene), en_product9 (epidemiology)."),
        "files": [],
    },
    # ------------------------------------------------------------------ Module 5
    "clinvar": {
        "dir": "clinvar",
        "licence": "NCBI public domain",
        "files": [
            ("variant_summary.txt.gz",
             "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"),
            ("gene_specific_summary.txt.gz",
             "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/gene_specific_summary.txt.gz"),
        ],
    },
    "pharmgkb": {
        "dir": "pharmgkb",
        "licence": "PharmGKB / ClinPGx - CC-BY-SA-4.0, registration required for bulk files",
        "manual": ("PharmGKB bulk downloads need a free account and forbids redistribution of "
                   "the raw files. Download 'clinicalAnnotations.zip', 'relationships.zip' and "
                   "'drugs.tsv' from https://www.pharmgkb.org/downloads into data/raw/pharmgkb/. "
                   "DGIdb's interaction TSV (https://dgidb.org/downloads) is CC0 and can be "
                   "fetched directly with: --only dgidb"),
        "files": [],
    },
    "dgidb": {
        "dir": "pharmgkb",
        "licence": "DGIdb - CC0 / open",
        "files": [
            ("dgidb_interactions.tsv",
             "https://www.dgidb.org/data/latest/interactions.tsv"),
        ],
    },
    "cpic": {
        "dir": "cpic",
        "licence": "CPIC - CC0 / free",
        "files": [
            ("cpic_gene_drug_pairs.tsv",
             "https://api.cpicpgx.org/v1/gene_drug_pair?select=*"),
            ("cpic_recommendations.tsv",
             "https://api.cpicpgx.org/v1/recommendation?select=*"),
            ("cpic_allele_frequency.tsv",
             "https://api.cpicpgx.org/v1/allele_frequency?select=*"),
        ],
        "accept": "application/json",
    },
    # ---------------------------------------------------------------- Module 5/6
    "gnomad": {
        "dir": "gnomad",
        "licence": "gnomAD - open (CC0 for aggregate frequencies)",
        "manual": ("gnomAD v4 South Asian allele frequencies: use the download portal at "
                   "https://gnomad.broadinstitute.org/downloads with the 'South Asian (sas)' "
                   "population selected, or query the GraphQL API. This is the substitute for "
                   "GenomeAsia-100K, which requires a data-access application."),
        "files": [],
    },
    "indigenomes": {
        "dir": "indigenomes",
        "licence": "IndiGenomes (IGIB) - data access request / browse via UCSC track",
        "manual": ("IndiGenomes / GenomeIndia allele frequencies are data-access gated. "
                   "Browsable frequencies: https://clingen.igib.res.in/indigen and the "
                   "GenomeIndia UCSC track. Apply via the GenomeIndia data access committee. "
                   "Until then, data/seeds/indian_af.csv (literature-derived) is used and "
                   "clearly labelled as an estimate."),
        "files": [],
    },
    # ------------------------------------------------------------------ Module 9
    "speech": {
        "dir": "speech",
        "licence": "Common Voice CC0 / IndicVoices CC-BY-4.0",
        "manual": ("ASR corpora are large - download deliberately:\n"
                   "  Common Voice  -> https://commonvoice.mozilla.org/en/datasets (hi, ta, te, bn, mr, pa)\n"
                   "  IndicVoices   -> https://huggingface.co/datasets/ai4bharat/IndicVoices\n"
                   "  OpenSLR       -> https://openslr.org/resources.php (Indic ASR resources)\n"
                   "Place a single-language tarball under data/raw/speech/<lang>/."),
        "files": [],
    },
    # ---------------------------------------------------------------- Module 1
    "nlp": {
        "dir": "nlp",
        "licence": "varies per corpus - check each before redistributing",
        "manual": ("Code-mixed clinical NLP corpora and their licences:\n"
                   "  GLUECoS (Hi-En LID/POS/NER)     -> https://microsoft.github.io/GLUECoS/\n"
                   "  COMI-LINGUA (125k+ Hi-En)       -> HuggingFace (search COMI-LINGUA)\n"
                   "  Naamapadam (11 Indic NER)       -> https://huggingface.co/datasets/ai4bharat/naamapadam\n"
                   "  HiNER (Hindi NER)               -> https://github.com/cfiltnlp/HiNER\n"
                   "  L3Cube HingCorpus (pretraining) -> https://github.com/l3cube-pune/code-mixed-nlp\n"
                   "Convert each to JSONL with {id, text, entities:[{start,end,label}]} and place\n"
                   "under data/raw/nlp/<corpus>/. Also add your own hand-labelled Hinglish\n"
                   "clinical sentences: that seed set is a first-class project contribution."),
        "files": [],
    },
    # --------------------------------------------------------------- Module 11
    "nfhs": {
        "dir": "nfhs",
        "licence": "DHS / NFHS - registration required for microdata",
        "manual": ("NFHS-5 state-level indicators (consanguinity, screening coverage): register at "
                   "https://www.dhsprogram.com/data/ and download the NFHS-5 (IAIR/IR) files. "
                   "data/seeds/nfhs5_consanguinity.csv holds the published state rates used now."),
        "files": [],
    },
}


def _download(url: str, dest: Path, accept: str | None = None) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        return {"url": url, "ok": False, "error": str(exc)}
    if url.endswith(".gz") and not raw[:2] == b"\x1f\x8b":
        return {"url": url, "ok": False, "error": "expected gzip payload"}
    dest.write_bytes(raw)
    return {"url": url, "ok": True, "path": str(dest), "bytes": len(raw)}


def fetch(name: str, include_manual: bool = False, verify: bool = True) -> dict:
    src = SOURCES[name]
    out_dir = RAW_DIR / src["dir"]
    results: list[dict] = []
    manifest = out_dir / "SOURCE.json"

    if src.get("manual"):
        print(f"\n[{name}] manual source - {src['licence']}")
        if include_manual:
            print(src["manual"])
        if not src["files"]:
            out_dir.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps(
                {"source": name, "licence": src["licence"], "instructions": src["manual"],
                 "status": "manual_download_required"}, indent=2), encoding="utf-8")
            return {"source": name, "status": "manual", "files": []}

    for fname, url in src["files"]:
        dest = out_dir / fname
        res = _download(url, dest, src.get("accept"))
        results.append({"file": fname, **res})
        flag = "ok " if res["ok"] else "FAIL"
        detail = f"{res.get('bytes', 0) / 1e6:.1f} MB" if res["ok"] else res.get("error", "")
        print(f"  [{flag}] {fname:<32} {detail}")

    ok = [r for r in results if r["ok"]]
    if verify and ok:
        _verify(name, out_dir, results)

    manifest.write_text(json.dumps(
        {"source": name, "licence": src["licence"], "fetched": results,
         "n_ok": len(ok), "n_failed": len(results) - len(ok)}, indent=2), encoding="utf-8")
    return {"source": name, "status": "ok" if len(ok) == len(results) else "partial",
            "files": results}


def _verify(name: str, out_dir: Path, results: list[dict]) -> None:
    """Cheap sanity check that the payload is the real thing, not an HTML error page."""
    checks = {
        "hp.obo": lambda p: b"[Term]" in p.read_bytes()[:200000],
        "phenotype.hpoa": lambda p: b"database_id" in p.read_bytes()[:5000].lower(),
        "variant_summary.txt.gz": lambda p: len(gzip.decompress(p.read_bytes()[:100000])) > 0,
        "dgidb_interactions.tsv": lambda p: b"\t" in p.read_bytes()[:5000],
        "cpic_gene_drug_pairs.tsv": lambda p: p.read_bytes().lstrip().startswith(b"["),
    }
    for r in results:
        if not r["ok"]:
            continue
        path = Path(r["path"])
        check = checks.get(path.name)
        if check is None:
            continue
        try:
            good = check(path)
        except Exception:
            good = False
        r["verified"] = bool(good)
        if not good:
            print(f"  [WARN] {path.name} does not look like the expected payload "
                  f"- inspect {path}")


def list_sources() -> None:
    print(f"{'name':<13} {'licence':<52} {'kind'}")
    print("-" * 88)
    for name, src in SOURCES.items():
        kind = "auto-download" if src["files"] else "manual (licence/registration)"
        print(f"{name:<13} {src['licence'][:50]:<52} {kind}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="*", help="source names, or --all")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--include-manual", action="store_true",
                    help="also print instructions for gated sources")
    args = ap.parse_args()

    if args.list or (not args.sources and not args.all):
        list_sources()
        return

    names = list(SOURCES) if args.all else args.sources
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        sys.exit(f"unknown source(s): {unknown}. Known: {list(SOURCES)}")

    print(f"Fetching {len(names)} source(s) into {RAW_DIR}")
    summary = [fetch(n, include_manual=args.include_manual) for n in names]
    print("\nSummary:")
    for s in summary:
        print(f"  {s['source']:<13} {s['status']}")
    print("\nNext: python -m ml_services.etl.kg_build   # rebuilds the KG from real files")


if __name__ == "__main__":
    main()
