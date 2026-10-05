"""Digital Twin state builders (Phase 3D).

Every function here derives one section of the Twin from data that already exists in the
case record, the Variant Intelligence session, the diagnosis engine, the PGx engine and the
Knowledge Graph. Nothing is estimated or invented: when a source is empty the section says
so (`available: False` + a plain-language note) instead of guessing.

Sections
    phenotype  - HPO terms documented for the patient, with provenance and organ systems
    genomic    - the selected Variant Intelligence analysis, counts and prioritised variants
    diagnosis  - ranked differential from the existing engine + per-disease genomic support
    pgx        - star alleles seen in the analysis and the guideline drug-gene pairs they touch
    family     - what the case record says about relatives (no pedigree is inferred)
    timeline   - dated events that exist in stored data
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set, Tuple

INSUFFICIENT = "Insufficient data"

NON_BENIGN = {"Pathogenic", "Likely pathogenic", "Uncertain significance"}
PLP = {"Pathogenic", "Likely pathogenic"}

SLIM_VARIANT_FIELDS = (
    "variant_id", "rank", "gene_symbol", "hgvs", "cdna", "protein", "consequence", "genotype",
    "zygosity", "disease_id", "disease_name", "inheritance", "clinvar_id", "clinvar_significance",
    "af_indian", "af_global", "acmg_classification", "acmg_score", "priority_score",
    "priority_tier", "phenotype_match_score", "pgx_star_allele", "pgx_function",
    "chrom", "pos", "ref", "alt", "af_sas", "cadd_phred", "criteria_met_pathogenic", "criteria_met_benign",
    "acmg_explanation", "priority_rationale", "matched_hpo_terms",
)

# CPIC-style translation of a *loss-of-function* star allele plus zygosity into a metabolizer
# status the PGx engine understands. Only applied for the LoF case; gain-of-function and
# "decreased function" alleles are listed but their status is NOT guessed.
_X_LINKED = {"G6PD"}


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _epoch(iso: Optional[str]) -> float:
    if not iso:
        return 0.0
    try:
        return time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
    except ValueError:
        return 0.0


# ------------------------------- ontology helpers -------------------------------

class HpoOntology:
    """Organ-system lookup derived from the graph's own HPO IS_A hierarchy."""

    ROOT_ABNORMALITY = "HP:0000118"

    def __init__(self, graph: Any):
        self.graph = graph
        self.parents: Dict[str, List[str]] = {}
        for e in graph.edges:
            if e["type"] == "IS_A" and e.get("src_type") == "Hpo":
                self.parents.setdefault(e["src"], []).append(e["dst"])

    def name(self, hpo_id: str) -> Optional[str]:
        node = self.graph.node("Hpo", hpo_id)
        return node.get("name") if node else None

    def known(self, hpo_id: str) -> bool:
        return self.graph.node("Hpo", hpo_id) is not None

    def organ_systems(self, hpo_id: str) -> List[Dict[str, str]]:
        """Top-level 'Abnormality of ...' ancestors (children of Phenotypic abnormality)."""
        found: Dict[str, str] = {}
        stack, seen = [hpo_id], set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for parent in self.parents.get(cur, []):
                if parent == self.ROOT_ABNORMALITY:
                    nm = self.name(cur) or cur
                    # Only "Abnormality of the <system>" terms are organ systems; a bare finding that sits
                    # directly under the root (e.g. Hepatomegaly) is reported as unclassified, not as a system.
                    if nm.lower().startswith("abnormality of"):
                        found[cur] = nm
                    else:
                        found["other"] = "Other / not mapped to an organ system"
                else:
                    stack.append(parent)
        return [{"id": k, "name": v} for k, v in sorted(found.items())]


# ------------------------------- phenotype state -------------------------------

