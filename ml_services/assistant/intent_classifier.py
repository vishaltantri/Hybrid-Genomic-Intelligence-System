"""Intent Classification and Clinical Routing for Genomera AI Assistant (Phase 3C).

Determines user intent to steer targeted retrieval across Genomera systems:
- VARIANT_EXPLANATION: questions about specific variants, rankings, prioritizations
- ACMG_EXPLANATION: questions on ACMG/AMP rules, criteria (PVS1, PM2, etc.), classifications
- DIAGNOSIS_REASONING: questions about differential diagnosis rankings, top diseases, probabilities
- PHENOTYPE_REASONING: questions about patient symptoms, HPO terms, feature matches
- GENE_DISEASE_ASSOCIATION: questions about genes, disease mechanisms, inheritance modes
- PGX_QUESTION: questions on drug metabolism, CPIC guidelines, star alleles
- REPRODUCTIVE_QUESTION: questions on carrier screening, couple risks, consanguinity
- KG_EXPLORATION: questions navigating knowledge graph connections
- CASE_SUMMARY: request for comprehensive clinical summary of the selected case
- PATIENT_FRIENDLY_EXPLANATION: requests to simplify clinical findings for patient communication
- GENERAL_GENOMICS: general genetic/medical queries not requiring specialized case retrieval
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


INTENT_PATTERNS = [
    ("ACMG_EXPLANATION", [
        r"\bacmg\b", r"\bamp\b", r"\bpvs1\b", r"\bpm\d\b", r"\bps\d\b", r"\bpp\d\b",
        r"\bba1\b", r"\bbs\d\b", r"\bbp\d\b", r"criteria", r"classification evidence",
        r"pathogenicity criteria"
    ]),
    ("VARIANT_EXPLANATION", [
        r"why.*ranked first", r"why.*top variant", r"top variant", r"this variant",
        r"variant.*ranked", r"variant.*score", r"c\.\d+", r"p\.[A-Z][a-z]{2}\d+",
        r"rs\d+", r"zygosity", r"cadd", r"allele frequency", r"indigenomes",
        r"genomeindia", r"clinvar"
    ]),
    ("DIAGNOSIS_REASONING", [
        r"why.*ranked.*disease", r"why.*top diagnosis", r"differential", r"diagnosis",
        r"probability", r"confidence.*disease", r"resnik", r"phenomizer",
        r"prior probability", r"founder risk"
    ]),
    ("PHENOTYPE_REASONING", [
        r"\bhpo\b", r"phenotype", r"symptom", r"sign", r"presentation",
        r"features.*support", r"clinical feature", r"overlap"
    ]),
    ("PGX_QUESTION", [
        r"\bpgx\b", r"pharmacogenom", r"drug", r"metabolizer", r"cpic", r"star allele",
        r"\*2\b", r"\*3\b", r"\*4\b", r"clopidogrel", r"warfarin", r"codeine"
    ]),
    ("REPRODUCTIVE_QUESTION", [
        r"carrier", r"couple risk", r"consanguin", r"pedigree", r"prenatal",
        r"recurrence risk", r"punnett", r"offspring"
    ]),
    ("CASE_SUMMARY", [
        r"summarize.*case", r"case summary", r"overview.*case", r"clinical summary",
        r"patient summary", r"briefing"
    ]),
    ("PATIENT_FRIENDLY_EXPLANATION", [
        r"patient[- ]friendly", r"explain.*for (a )?patient", r"simple terms",
        r"layman", r"easy to understand", r"family"
    ]),
    ("GENE_DISEASE_ASSOCIATION", [
        r"gene", r"inheritance", r"autosomal", r"x-linked", r"mechanism",
        r"function of", r"mutation"
    ]),
    ("KG_EXPLORATION", [
        r"knowledge graph", r"graph connection", r"node", r"edge", r"network"
    ]),
]


def detect_intent(query: str) -> str:
    """Classify user query into a primary intent category."""
    q = query.lower().strip()
    
    for intent, patterns in INTENT_PATTERNS:
        for p in patterns:
            if re.search(p, q):
                return intent
                
    return "GENERAL_GENOMICS"


def extract_entities_from_query(query: str) -> Dict[str, List[str]]:
    """Extract gene symbols, HPO IDs, variant tokens, and languages from query text."""
    q = query.strip()
    
    # Gene symbols (all caps 2-6 chars or common genes)
    common_genes = {
        "ATP7B", "HBB", "BRCA1", "VHL", "CFTR", "PAH", "SMN1", "ATM", "GLA",
        "SGCA", "DMD", "DMPK", "CYP2C19", "CYP2D6", "CYP2C9", "G6PD", "TPMT",
        "NUDT15", "VKORC1", "MTHFR", "CYP21A2", "FMR1", "PMP22", "RHO", "COL1A1"
    }
    found_genes = [g for g in common_genes if re.search(rf"\b{g}\b", q, re.IGNORECASE)]
    
    # HPO terms (HP:XXXXXXX)
    found_hpos = re.findall(r"\bHP:\d{7}\b", q, re.IGNORECASE)
    found_hpos = [h.upper() for h in found_hpos]
    
    # Language preference
    is_hindi = bool(re.search(r"\bhindi\b|हिंदी|हिन्दी", q, re.IGNORECASE))
    
    # Patient friendly
    is_patient_friendly = bool(re.search(r"patient[- ]friendly|for (a )?patient|layman|simple language", q, re.IGNORECASE))
    
    return {
        "genes": found_genes,
        "hpo_ids": found_hpos,
        "is_hindi": is_hindi,
        "is_patient_friendly": is_patient_friendly,
    }
