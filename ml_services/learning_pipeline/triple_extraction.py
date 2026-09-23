"""Literature triple extraction for KG updates (Module 10, patent claim #11).

Extracts (subject, predicate, object) triples from abstracts — gene→disease,
variant→disease, phenotype→disease, drug→gene — using curated patterns plus the project
lexicons (genes, diseases, drugs, HPO names). Every extracted triple becomes a *proposal*
with the supporting sentence and PMID; nothing is written to the KG without review.

Why rules first: a rare-disease KG cannot tolerate hallucinated edges, and rule output is
auditable ("show me the sentence"). An optional LLM/BioMistral extractor can be plugged in
later and judged against this rule baseline.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from ml_services.config import SEEDS_DIR
from ml_services.utils import read_csv_rows

CAUSAL_PATTERNS = [
    r"(?P<subj>[A-Z0-9\-]{2,15})\s+(?:gene\s+)?(?:mutations?|variants?|deletions?|defects?)\s+"
    r"(?:cause|causes|causing|lead to|leads to|result in|results in|are associated with|associated with)\s+"
    r"(?P<obj>[A-Za-z0-9'\- ]{3,60})",
    r"(?P<obj>[A-Za-z'\- ]{3,60})\s+is\s+caused\s+by\s+(?:mutations?|variants?|defects?)\s+in\s+(?P<subj>[A-Z0-9\-]{2,15})",
    r"(?P<subj>[A-Z0-9\-]{2,15})\s+is\s+(?:a\s+)?(?:causative|responsible)\s+(?:gene\s+)?for\s+(?P<obj>[A-Za-z'\- ]{3,60})",
]
PHENOTYPE_PATTERNS = [
    r"(?:patients?|children|individuals)\s+(?:present|presented|show|showed|exhibit|exhibited|have|had)\s+"
    r"(?P<obj>[A-Za-z0-9'\- ,]{4,80})",
]
DISEASE_MENTION_PATTERN = r"(?P<obj>[A-Za-z0-9'\- ]{4,60}(?:disease|syndrome|disorder|deficiency|anemia|anaemia|thalass[a]?emia|atrophy|dystrophy|fibrosis))"
DRUG_GENE_PATTERN = r"(?P<subj>[A-Za-z\-]{4,20})\s+(?:is |are )?metaboli[sz]ed by\s+(?P<obj>CYP\d[A-Z0-9]{1,3}|TPMT|NUDT15|DPYD|G6PD|SLCO1B1)"
CONSANGUINITY_PATTERN = r"consanguinity.{0,80}?(?P<num>\d{1,2}(?:\.\d+)?)\s?%"

DISEASE_HINTS = ("disease", "syndrome", "disorder", "deficiency", "anemia", "anaemia",
                 "thalassemia", "thalassaemia", "atrophy", "dystrophy", "fibrosis",
                 "phenylketonuria", "mucopolysaccharidosis", "hemoglobinopathy")
NEGATION_CUES = ("not ", "no evidence", "failed to", "did not", "unlikely", "no association")


class TripleExtractor:
    def __init__(self):
        self.genes = {r["gene_symbol"] for r in read_csv_rows(SEEDS_DIR / "orphanet_gene_disease.csv")
                      if r.get("gene_symbol")}
        self.diseases = {r["disease_name"].lower(): r["disease_id"]
                         for r in read_csv_rows(SEEDS_DIR / "orphanet_rare_diseases.csv")}
        self.drugs = {r["drug_name"].lower() for r in read_csv_rows(SEEDS_DIR / "drugs.csv")}
        from ml_services.etl.graph_store import load_processed

        graph = load_processed()
        self.hpo_names = {n["id"]: n["name"].lower() for n in graph.by_type("Hpo")} if graph else {}

    # ------------------------------ extraction ------------------------------

    def extract_from_abstract(self, article: Dict) -> List[dict]:
        text = f"{article.get('title', '')}. {article.get('abstract', '')}"
        sentences = re.split(r"(?<=[.!?])\s+", text)
        triples: List[dict] = []

        for sentence in sentences:
            low = sentence.lower()
            if any(cue in low for cue in NEGATION_CUES):
                continue
            for pattern in CAUSAL_PATTERNS:
                for m in re.finditer(pattern, sentence, re.IGNORECASE):
                    subj = m.group("subj").strip().upper()
                    obj = m.group("obj").strip(" .;,")
                    if subj in self.genes:
                        triples.append(self._triple("Gene", subj, "ASSOCIATED_WITH", "Disease", obj,
                                                    sentence, article, 0.8))
                    elif any(h in obj.lower() for h in DISEASE_HINTS):
                        triples.append(self._triple("Gene", subj, "ASSOCIATED_WITH", "Disease", obj,
                                                    sentence, article, 0.5))
            for m in re.finditer(DRUG_GENE_PATTERN, sentence, re.IGNORECASE):
                drug = m.group("subj").strip().lower()
                if drug in self.drugs:
                    triples.append(self._triple("Drug", drug, "METABOLIZED_BY", "Gene",
                                                m.group("obj").strip().upper(), sentence, article, 0.85))
            for pattern in PHENOTYPE_PATTERNS:
                for m in re.finditer(pattern, sentence, re.IGNORECASE):
                    phenotype_text = m.group("obj").strip(" .;,")
                    matched_hpo = self._match_hpo(phenotype_text)
                    if matched_hpo:
                        triples.append(self._triple("Phenotype", matched_hpo, "PRESENT_IN", "Disease",
                                                    self._match_disease(sentence) or "unspecified",
                                                    sentence, article, 0.6))
            for m in re.finditer(DISEASE_MENTION_PATTERN, sentence):
                disease_name = m.group("obj").strip(" .;,").lower()
                if disease_name in self.diseases:
                    triples.append(self._triple("Disease", disease_name, "MENTIONED_WITH", "Population",
                                                self._region_from(sentence), sentence, article, 0.55))
            m = re.search(CONSANGUINITY_PATTERN, sentence, re.IGNORECASE)
            if m:
                triples.append(self._triple("Population", "consanguinity", "HAS_RATE", "Region",
                                            f"{m.group('num')}%", sentence, article, 0.7))
        return self._dedupe(triples)

    def extract_batch(self, articles: List[Dict]) -> dict:
        proposals: List[dict] = []
        for art in articles:
            proposals.extend(self.extract_from_abstract(art))
        for i, p in enumerate(proposals):
            p["proposal_id"] = f"KGPROP-{i+1:04d}"
            p["status"] = "pending_review"
        return {
            "n_articles": len(articles),
            "n_proposals": len(proposals),
            "proposals": proposals,
            "by_predicate": _count_by(proposals, "predicate"),
            "note": "Proposals require expert review before insertion into the knowledge graph.",
        }

    # ------------------------------ helpers ------------------------------

    def _triple(self, stype, subj, predicate, otype, obj, sentence, article, confidence) -> dict:
        return {
            "subject_type": stype, "subject": subj, "predicate": predicate,
            "object_type": otype, "object": obj,
            "confidence": confidence,
            "evidence_sentence": sentence.strip()[:400],
            "pmid": article.get("pmid", ""), "title": article.get("title", "")[:200],
            "journal": article.get("journal", ""), "year": article.get("year", ""),
            "url": article.get("url", ""),
        }

    def _match_hpo(self, text: str) -> Optional[str]:
        low = text.lower()
        for hpo_id, name in self.hpo_names.items():
            if name and name in low:
                return hpo_id
        return None

    def _match_disease(self, sentence: str) -> Optional[str]:
        low = sentence.lower()
        for name, did in self.diseases.items():
            if name in low:
                return name
        return None

    def _region_from(self, sentence: str) -> str:
        low = sentence.lower()
        for region in ("northeast indian", "north indian", "south indian", "central indian",
                       "tribal", "india"):
            if region in low:
                return region
        return "unspecified"

    def _dedupe(self, triples: List[dict]) -> List[dict]:
        seen, out = set(), []
        for t in triples:
            key = (t["subject"], t["predicate"], t["object"])
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
        return out


def _count_by(items: List[dict], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for i in items:
        counts[i[key]] = counts.get(i[key], 0) + 1
    return counts


if __name__ == "__main__":
    demo_articles = [
        {"pmid": "99990001", "title": "ATP7B mutations cause Wilson disease in Indian children",
         "abstract": ("Background: Wilson disease is caused by mutations in ATP7B. "
                      "Methods: We studied 45 Indian children with consanguinity in 22% of families. "
                      "Results: Patients presented with jaundice and hepatic dysfunction. "
                      "Clopidogrel is metabolized by CYP2C19 in adults studied concurrently."),
         "journal": "Indian J Pediatr", "year": "2025", "url": "https://pubmed.ncbi.nlm.nih.gov/99990001/"},
    ]
    result = TripleExtractor().extract_batch(demo_articles)
    print(f"Proposals: {result['n_proposals']}  by predicate: {result['by_predicate']}")
    for p in result["proposals"]:
        print(f"\n  [{p['proposal_id']}] {p['subject']} --{p['predicate']}--> {p['object']} "
              f"(conf {p['confidence']})")
        print(f"    evidence: {p['evidence_sentence'][:110]}...")