def collect_phenotype_records(patient: dict, events: List[dict]) -> Dict[str, dict]:
    """HPO term -> documentation record, gathered from stored case data only."""
    records: Dict[str, dict] = {}

    def add(hpo_id: str, source: dict) -> None:
        rec = records.setdefault(hpo_id, {"hpo_id": hpo_id, "sources": []})
        rec["sources"].append(source)

    for hid in (patient.get("extra") or {}).get("hpo_ids", []) or []:
        add(str(hid), {"type": "patient_record", "ref": patient["patient_id"],
                       "timestamp": patient.get("created_utc"), "label": "Patient record HPO list"})

    for ev in sorted(events, key=lambda e: e.get("created_utc") or ""):
        payload = ev.get("payload") or {}
        if ev["kind"] == "phenotype_assertions":
            # explicit clinician-confirmed negation / uncertainty removes the term from the computational set
            for item in payload.get("assertions", []):
                if item.get("assertion") in ("absent", "possible"):
                    records.pop(item["hpo_id"], None)
        elif ev["kind"] == "hpo_profile":
            for item in payload.get("hpo_profile", []):
                add(item["hpo_id"], {
                    "type": "hpo_profile", "ref": ev["event_id"], "timestamp": ev["created_utc"],
                    "label": "Clinical-text HPO mapping",
                    "evidence_text": item.get("evidence_text"), "confidence": item.get("confidence"),
                    "method": item.get("method"),
                })
        elif ev["kind"] == "diagnosis":
            for hid in payload.get("hpo_ids", []) or []:
                add(hid, {"type": "diagnosis_input", "ref": ev["event_id"],
                          "timestamp": ev["created_utc"], "label": "Entered in a stored diagnosis run"})
    return records


def build_phenotype_state(records: Dict[str, dict], ontology: HpoOntology, events: List[dict]) -> dict:
    observed, systems, unknown = [], {}, []
    for hpo_id, rec in sorted(records.items(), key=lambda kv: min(
            (s.get("timestamp") or "" for s in kv[1]["sources"]), default="")):
        name = ontology.name(hpo_id)
        if name is None:
            unknown.append(hpo_id)
        organs = ontology.organ_systems(hpo_id) if name else []
        for o in organs:
            systems.setdefault(o["id"], {"system_id": o["id"], "system": o["name"], "hpo_ids": []})
            systems[o["id"]]["hpo_ids"].append(hpo_id)
        stamps = [s["timestamp"] for s in rec["sources"] if s.get("timestamp")]
        observed.append({
            "hpo_id": hpo_id,
            "name": name or hpo_id,
            "in_knowledge_graph": name is not None,
            "organ_systems": organs,
            "sources": rec["sources"],
            "first_documented_utc": min(stamps) if stamps else None,
            # Onset / severity are not captured by any existing intake path.
            "onset": None,
            "severity": None,
        })
    unmapped: List[str] = []
    for ev in events:
        if ev["kind"] == "hpo_profile":
            unmapped.extend((ev.get("payload") or {}).get("unmapped_symptoms", []) or [])
    return {
        "available": bool(observed),
        "count": len(observed),
        "observed": observed,
        "organ_systems": sorted(systems.values(), key=lambda s: -len(s["hpo_ids"])),
        "unmapped_symptoms": sorted(set(unmapped)),
        "unknown_to_graph": unknown,
        "onset_severity": "Onset and severity are not recorded for any phenotype in the case data.",
        "note": None if observed else
        f"{INSUFFICIENT}: no HPO phenotypes are documented for this patient yet "
        "(use Phenotypes to map clinical text to HPO terms with this patient selected).",
    }


# ------------------------------- genomic state -------------------------------

def slim_variant(v: dict) -> dict:
    return {k: v.get(k) for k in SLIM_VARIANT_FIELDS}


