"""Clinical Context Retrieval and Grounding Engine for Genomera AI Assistant (Phase 3C).

Retrieves targeted facts from:
- Selected patient record (demographics, state, community, consanguinity)
- Clinical phenotypes (HPO IDs, labels, IC weights)
- Differential diagnosis engine (ranked diseases, probabilities, priors, explanations)
- Variant Intelligence session (top variants, genotypes, ACMG criteria, Indian AFs)
- Genomera Knowledge Graph (gene-disease edges, founder risks, phenotypes)
- Verified reference datasets (ClinVar seeds, CPIC guidelines, Orphanet)

Assembles grounded context with full source citations to prevent hallucinations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app import store
from ml_services.assistant.intent_classifier import detect_intent, extract_entities_from_query


NO_VISIBLE_ANALYSIS = "__no_visible_analysis__"


@dataclass
class Citation:
    source_type: str         # "Variant Analysis", "Knowledge Graph", "ClinVar", "Orphanet", "IndiGenomes", "Diagnosis Engine", "CPIC"
    identifier: str          # e.g. "ATP7B c.2931C>G", "ORPHA:915", "VCV000001337"
    title: str
    summary: str
    reliability: str = "High"  # "High", "Moderate", "Computational Inference"


@dataclass
class RetrievedContext:
    intent: str
    patient_context_text: str
    retrieved_data_text: str
    citations: List[Citation] = field(default_factory=list)
    detected_entities: Dict[str, Any] = field(default_factory=dict)
    has_sufficient_context: bool = True
    context_summary: Dict[str, Any] = field(default_factory=dict)


class ContextRetriever:
    """Binds live Genomera engines to construct grounded clinical context."""

    def __init__(self, services_registry: Any):
        self.registry = services_registry

    def retrieve(
        self,
        query: str,
        patient_id: Optional[str] = None,
        analysis_id: Optional[str] = None,
        selected_variant_id: Optional[str] = None,
        active_hpo_ids: Optional[List[str]] = None,
        language: str = "en",
        mode: str = "clinical",
    ) -> RetrievedContext:
        intent = detect_intent(query)
        entities = extract_entities_from_query(query)
        citations: List[Citation] = []
        
        patient_parts: List[str] = []
        retrieved_parts: List[str] = []

        patient_record = None
        if patient_id:
            patient_record = store.get_patient(patient_id)
            if patient_record:
                name = patient_record.get("name") or patient_id
                state = patient_record.get("state") or "Unspecified"
                comm = patient_record.get("community") or "General"
                age = patient_record.get("age_years")
                sex = patient_record.get("sex") or "Unknown"
                cons = "Yes (Positive)" if patient_record.get("consanguinity") else "No"
                patient_parts.append(
                    f"PATIENT CONTEXT: ID={patient_id}, Age={age}, Sex={sex}, State={state}, "
                    f"Community={comm}, Consanguinity={cons}."
                )

        # -------------------------------------------------------------
        # 1. Variant & ACMG Retrieval (Phase 3B Engine)
        # -------------------------------------------------------------
        variants_data: List[dict] = []
        if analysis_id and analysis_id != NO_VISIBLE_ANALYSIS:
            analysis = self.registry.variants.get_analysis(analysis_id)
            if analysis:
                variants_data = analysis.get("variants", [])
        elif not variants_data:
            # No analysis_id: inspect recent analyses. The API passes NO_VISIBLE_ANALYSIS when analyses exist but none
            # belong to the caller, so another user's upload is never used; the verified demo trio is used instead.
            recent = [] if analysis_id == NO_VISIBLE_ANALYSIS else self.registry.variants.list_analyses()
            if recent:
                analysis = self.registry.variants.get_analysis(recent[0]["analysis_id"])
                if analysis:
                    variants_data = analysis.get("variants", [])
            else:
                # If no session analyses exist yet, load verified seed clinical trio
                from ml_services.config import SEEDS_DIR
                demo_path = SEEDS_DIR / "clinical_sample_trio.vcf"
                if demo_path.exists():
                    analysis = self.registry.variants.analyze_vcf(
                        demo_path.read_text(encoding="utf-8"),
                        filename="clinical_sample_trio.vcf",
                        patient_id=patient_id or "DEMO-SAMPLE",
                    )
                    variants_data = analysis.get("variants", [])

        target_variant = None
        if selected_variant_id and variants_data:
            for v in variants_data:
                if v.get("variant_id") == selected_variant_id or v.get("hgvs") == selected_variant_id:
                    target_variant = v
                    break
        elif variants_data:
            # Default to top ranked variant if variant question or unspecified
            target_variant = variants_data[0]

        # Check if user mentioned a specific gene from the catalog
        if entities["genes"] and variants_data:
            for v in variants_data:
                if v.get("gene_symbol") in entities["genes"]:
                    target_variant = v
                    break

        if target_variant and intent in ("VARIANT_EXPLANATION", "ACMG_EXPLANATION", "CASE_SUMMARY", "GENERAL_GENOMICS"):
            af_ind_val = target_variant.get("af_indian")
            af_ind_str = f"{af_ind_val * 100:.4f}%" if af_ind_val is not None else "Data unavailable in IndiGenomes"
            af_glob_val = target_variant.get("af_global")
            af_glob_str = f"{af_glob_val * 100:.4f}%" if af_glob_val is not None else "N/A"

            var_desc = (
                f"TARGET VARIANT (Rank #{target_variant.get('rank')}): {target_variant.get('gene_symbol')} "
                f"{target_variant.get('cdna') or target_variant.get('hgvs')} ({target_variant.get('variant_id')})\n"
                f"- Consequence: {target_variant.get('consequence')}\n"
                f"- Genotype: {target_variant.get('genotype')} ({target_variant.get('zygosity')})\n"
                f"- ACMG 2015 Classification: {target_variant.get('acmg_classification')} (Score: {target_variant.get('acmg_score')})\n"
                f"- Priority Tier: {target_variant.get('priority_tier')} (Priority Score: {target_variant.get('priority_score')}%)\n"
                f"- Indian Allele Frequency (IndiGenomes/GenomeIndia): {af_ind_str}\n"
                f"- Global AF: {af_glob_str}\n"
                f"- ClinVar Significance: {target_variant.get('clinvar_significance') or 'No matching ClinVar record in seed catalog'} "
                f"(ID: {target_variant.get('clinvar_id') or 'N/A'})\n"
                f"- Associated Disease: {target_variant.get('disease_name')} ({target_variant.get('disease_id') or 'ID N/A'}, {target_variant.get('inheritance') or 'Inheritance N/A'})\n"
                f"- In-silico CADD: {target_variant.get('cadd_phred')}\n"
                f"- Priority Rationale: {'; '.join(target_variant.get('priority_rationale', []))}"
            )
            retrieved_parts.append(var_desc)

            # Detail ACMG criteria
            met_path = target_variant.get("criteria_met_pathogenic", [])
            met_benign = target_variant.get("criteria_met_benign", [])
            all_crit = target_variant.get("all_criteria", [])
            crit_text_lines = []
            for c in all_crit:
                if c.get("status") == "Met":
                    crit_text_lines.append(f"  * {c.get('code')} ({c.get('applied_strength')}): {c.get('description')} [Evidence: {c.get('evidence')}]")
            
            if crit_text_lines:
                retrieved_parts.append("EVALUATED ACMG/AMP 2015 MET CRITERIA:\n" + "\n".join(crit_text_lines))

            # Citations
            citations.append(Citation(
                source_type="Variant Analysis",
                identifier=target_variant.get("variant_id"),
                title=f"{target_variant.get('gene_symbol')} {target_variant.get('hgvs')}",
                summary=f"ACMG {target_variant.get('acmg_classification')}, Priority Score {target_variant.get('priority_score')}%",
                reliability="High",
            ))
            if target_variant.get("clinvar_id"):
                citations.append(Citation(
                    source_type="ClinVar",
                    identifier=target_variant.get("clinvar_id"),
                    title=f"ClinVar record {target_variant.get('clinvar_id')}",
                    summary=f"Curated significance: {target_variant.get('clinvar_significance')}",
                    reliability="High",
                ))
            if target_variant.get("af_indian") is not None:
                citations.append(Citation(
                    source_type="IndiGenomes",
                    identifier="CSIR-IGIB / GenomeIndia",
                    title="Indian Reference Population Frequency",
                    summary=f"Allele frequency: {target_variant.get('af_indian')*100:.4f}%",
                    reliability="High",
                ))

        # -------------------------------------------------------------
        # 2. Phenotype & Diagnosis Retrieval
        # -------------------------------------------------------------
        hpos_to_use = list(active_hpo_ids or [])
        if not hpos_to_use and patient_record:
            hpos_to_use = list(patient_record.get("hpo_ids") or [])

        # If entities contain HPO terms, add them
        for h in entities["hpo_ids"]:
            if h not in hpos_to_use:
                hpos_to_use.append(h)

        if hpos_to_use and intent in ("DIAGNOSIS_REASONING", "PHENOTYPE_REASONING", "CASE_SUMMARY", "GENERAL_GENOMICS"):
            # Resolve HPO names via KG
            hpo_details = []
            for hid in hpos_to_use:
                node = self.registry.graph.node("Hpo", hid) if self.registry.graph else None
                name = node.get("name") if node else hid
                ic = node.get("ic") if node else 1.0
                hpo_details.append(f"{hid} ({name}, IC={ic:.2f})" if isinstance(ic, float) else f"{hid} ({name})")
            
            retrieved_parts.append("PATIENT PHENOTYPES (HPO):\n- " + "\n- ".join(hpo_details))
            citations.append(Citation(
                source_type="Human Phenotype Ontology",
                identifier=f"{len(hpos_to_use)} HPO terms",
                title="Clinical Phenotype Profile",
                summary=f"Profile containing: {', '.join(hpos_to_use[:4])}",
                reliability="High",
            ))

            # Run or retrieve differential diagnosis
            context_ctx = {
                "state": patient_record.get("state") if patient_record else None,
                "community": patient_record.get("community") if patient_record else None,
                "sex": patient_record.get("sex") if patient_record else None,
            }
            try:
                diag_res = self.registry.diagnosis.diagnose(hpos_to_use, context_ctx, top_k=3, explain=True)
                diff = diag_res.get("differential", [])
                if diff:
                    diff_lines = []
                    for rank_i, d in enumerate(diff, 1):
                        diff_lines.append(
                            f"#{rank_i} {d.get('disease_name')} ({d.get('disease_id')}): "
                            f"Probability={d.get('probability')*100:.1f}%, Similarity={d.get('similarity')*100:.1f}%, "
                            f"Prior Multiplier={d.get('prior_multiplier')*100:.2f}%, Match={d.get('match_count')}/{d.get('total_phenotypes')} phenotypes."
                        )
                        if d.get("top_matching_phenotypes"):
                            diff_lines.append(f"   Matches: {', '.join(d.get('top_matching_phenotypes'))}")
                    
                    retrieved_parts.append("RANKED DIFFERENTIAL DIAGNOSIS:\n" + "\n".join(diff_lines))
                    top_disease = diff[0]
                    citations.append(Citation(
                        source_type="Diagnosis Engine",
                        identifier=top_disease.get("disease_id"),
                        title=top_disease.get("disease_name"),
                        summary=f"Probability {top_disease.get('probability')*100:.1f}%, Resnik similarity {top_disease.get('similarity')*100:.1f}%",
                        reliability="Computational Inference",
                    ))
            except Exception as ex:
                retrieved_parts.append(f"Differential diagnosis computation error: {ex}")

        # -------------------------------------------------------------
        # 3. Knowledge Graph Gene / Disease Exploration
        # -------------------------------------------------------------
        queried_genes = entities["genes"]
        if target_variant and target_variant.get("gene_symbol") and target_variant.get("gene_symbol") not in queried_genes:
            queried_genes.append(target_variant.get("gene_symbol"))

        if queried_genes and self.registry.graph:
            for g_sym in queried_genes[:2]:
                g_node = self.registry.graph.node("Gene", g_sym)
                if g_node:
                    diseases = self.registry.graph.neighbors(g_sym, "ASSOCIATED_WITH")
                    d_names = [d.get("name") or d["id"] for d in diseases]
                    kg_desc = f"KNOWLEDGE GRAPH: Gene {g_sym} is causally associated with: {', '.join(d_names) if d_names else 'No direct diseases registered'}."
                    retrieved_parts.append(kg_desc)
                    citations.append(Citation(
                        source_type="Knowledge Graph",
                        identifier=g_sym,
                        title=f"Gene Node: {g_sym}",
                        summary=f"Curated causal associations in Genomera Knowledge Graph: {', '.join(d_names[:3])}",
                        reliability="High",
                    ))

        # Context Summary
        context_summary = {
            "patient_id": patient_id,
            "analysis_id": analysis_id,
            "target_variant": target_variant.get("variant_id") if target_variant else None,
            "target_gene": target_variant.get("gene_symbol") if target_variant else None,
            "hpo_count": len(hpos_to_use),
            "citations_count": len(citations),
        }

        return RetrievedContext(
            intent=intent,
            patient_context_text="\n".join(patient_parts) if patient_parts else "No specific patient context linked.",
            retrieved_data_text="\n\n".join(retrieved_parts) if retrieved_parts else "No specific genomic records retrieved for this query.",
            citations=citations,
            detected_entities=entities,
            has_sufficient_context=bool(retrieved_parts or patient_parts),
            context_summary=context_summary,
        )
