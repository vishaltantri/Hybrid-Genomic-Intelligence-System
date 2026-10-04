"""Module 10/11 endpoints: federated aggregates, national dashboard, policy briefs."""
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, Query

from backend.app.security import require
from backend.app.services import registry
from ml_services.config import SEEDS_DIR
from ml_services.utils import read_csv_rows

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

# SIMULATED national records (see docs/DATASETS.md): no open national rare-disease registry
# exists, so the prototype aggregates the same simulated stream the ASHA demo uses.
SIMULATED_NOTE = ("SIMULATED DATA: real national rare-disease registries (ICMR NRROID) are not "
                  "openly downloadable. These figures are generated from knowledge-graph "
                  "prevalences and NFHS-5 consanguinity rates for prototype demonstration only.")


def _simulated_records() -> List[dict]:
    path = SEEDS_DIR / "simulated_national_records.csv"
    return read_csv_rows(path) if path.exists() else []


@router.get("/national")
def national_dashboard(month: str = Query(default="2026-01"),
                       user: dict = Depends(require("dashboard:read"))):
    """Disease map by state + specialist gap analysis (SIMULATED data, labelled as such)."""
    graph = registry.graph
    records = [r for r in _simulated_records() if r.get("month") == month] or _simulated_records()

    by_state: Dict[str, dict] = {}
    for r in records:
        state = r["state"]
        entry = by_state.setdefault(state, {"state": state, "cases": 0, "asha_reports": 0,
                                            "confirmed": 0, "red_flagged": 0, "by_disease": {}})
        entry["cases"] += int(r.get("case_count_simulated") or 0)
        entry["asha_reports"] += int(r.get("asha_reports") or 0)
        entry["confirmed"] += int(r.get("confirmed") or 0)
        entry["red_flagged"] += int(r.get("flagged_red_simulated") or 0)
        did = r.get("disease_id", "")
        entry["by_disease"][did] = entry["by_disease"].get(did, 0) + int(r.get("case_count_simulated") or 0)

    labs_by_state: Dict[str, int] = {}
    docs_by_state: Dict[str, int] = {}
    for lab in graph.by_type("Lab"):
        labs_by_state[lab.get("state", "")] = labs_by_state.get(lab.get("state", ""), 0) + 1
    for doc in graph.by_type("Doctor"):
        docs_by_state[doc.get("state", "")] = docs_by_state.get(doc.get("state", ""), 0) + 1

    for state, entry in by_state.items():
        entry["labs"] = labs_by_state.get(state, 0)
        entry["specialists"] = docs_by_state.get(state, 0)
        # gap score: cases per available specialist+lab (higher = worse access)
        capacity = max(entry["specialists"] + entry["labs"], 1)
        entry["access_gap_score"] = round(entry["cases"] / capacity, 2)
        entry["gap_label"] = ("critical" if entry["access_gap_score"] > 40 else
                              "high" if entry["access_gap_score"] > 15 else "ok")
        entry["consanguinity_rate"] = (graph.node("State", state) or {}).get("consanguinity_rate", None)

    rows = sorted(by_state.values(), key=lambda e: -e["cases"])
    return {
        "month": month,
        "states": rows,
        "totals": {
            "cases": sum(s["cases"] for s in rows),
            "confirmed": sum(s["confirmed"] for s in rows),
            "red_flagged": sum(s["red_flagged"] for s in rows),
            "states_reporting": len(rows),
        },
        "top_states_by_gap": [{"state": s["state"], "gap": s["access_gap_score"], "label": s["gap_label"]}
                              for s in sorted(rows, key=lambda e: -e["access_gap_score"])[:5]],
        "data_note": SIMULATED_NOTE,
        "map_hint": ("Frontend renders this with the Datameet India GeoJSON (github.com/datameet/maps) "
                     "or the schematic coordinates in data/seeds/india_state_coords.csv."),
    }