def count_classes(variants: List[dict]) -> Dict[str, int]:
    return {
        "total": len(variants),
        "pathogenic": sum(1 for v in variants if v["acmg_classification"] == "Pathogenic"),
        "likely_pathogenic": sum(1 for v in variants if v["acmg_classification"] == "Likely pathogenic"),
        "vus": sum(1 for v in variants if v["acmg_classification"] == "Uncertain significance"),
        "benign_likely_benign": sum(1 for v in variants if v["acmg_classification"] in ("Benign", "Likely benign")),
        "tier1": sum(1 for v in variants if (v.get("priority_tier") or "").startswith("Tier 1")),
    }


def gene_summary(variants: List[dict]) -> List[dict]:
    order = {"Pathogenic": 0, "Likely pathogenic": 1, "Uncertain significance": 2, "Likely benign": 3, "Benign": 4}
    genes: Dict[str, dict] = {}
    for v in variants:
        g = v.get("gene_symbol")
        if not g:
            continue
        rec = genes.setdefault(g, {"gene": g, "variant_ids": [], "best_classification": v["acmg_classification"],
                                   "diseases": set(), "inheritance": set(), "zygosity": set()})
        rec["variant_ids"].append(v["variant_id"])
        if order.get(v["acmg_classification"], 9) < order.get(rec["best_classification"], 9):
            rec["best_classification"] = v["acmg_classification"]
        if v.get("disease_name"):
            rec["diseases"].add(v["disease_name"])
        if v.get("inheritance"):
            rec["inheritance"].add(v["inheritance"])
        if v.get("zygosity"):
            rec["zygosity"].add(v["zygosity"])
    out = []
    for rec in genes.values():
        out.append({**rec, "diseases": sorted(rec["diseases"]), "inheritance": sorted(rec["inheritance"]),
                    "zygosity": sorted(rec["zygosity"])})
    out.sort(key=lambda r: (order.get(r["best_classification"], 9), r["gene"]))
    return out


def build_genomic_state(analysis: Optional[dict], analyses: List[dict], twin_hpos: List[str]) -> dict:
    listing = [{"analysis_id": a["analysis_id"], "filename": a["filename"],
                "timestamp_utc": _iso(a["timestamp"]), "total_variants": a["qc_metrics"]["total_variants"]}
               for a in analyses]
    if not analysis:
        return {
            "available": False, "analyses": listing, "variants": [], "counts": count_classes([]),
            "note": f"{INSUFFICIENT}: no Variant Intelligence analysis is linked to this patient. "
                    "Upload a VCF in Variant Intelligence with this patient selected.",
        }
    variants = [slim_variant(v) for v in analysis["variants"]]
    analysis_hpos = sorted(analysis.get("patient_hpo_ids") or [])
    return {
        "available": True,
        "analysis_id": analysis["analysis_id"],
        "filename": analysis["filename"],
        "timestamp_utc": _iso(analysis["timestamp"]),
        "created_by": analysis.get("created_by"),
        "analyses": listing,
        "counts": count_classes(variants),
        "pgx_variant_count": analysis["qc_metrics"].get("pgx_variant_count", 0),
        "samples": analysis["qc_metrics"].get("samples", []),
        "variants": variants,
        "prioritized": [v for v in variants if (v["priority_tier"] or "").startswith("Tier 1")
                        or v["acmg_classification"] in PLP][:10],
        "genes": gene_summary(analysis["variants"]),
        "analysis_hpo_ids": analysis_hpos,
        "hpo_set_differs_from_twin": analysis_hpos != sorted(twin_hpos),
        "inheritance_note": (
            "Genotype shown is for the first VCF sample only; per-sample segregation and de novo "
            "status are not stored by the Variant Intelligence engine."
            if len(analysis["qc_metrics"].get("samples", [])) > 1 else
            "Single-sample VCF: no segregation or de novo evidence is available."),
    }


# ------------------------------- diagnosis state -------------------------------

def disease_genes(graph: Any, disease_id: str) -> List[str]:
    return sorted({g["id"] for g in graph.neighbors(disease_id, "ASSOCIATED_WITH") if g.get("type") == "Gene"})


