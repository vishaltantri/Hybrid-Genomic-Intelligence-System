"""Body-system and genome-layer mapping for the Digital Twin visualisation.

Everything here is *reference knowledge + the patient's own data*; nothing is a measurement:

* ``SYSTEMS``            body systems that the 3D/2D body can highlight (display taxonomy).
* ``HPO_SYSTEM``         curated HPO term -> body system table for the 67 phenotype terms that exist in the
                         Genomera knowledge graph (the graph's own IS_A hierarchy puts many of them directly
                         under the root, so it cannot place e.g. Hepatomegaly). Terms not listed here are
                         resolved through their "Abnormality of the <system>" ancestor, else left unmapped.
* ``CHROMOSOME_LENGTHS`` GRCh38 primary-assembly lengths (bp), used only to place a variant's VCF position.

A system is marked as having *case-specific* data only when (a) one of the patient's documented phenotypes maps
to it, or (b) a non-benign variant of the patient lies in a gene that the knowledge graph links to a disease
whose documented phenotypes map to it. Otherwise it stays neutral ("No case-specific genomic or phenotype
findings mapped to this system.").
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

SYSTEMS: List[Dict[str, str]] = [
    {"id": "nervous", "label": "Nervous"},
    {"id": "ocular", "label": "Ocular"},
    {"id": "cardiovascular", "label": "Cardiovascular"},
    {"id": "respiratory", "label": "Respiratory"},
    {"id": "digestive", "label": "Digestive"},
    {"id": "hepatic", "label": "Hepatic"},
    {"id": "renal", "label": "Renal"},
    {"id": "endocrine", "label": "Endocrine"},
    {"id": "musculoskeletal", "label": "Musculoskeletal"},
    {"id": "hematologic", "label": "Hematologic"},
    {"id": "immune", "label": "Immune / lymphoid"},
    {"id": "reproductive", "label": "Reproductive"},
    {"id": "integumentary", "label": "Skin"},
]
SYSTEM_LABEL = {s["id"]: s["label"] for s in SYSTEMS}

_ANCESTOR_KEYWORDS = {
    "nervous system": "nervous", "eye": "ocular", "skin": "integumentary", "musculature": "musculoskeletal",
    "skeletal": "musculoskeletal", "cardiovascular": "cardiovascular", "respiratory": "respiratory",
    "liver": "hepatic", "digestive": "digestive", "kidney": "renal", "genitourinary": "renal",
    "endocrine": "endocrine", "blood": "hematologic", "immune": "immune",
}

HPO_SYSTEM: Dict[str, str] = {
    # nervous
    "HP:0001249": "nervous", "HP:0001250": "nervous", "HP:0001252": "nervous", "HP:0001263": "nervous",
    "HP:0001251": "nervous", "HP:0001337": "nervous", "HP:0001332": "nervous", "HP:0001257": "nervous",
    "HP:0001288": "nervous", "HP:0002515": "nervous", "HP:0001284": "nervous", "HP:0001265": "nervous",
    "HP:0001307": "nervous", "HP:0001297": "nervous", "HP:0002460": "nervous", "HP:0011344": "nervous",
    "HP:0000252": "nervous", "HP:0000256": "nervous",
    # musculoskeletal
    "HP:0002066": "musculoskeletal", "HP:0003011": "musculoskeletal", "HP:0001324": "musculoskeletal",
    "HP:0008981": "musculoskeletal", "HP:0002486": "musculoskeletal", "HP:0001761": "musculoskeletal",
    "HP:0001217": "musculoskeletal", "HP:0004322": "musculoskeletal", "HP:0000098": "musculoskeletal",
    # ocular
    "HP:0000478": "ocular", "HP:0000618": "ocular", "HP:0000510": "ocular", "HP:0000639": "ocular",
    "HP:0000518": "ocular", "HP:0001083": "ocular", "HP:0000616": "ocular", "HP:0000592": "ocular",
    "HP:0000582": "ocular",
    # skin
    "HP:0000951": "integumentary", "HP:0001010": "integumentary", "HP:0000957": "integumentary",
    "HP:0000954": "integumentary", "HP:0000995": "integumentary",
    # hepatic / digestive
    "HP:0000952": "hepatic", "HP:0002240": "hepatic", "HP:0001394": "hepatic",
    "HP:0001738": "digestive", "HP:0002591": "digestive",
    # respiratory / cardiovascular / renal / endocrine / blood / immune
    "HP:0012735": "respiratory", "HP:0002783": "respiratory", "HP:0002110": "respiratory",
    "HP:0001638": "cardiovascular", "HP:0000790": "renal", "HP:0000848": "endocrine",
    "HP:0001903": "hematologic", "HP:0001878": "hematologic", "HP:0001744": "immune",
}

CHROMOSOME_LENGTHS: Dict[str, int] = {
    "chr1": 248956422, "chr2": 242193529, "chr3": 198295559, "chr4": 190214555, "chr5": 181538259,
    "chr6": 170805979, "chr7": 159345973, "chr8": 145138636, "chr9": 138394717, "chr10": 133797422,
    "chr11": 135086622, "chr12": 133275309, "chr13": 114364328, "chr14": 107043718, "chr15": 101991189,
    "chr16": 90338345, "chr17": 83257441, "chr18": 80373285, "chr19": 58617616, "chr20": 64444167,
    "chr21": 46709983, "chr22": 50818468, "chrX": 156040895, "chrY": 57227415,
}
NON_BENIGN = {"Pathogenic", "Likely pathogenic", "Uncertain significance"}


def system_of_hpo(hpo_id: str, ontology: Any) -> Optional[str]:
    """Curated table first, then the 'Abnormality of the <system>' ancestor; None if neither applies."""
    if hpo_id in HPO_SYSTEM:
        return HPO_SYSTEM[hpo_id]
    for anc in ontology.organ_systems(hpo_id):
        name = anc["name"].lower()
        for key, sys_id in _ANCESTOR_KEYWORDS.items():
            if key in name:
                return sys_id
    return None


def disease_systems(graph: Any, ontology: Any, disease_id: str) -> Dict[str, List[str]]:
    """system -> HPO ids (documented manifestations of the disease in the knowledge graph)."""
    out: Dict[str, List[str]] = {}
    for e in graph.edges_from(disease_id, "HAS_PHENOTYPE"):
        s = system_of_hpo(e["dst"], ontology)
        if s:
            out.setdefault(s, []).append(e["dst"])
    return out


def _gene_diseases(graph: Any, gene: str) -> List[dict]:
    return [d for d in graph.neighbors(gene, "ASSOCIATED_WITH") if d.get("type") == "Disease"]


def build_anatomy(graph: Any, ontology: Any, phenotype_state: dict, variants: List[dict],
                  diagnosis_state: dict) -> dict:
    observed = {o["hpo_id"]: o for o in phenotype_state.get("observed", [])}
    pheno_by_system: Dict[str, List[dict]] = {}
    unmapped = []
    for hid, o in observed.items():
        s = system_of_hpo(hid, ontology) if o.get("in_knowledge_graph") else None
        if s:
            pheno_by_system.setdefault(s, []).append({"hpo_id": hid, "name": o["name"]})
        else:
            unmapped.append({"hpo_id": hid, "name": o["name"]})

    # gene index (patient genes only): diseases from the KG, systems from those diseases' documented phenotypes
    gene_index: Dict[str, dict] = {}
    for v in variants:
        g = v.get("gene_symbol")
        if not g:
            continue
        rec = gene_index.setdefault(g, {"gene": g, "variants": [], "diseases": [], "systems": {}, "node": None})
        rec["variants"].append({"variant_id": v["variant_id"], "classification": v["acmg_classification"],
                                "hgvs": v.get("cdna") or v.get("hgvs")})
    for g, rec in gene_index.items():
        node = graph.node("Gene", g) or {}
        rec["node"] = {"name": node.get("name"), "is_pgx": node.get("is_pgx")}
        for d in _gene_diseases(graph, g):
            ds = disease_systems(graph, ontology, d["id"])
            rec["diseases"].append({"disease_id": d["id"], "name": d.get("name") or d["id"],
                                    "inheritance": d.get("inheritance"), "source": d.get("source"),
                                    "systems": sorted(ds)})
            for s, hp in ds.items():
                rec["systems"].setdefault(s, set()).update(hp)
        rec["systems"] = {s: sorted(h) for s, h in rec["systems"].items()}
        rec["best_classification"] = next(
            (c for c in ("Pathogenic", "Likely pathogenic", "Uncertain significance", "Likely benign", "Benign")
             if any(x["classification"] == c for x in rec["variants"])), None)

    systems = []
    for s in SYSTEMS:
        sid = s["id"]
        genes, variant_ids, diseases = [], [], {}
        for g, rec in gene_index.items():
            if sid not in rec["systems"]:
                continue
            relevant = [x for x in rec["variants"] if x["classification"] in NON_BENIGN]
            if not relevant:
                continue
            genes.append(g)
            variant_ids += [x["variant_id"] for x in relevant]
            for d in rec["diseases"]:
                if sid in d["systems"]:
                    diseases[d["disease_id"]] = d["name"]
        phen = pheno_by_system.get(sid, [])
        top = diagnosis_state.get("top_diagnosis") or {}
        systems.append({
            "id": sid, "label": s["label"],
            "has_case_data": bool(phen or variant_ids),
            "phenotypes": phen, "genes": sorted(genes), "variant_ids": variant_ids,
            "diseases": [{"disease_id": k, "name": v} for k, v in sorted(diseases.items())],
            "top_diagnosis_involves": bool(top and top.get("disease_id") in diseases),
            "note": None if (phen or variant_ids) else
            "No case-specific genomic or phenotype findings mapped to this system.",
        })

    chromosomes = []
    for chrom, length in CHROMOSOME_LENGTHS.items():
        here = [{"variant_id": v["variant_id"], "pos": v["pos"], "gene": v.get("gene_symbol"),
                 "classification": v["acmg_classification"], "hgvs": v.get("cdna") or v.get("hgvs"),
                 "ref": v.get("ref"), "alt": v.get("alt")}
                for v in variants if v.get("chrom") == chrom and v.get("pos") is not None]
        chromosomes.append({"chrom": chrom, "length_bp": length, "variants": here})
    placed = {v["variant_id"] for c in chromosomes for v in c["variants"]}
    return {
        "systems": systems,
        "genes": sorted(gene_index.values(), key=lambda r: r["gene"]),
        "chromosomes": chromosomes,
        "variants_not_placed": [v["variant_id"] for v in variants if v["variant_id"] not in placed],
        "unmapped_phenotypes": unmapped,
        "notes": [
            "Computational Digital Twin - derived from available clinical and genomic data; not imaging, "
            "vitals or a scan of the patient.",
            "System highlighting means: a documented patient phenotype maps to the system, or a non-benign "
            "variant lies in a gene whose knowledge-graph disease has documented manifestations there. It does "
            "not indicate organ damage.",
            "Variant positions are those reported in the uploaded VCF (GRCh38 chromosome lengths used for scale); "
            "gene loci are not drawn because no gene coordinates are stored.",
        ],
    }
