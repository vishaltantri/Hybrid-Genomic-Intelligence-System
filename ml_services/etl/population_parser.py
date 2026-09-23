"""India-specific population data parser (Modules 3/5/6/9/11).

Sources (production): IndiGenomes clingen.igib.res.in/indigen, GenomeIndia allele-frequency
supplements, gnomAD v4 South Asian subset, NFHS-5 fact sheets, NABL lab directory,
Datameet GeoJSON for maps. Seeds live in data/seeds/.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ml_services.config import RAW_DIR, SEEDS_DIR
from ml_services.utils import read_csv_rows

AF_PATHS = [RAW_DIR / "indian_af" / "indian_af.csv", SEEDS_DIR / "indian_af.csv"]
COMMUNITY_PATHS = [RAW_DIR / "population" / "communities.csv", SEEDS_DIR / "indian_communities.csv"]
NFHS_PATHS = [RAW_DIR / "nfhs" / "consanguinity.csv", SEEDS_DIR / "nfhs5_consanguinity.csv"]
LABS_PATHS = [RAW_DIR / "labs" / "nabl_labs.csv", SEEDS_DIR / "nabl_labs.csv"]
SPECIALISTS_PATHS = [RAW_DIR / "specialists" / "specialists.csv", SEEDS_DIR / "specialists.csv"]
ASHA_PATHS = [RAW_DIR / "asha" / "asha_per_1000.csv", SEEDS_DIR / "ashas_per_1000.csv"]


def _first_existing(paths):
    for p in paths:
        if p.exists():
            return p
    return None


def run() -> dict:
    out: dict = {}

    af_path = _first_existing(AF_PATHS)
    out["af_rows"] = (
        [
            {
                "gene": r["gene"],
                "variant_or_allele": r["variant_or_allele"],
                "ethnicity": r.get("ethnicity", ""),
                "state_or_region": r.get("state_or_region", ""),
                "af_indian": _f(r.get("af_indian")),
                "af_sas_gnomad": _f(r.get("af_sas_gnomad") or r.get("af_sas")),
                "af_global": _f(r.get("af_global")),
                "source": r.get("source", ""),
                "n_samples": r.get("n_samples", ""),
            }
            for r in read_csv_rows(af_path)
        ]
        if af_path
        else []
    )

    community_path = _first_existing(COMMUNITY_PATHS)
    out["community_nodes"] = (
        [
            {
                "id": r["community"],
                "type": "Ethnicity",
                "linguistic_group": (r.get("linguistic_group") or "").strip(),
                "primary_states": [s.strip() for s in (r.get("primary_states") or "").split(";") if s.strip()],
                "founder_disease_id": r.get("founder_disease_id", ""),
                "founder_note": r.get("founder_note", ""),
                "carrier_multiplier": _f(r.get("carrier_multiplier")) or 1.0,
            }
            for r in read_csv_rows(community_path)
        ]
        if community_path
        else []
    )

    nfhs_path = _first_existing(NFHS_PATHS)
    asha_path = _first_existing(ASHA_PATHS)
    asha_by_state = (
        {r["state"]: _f(r.get("asha_per_1000")) for r in read_csv_rows(asha_path)} if asha_path else {}
    )
    out["state_nodes"] = (
        [
            {
                "id": r["state"],
                "type": "State",
                "consanguinity_rate": _f(r.get("consanguinity_rate_pct")) or 0.0,
                "asha_per_1000": asha_by_state.get(r["state"]),
                "source": r.get("source", "NFHS-5"),
            }
            for r in read_csv_rows(nfhs_path)
        ]
        if nfhs_path
        else []
    )

    lab_path = _first_existing(LABS_PATHS)
    out["lab_nodes"] = (
        [
            {
                "id": r["lab_id"],
                "type": "Lab",
                "name": r["lab_name"],
                "city": r.get("city", ""),
                "state": r.get("state", ""),
                "tests": [t.strip() for t in (r.get("tests_offered") or "").split(";") if t.strip()],
                "nabl_accredited": (r.get("nabl_accredited") or "false").lower() == "true",
            }
            for r in read_csv_rows(lab_path)
        ]
        if lab_path
        else []
    )

    spec_path = _first_existing(SPECIALISTS_PATHS)
    out["specialist_nodes"] = (
        [
            {
                "id": r["specialist_id"],
                "type": "Doctor",
                "name": r["name"],
                "specialty": r.get("specialty", ""),
                "city": r.get("city", ""),
                "state": r.get("state", ""),
                "institution": r.get("institution_dummy", ""),
            }
            for r in read_csv_rows(spec_path)
        ]
        if spec_path
        else []
    )

    return out


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    result = run()
    print(
        f"AF rows: {len(result['af_rows'])}, communities: {len(result['community_nodes'])}, "
        f"states: {len(result['state_nodes'])}, labs: {len(result['lab_nodes'])}, specialists: {len(result['specialist_nodes'])}"
    )