def genomic_support(graph: Any, variants: List[dict], disease_id: str) -> dict:
    """Which non-benign variants implicate this disease (by variant->disease or gene->disease)."""
    genes = set(disease_genes(graph, disease_id))
    support = [v for v in variants if v["acmg_classification"] in NON_BENIGN and
               (v.get("disease_id") == disease_id or (v.get("gene_symbol") in genes))]
    return {
        "disease_id": disease_id,
        "genes": sorted(genes),
        "pathogenic_or_likely": sum(1 for v in support if v["acmg_classification"] in PLP),
        "vus": sum(1 for v in support if v["acmg_classification"] == "Uncertain significance"),
        "variant_ids": [v["variant_id"] for v in support],
        "max_priority_score": max((v["priority_score"] for v in support), default=None),
    }


def implicated_diseases(graph: Any, variants: List[dict]) -> Set[str]:
    out: Set[str] = set()
    for v in variants:
        if v["acmg_classification"] not in NON_BENIGN:
            continue
        if v.get("disease_id") and graph.node("Disease", v["disease_id"]):
            out.add(v["disease_id"])
        if v.get("gene_symbol"):
            for d in graph.neighbors(v["gene_symbol"], "ASSOCIATED_WITH"):
                if d.get("type") == "Disease":
                    out.add(d["id"])
    return out


def supporting_phenotypes(diagnosis_engine: Any, hpos: List[str], disease_id: str) -> int:
    if not hpos:
        return 0
    rows = diagnosis_engine.attribute_symptoms(hpos, disease_id, top_n=len(hpos))
    return sum(1 for r in rows if r["similarity"] > 0)


def evaluate_diagnosis_state(diagnosis_engine: Any, graph: Any, hpos: List[str], context: dict,
                             variants: List[dict], top_k: int = 10, explain: bool = False,
                             _cache: Optional[dict] = None) -> dict:
    """Run the *existing* engine on the given HPO set and annotate with genomic support."""
    if not hpos:
        return {"available": False, "differential": [], "genomic_candidates": [], "top_diagnosis": None,
                "note": f"{INSUFFICIENT}: a phenotype profile is required to rank diagnoses."}
    key = (tuple(sorted(hpos)), context.get("state") or "", context.get("community") or "",
           context.get("sex") or "", top_k, explain)
    if _cache is not None and key in _cache:
        raw = _cache[key]
    else:
        raw = diagnosis_engine.diagnose(sorted(hpos), context, top_k=top_k, explain=explain)
        if _cache is not None:
            _cache[key] = raw
    results = raw.get("results", [])
    differential = []
    for i, r in enumerate(results):
        sup = genomic_support(graph, variants, r["disease_id"])
        entry = {
            "rank": i + 1, "disease_id": r["disease_id"], "disease_name": r["disease_name"],
            "probability": r["probability"], "probability_ci": r.get("probability_ci"),
            "phenotype_similarity": r["phenotype_similarity"], "inheritance": r.get("inheritance"),
            "genes": r.get("genes", []), "genomic_support": sup,
            "supporting_phenotype_count": supporting_phenotypes(diagnosis_engine, hpos, r["disease_id"]),
        }
        if explain:
            entry["driving_symptoms"] = r.get("driving_symptoms", [])
            entry["missing_findings"] = r.get("missing_findings", [])
            entry["confirmatory_tests"] = r.get("confirmatory_tests")
            entry["population_prior"] = r.get("population_prior")
        differential.append(entry)

    ranked_ids = {d["disease_id"]: d["rank"] for d in differential}
    candidates = []
    for did in sorted(implicated_diseases(graph, variants)):
        sup = genomic_support(graph, variants, did)
        if not sup["variant_ids"]:
            continue
        node = graph.node("Disease", did) or {}
        candidates.append({
            "disease_id": did, "disease_name": node.get("name", did),
            "phenotype_similarity": round(diagnosis_engine.baseline.disease_score(hpos, did), 4),
            "phenotype_rank_in_differential": ranked_ids.get(did),
            "genomic_support": sup,
        })
    candidates.sort(key=lambda c: (-c["genomic_support"]["pathogenic_or_likely"],
                                   -(c["genomic_support"]["max_priority_score"] or 0), c["disease_name"]))
    return {
        "available": True,
        "engine": raw.get("engine"),
        "ranking_note": raw.get("ranking_note"),
        "differential": differential,
        "top_diagnosis": differential[0] if differential else None,
        "genomic_candidates": candidates,
        "ranking_basis": "Phenotype similarity x Indian population prior (existing engine). "
                         "Variants are shown as separate genomic support and do not alter this ranking.",
        "note": None if differential else "No phenotype matched any disease in the knowledge graph.",
    }


