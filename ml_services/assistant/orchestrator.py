"""Phase 28: the AI Assistant as orchestrator.

`infer_context` decides, from the user's message and the selected case, which already-implemented Genomera sources to
ground the answer on (diagnosis intelligence, PGx, reproductive, pedigree, Digital Twin, literature, knowledge graph).
It only *selects* sources; the data itself is read server-side through the same permission-checked builders as an explicit
request, so inference can never widen access: sources the caller may not use are skipped.

`verify_answer` is the output guardrail. Clinical specifics in the model's text (variant notation, PMIDs, DOIs, ClinVar
accessions) that do not appear in the context the model was given are replaced, and provider names are scrubbed.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# message keyword -> payload flag. Patterns are deliberately plain; they only choose which real data to attach.
RULES: Dict[str, re.Pattern] = {
    "include_diagnosis_intel": re.compile(r"\b(diagnos\w*|differential|ranked?|ranking|why .*first|top candidate|likely (disease|condition))\b", re.I),
    "include_pgx": re.compile(r"\b(drugs?|medicines?|medicat\w*|prescri\w*|pgx|pharmaco\w*|metaboli[sz]er|clopidogrel|warfarin|cyp\d\w+|dose|dosing|adverse reaction)\b", re.I),
    "include_repro": re.compile(r"\b(carrier|recurrence|reproduct\w*|pregnan\w*|child(ren)?|baby|offspring|couple|prenatal|risk to (a )?future)\b", re.I),
    "include_pedigree": re.compile(r"\b(pedigree|inherit\w*|segregat\w*|family|parents?|mother|father|sibling|de novo|autosomal|x-linked|trio)\b", re.I),
    "include_twin": re.compile(r"\b(digital twin|twin|scenario|baseline|what changed|what[- ]if|timeline)\b", re.I),
    "include_evidence": re.compile(r"\b(literature|publications?|papers?|pubmed|pmid|study|studies|references?|cite|citations?|evidence for)\b", re.I),
}
NEEDS_PATIENT = {"include_diagnosis_intel", "include_pgx", "include_repro", "include_pedigree", "include_twin"}
PERMISSION = {"include_diagnosis_intel": "diagnosis:run", "include_pgx": "pgx:read", "include_repro": "reproductive:read",
              "include_pedigree": "pedigree:read", "include_twin": "twin:read", "include_evidence": "evidence:read"}


def link_graph_entity(registry, message: str) -> Optional[str]:
    """First gene symbol or disease name in the message that really exists in the knowledge graph (as a Type::id key)."""
    g = registry.graph
    for tok in dict.fromkeys(re.findall(r"\b[A-Z][A-Z0-9]{2,9}\b", message)):
        if g.node("Gene", tok):
            return f"Gene::{tok}"
    low = message.lower()
    for d in g.by_type("Disease"):
        name = (d.get("name") or "").lower()
        if len(name) >= 5 and name in low:
            return f"Disease::{d['id']}"
    return None


def infer_context(registry, message: str, patient_id: Optional[str], has_perm, already: Dict[str, bool]) -> Tuple[Dict[str, object], List[str]]:
    """Returns (flags to switch on, human-readable list of sources chosen). Never raises for a missing permission: skips it."""
    flags: Dict[str, object] = {}
    used: List[str] = []
    for flag, pat in RULES.items():
        if already.get(flag) or not pat.search(message):
            continue
        if flag in NEEDS_PATIENT and not patient_id:
            continue
        if not has_perm(PERMISSION[flag]):
            continue
        flags[flag] = True
        used.append(flag.replace("include_", "").replace("_", " "))
    if not already.get("graph_node") and has_perm("kg:read"):
        key = link_graph_entity(registry, message)
        if key:
            flags["graph_node"] = key
            used.append(f"knowledge graph ({key})")
    return flags, used


# --------------------------------------------------------------------------- output verification

_PROTEIN = re.compile(r"p\.\(?[A-Z][a-z]{2}\d+(?:[A-Z][a-z]{2}|Ter|\*|=)(?:fs\*?\d*)?\)?")
_CDNA = re.compile(r"c\.\d+(?:[+-]\d+)?(?:_\d+(?:[+-]\d+)?)?(?:[ACGT]>[ACGT]|del[ACGT]*|dup[ACGT]*|ins[ACGT]+)")
_PMID = re.compile(r"PMID:?\s*(\d{5,9})", re.I)
_DOI = re.compile(r"\b10\.\d{4,9}/[^\s)\]>,;]+")
_CLINVAR = re.compile(r"\b(?:VCV|RCV|SCV)\d{6,12}\b")
_PROVIDER = re.compile(r"\b(groq|openai|gpt-oss|llama|meta ai|qwen|anthropic|claude|chatgpt|mixtral|mistral)\b", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[()\s*]", "", s)


def verify_answer(answer: str, context_text: str, citation_ids: List[str]) -> Tuple[str, List[dict]]:
    """Replace unsupported specifics. A specific counts as supported only if it occurs in the context given to the model."""
    flags: List[dict] = []
    ctx = context_text or ""
    ctx_norm = _norm(ctx)
    known_ids = {re.sub(r"\D", "", c) for c in citation_ids if "pmid" in c.lower()} | {m.group(1) for m in _PMID.finditer(ctx)}

    def guard(pattern, kind, supported, repl):
        nonlocal answer

        def _sub(m):
            tok = m.group(0)
            if supported(tok, m):
                return tok
            flags.append({"type": kind, "text": tok})
            return repl
        answer = pattern.sub(_sub, answer)

    guard(_PROTEIN, "variant_notation", lambda t, m: _norm(t) in ctx_norm, "[protein change not in case data]")
    guard(_CDNA, "variant_notation", lambda t, m: _norm(t) in ctx_norm, "[cDNA change not in case data]")
    guard(_PMID, "citation", lambda t, m: m.group(1) in known_ids, "[PMID not retrieved]")
    guard(_DOI, "citation", lambda t, m: t.rstrip(".") in ctx, "[DOI not retrieved]")
    guard(_CLINVAR, "accession", lambda t, m: t in ctx, "[accession not in case data]")
    n_provider = len(_PROVIDER.findall(answer))
    if n_provider:
        answer = _PROVIDER.sub("the Genomera AI Assistant", answer)
        flags.append({"type": "provider_reference", "text": f"{n_provider} removed"})
    if any(f["type"] != "provider_reference" for f in flags):
        n = sum(1 for f in flags if f["type"] != "provider_reference")
        answer += (f"\n\nVerification: {n} detail(s) were removed because they do not appear in the case data or retrieved evidence "
                   "given to the assistant. Check the source records for the exact values.")
    return answer, flags
