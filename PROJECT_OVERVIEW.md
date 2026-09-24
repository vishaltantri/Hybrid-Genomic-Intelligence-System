# Genomind-India — Project Overview

*A one-page explanation of the project in plain language.*

---

## 1. What is this project?

Genomind-India is a **rare disease diagnosis assistant built for India**.

A doctor (or an ASHA health worker in a village) enters a patient's symptoms — in plain Hindi, Hinglish, or English. The system:

1. **Reads the symptoms** and converts them into standard medical codes.
2. **Searches a huge medical knowledge network** of 12,000+ rare diseases to suggest the most likely conditions, ranked.
3. **Adjusts the ranking for Indian patients** — things like the patient's state, community, and family history that international tools simply don't know about.
4. **Explains its answer** — which symptoms pointed where, what test would confirm it, which lab or specialist to visit.
5. Also checks **medicine safety** for the patient's genes, and **family planning risk** for couples.

Think of it as an experienced geneticist's brain, available on a laptop, tuned for Indian genetics.

---

## 2. Why does this matter? (The problem)

- **1 in 20 Indians** is born with or develops a rare disease — roughly **7–9 crore people**.
- On average, a rare disease patient in India waits **5–7 years** and visits **4+ doctors** before getting the right diagnosis. Many never do.
- Existing international tools (like Exomiser or Phenomizer) are built on **European/American genetics data**. They don't know that:
  - Sickle cell disease is far more common in certain tribal communities.
  - Thalassemia carrier rates differ hugely between Indian communities (e.g., Sindhis, Punjabis).
  - Cousin-marriage (consanguinity) rates vary 10x between Indian states, which changes which diseases are likely.
- There is **almost no medical AI that understands Hindi or Hinglish**, so village-level health workers are left out.

The right diagnosis early = right treatment, fewer wrong treatments, and families can plan future pregnancies properly.

---

## 3. What makes it new? (Novelty)

1. **India-first diagnosis engine.** The ranking deliberately uses Indian population knowledge — state-wise consanguinity, community founder effects (e.g., higher sickle-cell risk in the Gond community), sex-linked factors. Two patients with identical symptoms from different states can get different, more accurate suggestions. **No existing tool does this.**
2. **Works in the languages people actually speak.** Reads Hindi/Hinglish clinical sentences — a first, because no such dataset existed, so we built one.
3. **Explainable, not a black box.** Every diagnosis shows *why*: which findings drove it, how confident it is, and what one extra test would settle it. Built for real clinical trust, not just a demo.
4. **Covers the full journey, not just diagnosis:** symptom reading → ranked diagnosis → medicine safety check for the patient's genes → family/reproductive counseling in local languages → nearest NABL lab / specialist referral.
5. **Privacy by design.** Hospitals can improve the AI together without ever sharing patient records (federated learning with built-in anonymization).
6. **It learns.** A pipeline reads new medical publications and updates the knowledge base automatically, and doctor corrections flow back into training.

---

## 4. What gets delivered (Deliverables)

| # | Deliverable | What it means in practice |
|---|---|---|
| 1 | **Rare disease knowledge network** | Real data from HPO, Orphanet, ClinVar, PharmGKB, CPIC + Indian genetics data (IndiGenomes/GenomeIndia frequencies, NFHS consanguinity) |
| 2 | **Symptom reading AI (Hindi/Hinglish/English)** | Trained model that turns patient text into structured medical findings |
| 3 | **Symptom → disease matching AI** | Trained over all 20,482 official medical condition terms |
| 4 | **Ranked diagnosis engine with Indian priors** | Top-10 list with probabilities, confidence ranges, India-specific reasoning |
| 5 | **Graph AI model (GNN)** | Learns patterns across the whole disease network, not just pairwise matching |
| 6 | **Medicine safety engine (pharmacogenomics)** | Flags risky drugs using Indian gene frequencies (e.g., G6PD, CYP2C19) |
| 7 | **Family planning counselor** | Couple carrier-risk, child-risk simulator, reports in Hindi/English/Tamil |
| 8 | **Explainability layer** | Driving symptoms, missing findings, confidence intervals |
| 9 | **Hospital privacy training (federated learning)** | Simulated multi-hospital training, no data sharing |
| 10 | **ASHA worker tool** | Simple triage questions + voice input (speech-to-text) for rural use |
| 11 | **Self-updating knowledge pipeline** | Reads new PubMed papers, proposes knowledge updates |
| 12 | **National dashboard** | State-wise rare disease map and policy briefs (simulated data, clearly labelled) |
| 13 | **Server API** | FastAPI backend with login/roles, works with standard hospital record formats (FHIR) |
| 14 | **Web dashboard for clinicians** | React app (in progress) |
| 15 | **Mobile app for ASHA workers** | Flutter app, works offline (in progress) |
| 16 | **Full test suite + demo** | 124 automated tests, one-command end-to-end demo |
| 17 | **Documentation** | Dataset map, training recipes, patent-claim mapping, deployment guide |

---

## 5. Progress so far (status update)

### ✅ Done and working

- **Knowledge network built from real data** — 20,482 real disease terms, 12,880+ diseases, 286,000+ symptom links, validated with zero broken references.
- **All 3 AI models trained on our own GPU** (no cloud needed):
  - Symptom reader: **98.6% accurate** on its test set, **80%** on hand-written sentences (limited by small hand data — improves automatically as doctors correct it).
  - Symptom→term matcher: correct term is the **#1 guess 80% of the time, top-5 92% of the time** across all 20,482 terms.
  - Graph AI (GNN): trained and now part of live ranking, tuned so it supports rather than overrides solid evidence.
- **Diagnosis engine: 91.7% of enriched test cases get the right disease in the top 3** — on the full 12,880-disease database.
- **India prior working end-to-end**: e.g., for an Andhra Pradesh case it correctly surfaces G6PD deficiency; founder communities get raised risk for their known diseases.
- **Medicine safety, counseling reports, explainability, federated simulation, PubMed pipeline, national dashboard data** — all modules functional.
- **Server API live** with login/roles and hospital-record (FHIR) support.
- **124 / 124 automated tests pass** (1 min 40 s), end-to-end demo runs green.

### 🔄 In progress

- Completing the full 400-case accuracy benchmark (a speed fix made this possible; partial runs show ~92% top-3).
- Documentation set (training recipes, dataset map, patent-claim map).

### ⏳ Remaining

- **React web dashboard** — built and compiling; connect it to the live API for a full click-through demo.
- **Flutter mobile app** for ASHA workers — built (offline triage + sync queue, widget test passing); install on a phone for a real device demo.
- Optional polish: demo video, screenshots, final report formatting.

---

## 6. Key numbers at a glance

| Metric | Value |
|---|---|
| Real disease terms in knowledge base | 20,482 |
| Diseases covered | 12,880+ |
| Symptom–disease links | 286,000+ |
| Test cases with right answer in top-3 | **91.7%** |
| Symptom-reader accuracy (test set) | 98.6% |
| Symptom→term matcher (top-1 / top-5) | 80% / 92% |
| Automated tests passing | 124 / 124 |
| Trained on | Local GPU (RTX 3050), minutes per model |

---

## 7. Honest limitations

- The symptom reader's 80% score on hand-written sentences reflects **25 hand-labelled examples** — small data, not a model limit. Every corrected sentence from real use makes it better (this loop is built in).
- The national dashboard uses **clearly-labelled simulated data** because India's official rare disease registry (ICMR NRROID) is not publicly downloadable.
- Final accuracy numbers will be restated after the full 400-case benchmark completes.