# ------------------------------- PGx state -------------------------------

def metabolizer_status(gene: str, function: str, zygosity: str) -> Optional[str]:
    """LoF allele + zygosity -> engine status; anything else is left unassigned."""
    if (function or "").lower() != "lof":
        return None
    z = (zygosity or "").lower()
    if gene in _X_LINKED:
        return "deficient" if z in ("homozygous", "hemizygous") else ("carrier" if z == "heterozygous" else None)
    if z == "homozygous":
        return "poor_metabolizer"
    if z == "heterozygous":
        return "intermediate_metabolizer"
    return None


def known_genotypes_from_variants(variants: List[dict]) -> Tuple[Dict[str, str], List[dict]]:
    """gene -> status for LoF alleles; also returns the per-variant observations."""
    known: Dict[str, str] = {}
    observations: List[dict] = []
    for v in variants:
        star = v.get("pgx_star_allele")
        if not star:
            continue
        gene = v.get("gene_symbol") or star.split("*")[0].split(" ")[0]
        status = metabolizer_status(gene, v.get("pgx_function"), v.get("zygosity"))
        observations.append({"variant_id": v["variant_id"], "gene": gene, "star_allele": star,
                             "function": v.get("pgx_function"), "zygosity": v.get("zygosity"),
                             "assigned_status": status})
        if status and gene not in known:
            known[gene] = status
    return known, observations


def build_pgx_state(pgx_engine: Any, variants: List[dict], patient: dict) -> dict:
    known, observations = known_genotypes_from_variants(variants)
    if not observations:
        return {"available": False, "observations": [], "findings": [],
                "note": "No PGx findings available for this case."}
    findings = []
    for gene in sorted({o["gene"] for o in observations}):
        rows = pgx_engine.gene_drug_index.get(gene, [])
        drugs = sorted({(r.get("drug") or "").lower() for r in rows if r.get("drug")})
        if not drugs:
            continue
        res = pgx_engine.check_drugs(drugs, state=patient.get("state") or "",
                                     known_genotypes={gene: known[gene]} if gene in known else {},
                                     sex=patient.get("sex") or "")
        for a in res["alerts"]:
            if a["gene"].split("+")[0] != gene:
                continue
            findings.append({
                "gene": gene, "drug": a["drug"], "severity": a["severity"],
                "status": a["inferred_status"], "recommendation": a["recommendation"],
                "evidence_level": a["evidence_level"], "alternatives": a["alternatives"],
                "actionability": ("guideline recommendation in rule" if a["recommendation"] else
                                  "status-derived default severity (rule has no recommendation text)"),
                "basis": ("genotype from variant analysis" if a["assumption"] == "known_genotype_override"
                          else "population inference (genotype status not assignable from the variant)"),
            })
    return {
        "available": True, "observations": observations, "findings": findings,
        "note": ("Genotype-derived status is assigned only for loss-of-function alleles; other alleles are "
                 "listed without a metabolizer call. Confirm with clinical PGx testing."),
    }


# ------------------------------- family state -------------------------------

