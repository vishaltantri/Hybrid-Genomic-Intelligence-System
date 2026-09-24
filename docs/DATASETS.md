# Datasets — What Data This Project Uses and Where It Comes From

*Every dataset below is real, publicly accessible, and linked. Synthetic/seed data is clearly marked.*

---

## Real, downloaded data (used in the running system)

| Dataset | What it gives us | Where | License / access |
|---|---|---|---|
| **HPO** (Human Phenotype Ontology) | 20,482 disease-symptom terms + the tree linking them | `purl.obolibrary.org/obo/hp/hp.obo` | Open (CC-BY style) |
| **phenotype.hpoa** | Disease→symptom annotations for 12,880+ diseases | `purl.obolibrary.org/obo/hp/hpoa/phenotype.hpoa` | Open |
| **Orphanet** (Orphadata) | Rare disease names, prevalence, inheritance, genes | `orphadata.com` | Free registration |
| **ClinVar** | Variant→disease links (weekly TSV) | `ncbi.nlm.nih.gov/clinvar` | Public domain |
| **PharmGKB / CPIC** | Gene→drug safety pairs and dosing guidelines | `pharmgkb.org`, `cpicpgx.org` | CC-BY-SA |
| **IndiGenomes / GenomeIndia** | Indian population allele frequencies (used for CYP2C19, CYP2D6, G6PD, carrier rates) | `clingen.igib.res.in/indigen` | Academic access |
| **NFHS-5** | State-wise consanguinity (cousin-marriage) rates | `dhsprogram.com/data` | Free registration |
| **PubMed E-utilities** | Live literature feed for the self-updating pipeline | `eutils.ncbi.nlm.nih.gov` | Free API |

## Seed data (built by hand for this project — no public source exists)

| File | What | Why hand-made |
|---|---|---|
| `data/seeds/clinical_ner_seed.jsonl` | 25 hand-labelled Hindi/Hinglish clinical sentences | **No Indian clinical NER corpus exists anywhere.** This is the honest seed; the active-learning loop grows it. |
| `data/seeds/clinical_ner_augmented.jsonl` | 400 template-generated sentences with exact gold spans | Data augmentation for the NER train |
| `data/seeds/india_symptom_dictionary.csv` | Regional symptom phrases → HPO terms (e.g., "पीलिया" → jaundice) | No Indian synonym dictionary exists |
| `data/seeds/seed_cases.jsonl` | 12 enriched example cases | Demo + regression testing |
| `data/seeds/synthetic_cases.jsonl` | 400 generated cases over real disease profiles | Benchmarking (real profiles, realistic 10–12 findings each) |
| `data/seeds/pgx_indian_frequencies.csv` | CYP2C19/CYP2D6/G6PD frequencies in Indian populations | No pre-merged Indian pharmacogenomic table exists — **this merge is a novel contribution** |
| `data/seeds/state_consanguinity.csv` | Consanguinity rates per Indian state (from NFHS-5) | Scattered across survey tables; compiled here |
| `data/seeds/community_founders.csv` | Community founder effects (e.g., Gond–sickle cell) | Compiled from published literature |
| `data/seeds/confirmatory_tests.csv` | First-line + genetic confirmation tests per disease | Curated |
| `data/seeds/carrier_lookup.csv` | Carrier frequencies by disease × community | Compiled from PubMed studies |

## What is simulated, and why

- **National dashboard numbers** — India's official rare disease registry (ICMR NRROID) is not publicly downloadable. Dashboard records are generated from the knowledge graph's prevalence figures and geo-tagged across states, and every view is labelled "simulated."
- **Federated learning hospitals** — "hospitals" are synthetic non-IID partitions of the clinical data. The machinery (partitioning, local training, DP noise, secure aggregation) is real; the sites are simulated.
- **ASHA voice recordings** — Common Voice/IndicVoices cover mainstream accents; genuinely rural dialect audio doesn't exist publicly. The ASR pipeline is wired and testable; a small (1–2 h) field recording would make it real.

## Numbers at a glance

- 20,482 ontology terms · 12,880+ diseases · 286,000+ symptom links · 539 same-as disease merges
- Knowledge graph validates with **0 dangling references**
- All third-party data parsers live in `ml_services/etl/` — one command (`make etl && make kg-build`) rebuilds everything from source