@router.get("/research-gap")
def research_gap(user: dict = Depends(require("dashboard:read"))):
    """Which Indian-prevalent conditions have the least research/linkage attention (proxy score)."""
    graph = registry.graph
    rows = []
    for d in graph.by_type("Disease"):
        prevalence = float(d.get("prevalence_per_100k") or 0)
        gene_links = len(graph.neighbors(d["id"], "ASSOCIATED_WITH"))
        pheno_links = len(graph.edges_from(d["id"], "HAS_PHENOTYPE"))
        linkage = gene_links + pheno_links / 10.0
        gap = round(prevalence / max(linkage, 0.5), 2)
        rows.append({"disease_id": d["id"], "disease_name": d["name"],
                     "prevalence_per_100k": prevalence, "gene_links": gene_links,
                     "phenotype_links": pheno_links, "research_gap_score": gap})
    rows.sort(key=lambda r: -r["research_gap_score"])
    return {"rows": rows[:15],
            "method_note": ("Prototype proxy: prevalence divided by knowledge-graph linkage density. "
                            "Production version should use PubMed publication counts per disease "
                            "(ml_services/learning_pipeline/pubmed_scraper.py).")}


@router.get("/driver-gene-map")
def driver_gene_map(user: dict = Depends(require("dashboard:read"))):
    """Drug availability vs pharmacogenomic need, by gene (Module 11 tile)."""
    coverage = registry.pgx.drug_gene_table()
    by_gene: Dict[str, dict] = {}
    for row in coverage:
        g = by_gene.setdefault(row["gene"], {"gene": row["gene"], "af_indian": row["af_indian"],
                                             "drugs": [], "max_severity": ""})
        if row["drug"] not in g["drugs"]:
            g["drugs"].append(row["drug"])
        order = {"": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        if order.get(row.get("severity", ""), 0) > order.get(g["max_severity"], 0):
            g["max_severity"] = row.get("severity", "")
    return {"genes": sorted(by_gene.values(), key=lambda x: -x["af_indian"]),
            "note": "High AF + critical severity genes are the priority for Indian PGx test panels."}


@router.post("/policy-brief")
def policy_brief(month: str = Query(default="2026-01"),
                 user: dict = Depends(require("dashboard:read"))):
    """Generate a government-style policy brief from the dashboard aggregates."""
    dash = national_dashboard(month=month, user=user)
    gap = research_gap(user=user)
    pgx = driver_gene_map(user=user)
    lines = [
        "# Policy Brief: Rare Disease Intelligence (SIMULATED prototype data)",
        "",
        f"**Reporting month:** {dash['month']}  |  **States reporting:** {dash['totals']['states_reporting']}",
        "",
        "## 1. Current picture",
        f"- {dash['totals']['cases']:,} suspected rare-disease presentations were recorded across "
        f"{dash['totals']['states_reporting']} states, of which {dash['totals']['confirmed']:,} were confirmed.",
        f"- {dash['totals']['red_flagged']:,} presentations met urgent referral criteria.",
        "",
        "## 2. Access gaps (where patients are, and where specialists are not)",
    ]
    for s in dash["top_states_by_gap"]:
        lines.append(f"- **{s['state']}** — access gap score {s['gap']} ({s['label']}): "
                     "high case load relative to available genetic labs and specialists.")
    lines += ["", "## 3. Research gaps"]
    for r in gap["rows"][:5]:
        lines.append(f"- {r['disease_name']}: prevalence proxy {r['prevalence_per_100k']}/100k with only "
                     f"{r['gene_links']} gene and {r['phenotype_links']} phenotype links curated — "
                     "under-studied relative to burden.")
    lines += ["", "## 4. Pharmacogenomics preparedness"]
    for g in pgx["genes"][:5]:
        lines.append(f"- {g['gene']} (Indian AF {g['af_indian']}) drives risk for "
                     f"{', '.join(g['drugs'][:3])} — severity {g['max_severity'] or 'n/a'}.")
    lines += ["", "## 5. Recommended actions",
              "1. Fund genetic testing capacity in the highest access-gap states (see section 2).",
              "2. Expand newborn screening for hemoglobinopathies and G6PD in tribal districts.",
              "3. Prioritise PGx panel availability for genes with high Indian allele frequency.",
              "4. Commission research on the under-linked conditions in section 3."]
    return {"month": month, "markdown": "\n".join(lines), "format": "markdown",
            "data_note": SIMULATED_NOTE}