def build_family_state(patient: dict, analysis: Optional[dict]) -> dict:
    extra = patient.get("extra") or {}
    fam = {k: v for k, v in (extra.get("family_history") or {}).items()}
    carrier = {k: v for k, v in (extra.get("known_carrier") or {}).items() if v}
    affected = {k: v for k, v in (extra.get("known_affected") or {}).items() if v}
    cons = bool(patient.get("consanguineous"))
    has_data = bool(fam or carrier or affected or cons)
    samples = (analysis or {}).get("qc_metrics", {}).get("samples", []) if analysis else []
    return {
        "available": has_data,
        "consanguineous_parents": cons,
        "family_history": fam, "known_carrier": sorted(carrier), "known_affected": sorted(affected),
        "vcf_samples": samples,
        "segregation": None,
        "note": None if has_data else "Family/inheritance information unavailable.",
        "limitation": ("No relatives, pedigree structure, segregation or de novo evidence are stored; "
                       "none are inferred." + (f" The VCF names {len(samples)} samples but only the first "
                                              "sample's genotype is retained." if len(samples) > 1 else "")),
    }


# ------------------------------- timeline -------------------------------

def _event_title(ev: dict) -> Optional[Tuple[str, str, str]]:
    kind, p = ev["kind"], ev.get("payload") or {}
    if kind == "hpo_profile":
        return ("phenotype", "Phenotypes documented", f"{len(p.get('hpo_ids', []))} HPO term(s) mapped from clinical text")
    if kind == "clinical_note":
        return ("note", "Clinical note recorded", f"{len(p.get('entities', []))} entities extracted")
    if kind == "diagnosis":
        res = p.get("results") or []
        top = f"top: {res[0]['disease_name']}" if res else "no ranked result"
        return ("diagnosis", "Diagnosis analysis run", top)
    if kind == "vcf_analysis":
        return ("genomic", "Variant analysis uploaded",
                f"{p.get('filename')} - {(p.get('qc_metrics') or {}).get('total_variants', '?')} variants")
    if kind == "variant_report_bundle":
        return ("report", "Variant findings sent to report", f"{len(p.get('reported_variants', []))} variant(s)")
    if kind == "twin_report_bundle":
        return ("report", "Digital Twin snapshot sent to report", p.get("snapshot_version", ""))
    return None


def build_timeline(patient: dict, events: List[dict], analyses: List[dict]) -> dict:
    items: List[dict] = []
    if patient.get("created_utc"):
        items.append({"timestamp_utc": patient["created_utc"], "kind": "registration",
                      "title": "Patient registered", "detail": "", "source": {"type": "patient", "ref": patient["patient_id"]}})
    seen_analyses = set()
    for ev in events:
        t = _event_title(ev)
        if not t:
            continue
        kind, title, detail = t
        if ev["kind"] == "vcf_analysis":
            seen_analyses.add((ev.get("payload") or {}).get("analysis_id"))
        items.append({"timestamp_utc": ev["created_utc"], "kind": kind, "title": title, "detail": detail,
                      "source": {"type": ev["kind"], "ref": ev["event_id"]}})
    for a in analyses:
        if a["analysis_id"] not in seen_analyses:
            items.append({"timestamp_utc": _iso(a["timestamp"]), "kind": "genomic",
                          "title": "Variant analysis completed",
                          "detail": f"{a['filename']} - {a['qc_metrics']['total_variants']} variants",
                          "source": {"type": "variant_analysis", "ref": a["analysis_id"]}})
    items.sort(key=lambda i: i["timestamp_utc"] or "")
    days = {(i["timestamp_utc"] or "")[:10] for i in items}
    limited = len(items) < 3 or len(days) < 2
    return {
        "available": bool(items), "events": items, "limited": limited,
        "note": ("Longitudinal history is limited in the current dataset: all recorded events fall on "
                 "a single day or there are fewer than three."
                 if limited else None),
    }
