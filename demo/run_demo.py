"""GENOMIND-INDIA end-to-end demo.

Runs one realistic Indian patient journey through every module in the platform:

    free-text / ASR transcript
        -> M1 code-mixed clinical NER
        -> M2 HPO phenotype mapping (incl. Indian synonym dictionary)
        -> M4 differential diagnosis + India population prior + Bayesian uncertainty
        -> M7 explainability (attribution, graph attention, similar cases)
        -> M5 pharmacogenomic risk engine (Indian allele frequencies)
        -> M6 reproductive / carrier counselling + Punnett
        -> multilingual report generation
        -> M9 ASHA triage + offline record
        -> M10 active-learning queue
        -> M8 federated learning round (simulated hospitals)

Usage:
    python -m demo.run_demo              # human-readable walkthrough
    python -m demo.run_demo --json out.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml_services import config

REPORTS = config.REPORTS_DIR

BANNER = "=" * 78


def rule(title: str) -> None:
    print(f"\n{BANNER}\n{title}\n{BANNER}")


# --------------------------------------------------------------------------- #
# The patient: an 8-month-old from Tamil Nadu, consanguineous parents.
# (Composite/synthetic record - no real patient data is used anywhere.)
# --------------------------------------------------------------------------- #

PATIENT = {
    "patient_id": "DEMO-0001",
    "sex": "F",
    "age_months": 8,
    "state": "Tamil Nadu",
    "community": "Nadar",
    "language": "ta-en",
}

TRANSCRIPT = (
    "Bachche ka weight nahi badh raha, 8 mahine ka hai. Kuch bhi khilaao, "
    "weight gain nahi hota. Bahut kamzor hai. Kamar se pair tak sujan hai, "
    "aur thakan bahut rehti hai. Bar bar bukhar aata hai. "
    "She has not started sitting independently and poor weight gain since 3 months."
)

# Parents for the reproductive-counselling stage (Module 6).
PARTNER_A = {"id": "father", "sex": "M", "age": 29, "state": "Tamil Nadu", "community": "Nadar",
             "relationship": "first_cousins"}
PARTNER_B = {"id": "mother", "sex": "F", "age": 26, "state": "Tamil Nadu", "community": "Nadar",
             "relationship": "first_cousins"}


def stage_1_ner() -> dict:
    rule("MODULE 1 - Multilingual clinical NER (code-mixed Hindi/Hinglish/English)")
    from ml_services.nlp.clinical_ner import get_ner

    ner = get_ner()
    result = ner.extract(TRANSCRIPT)
    print(f"engine            : {result.get('engine')}")
    print(f"token-level LID   : {result.get('lid_counts')}")
    print(f"code-mixed        : {result.get('is_code_mixed')}"
          f"  (romanised-Hindi tokens: {result.get('romanised_hindi_tokens')})")
    print("\nEntities (symptom / duration / age / lab / family history):")
    for e in result.get("entities", []):
        neg = " [NEGATED]" if e.get("negated") else ""
        dur = f"  onset={e['duration']}" if e.get("duration") else ""
        hpo = f"  -> {e['hpo_id']}" if e.get("hpo_id") else ""
        print(f"  - {e['text']:<34} {e['label']:<14} {e['source']:<8}"
              f"conf={e.get('confidence', 0):.2f}{hpo}{dur}{neg}")
    if result.get("negated_symptoms"):
        print(f"\nnegated (must NOT be treated as findings): {result['negated_symptoms']}")
    return result


def stage_2_hpo(ner_result: dict) -> dict:
    rule("MODULE 2 - HPO phenotype mapper (English + Indian synonym dictionary)")
    from ml_services.nlp.hpo_mapper import HPOMapper

    mapper = HPOMapper()
    mapped = mapper.map_ner_result(ner_result)
    print("phrase -> HPO term (confidence, evidence):")
    for item in mapped.get("hpo_profile", []):
        print(f"  {item['hpo_id']:<12} {item['hpo_name']:<44} {item['confidence']:.2f}"
              f"  via {item['method']} ('{item['evidence_text']}')")
    print(f"\nmapped HPO terms  : {mapped['hpo_ids']}")
    if mapped.get("unmapped_symptoms"):
        print(f"unmapped phrases  : {mapped['unmapped_symptoms']}  (queued for Module 10 labelling)")
    print(f"low-confidence    : {mapped.get('low_confidence_count', 0)} (routed to expert review)")
    return mapped


def stage_4_diagnosis(hpo_ids: list[str]) -> dict:
    rule("MODULE 4 - Differential diagnosis (HPO graph + Indian population prior)")
    from ml_services.graph_ai.gnn_diagnosis import DifferentialDiagnosisEngine

    engine = DifferentialDiagnosisEngine()
    dx = engine.diagnose(hpo_ids, PATIENT, top_k=5, explain=True)
    print(f"engine: {dx['engine']}\n")
    for i, r in enumerate(dx["results"], 1):
        ci = r.get("probability_ci") or [0, 0]
        pp = r.get("population_prior", {})
        jk = r.get("similarity_jackknife") or [0, 0]
        print(f"{i}. {r['disease_name']}  ({r['disease_id']})")
        print(f"   probability   : {r['probability'] * 100:5.1f}%"
              f"   95% CI [{ci[0] * 100:.1f}%, {ci[1] * 100:.1f}%]")
        print(f"   phenotype sim : {r['phenotype_similarity']:.3f}"
              f"  (jackknife [{jk[0]:.2f}, {jk[1]:.2f}])"
              f"   india prior x{pp.get('relative_weight', 1.0)}"
              f"  {'(re-ranked)' if pp.get('prior_applied_to_ranking') else '(phenotype decided)'}")
        print(f"   prevalence    : {pp.get('prevalence_per_100k', 0)}/100k"
              f"   consanguinity x{pp.get('consanguinity_multiplier', 1)}"
              f"   founder x{pp.get('founder_multiplier', 1)}   sex x{pp.get('sex_multiplier', 1)}")
        print(f"   genes         : {', '.join(r.get('genes', [])[:4]) or '-'}")
        print(f"   inheritance   : {r.get('inheritance', 'n/a')}")
        if r.get("driving_symptoms"):
            def _name(term: str) -> str:
                return (engine.graph.node("Hpo", term) or {}).get("name", term)
            print("   driven by     : " + ", ".join(
                f"{_name(d['patient_term'])} ({d['contribution']:.2f})"
                for d in r["driving_symptoms"][:4]))
        if r.get("missing_findings"):
            print(f"   missing       : {', '.join(m.get('hpo_name', '') for m in r['missing_findings'][:3])}")
        tests = r.get("confirmatory_tests") or {}
        if tests:
            print(f"   confirm tests : {', '.join(tests.get('first_line', [])[:2])}"
                  f" | genetic: {', '.join(tests.get('genetic', [])[:2])}")
        if pp.get("india_notes"):
            print(f"   india context : {pp['india_notes'][:96]}")
        print()
    ref = dx.get("referral") or {}
    if ref:
        print("nearest services for the top differential:")
        for s in (ref.get("specialists") or [])[:3]:
            print(f"  - {s.get('specialist', s.get('name', ''))}"
                  f"  @ {s.get('hospital', s.get('city', ''))}")
        for lab in (ref.get("labs") or [])[:3]:
            print(f"  - lab: {lab.get('lab_name', lab.get('name', ''))} ({lab.get('city', '')})")
    return dx


def stage_7_xai(hpo_ids: list[str]) -> dict:
    rule("MODULE 7 - Explainable AI layer")
    from ml_services.xai.explainability import ExplainabilityLayer

    xai = ExplainabilityLayer()
    bundle = xai.explain(text=TRANSCRIPT, hpo_ids=hpo_ids, patient_context=PATIENT, top_k=3)
    ex = bundle.get("explanation")
    if not ex:
        print("nothing to explain - no candidate diagnosis for these findings")
        return bundle
    ci = ex.get("probability_ci") or [0, 0]
    print(f"top diagnosis : {ex['disease_name']} ({ex['probability'] * 100:.1f}%,"
          f" 95% CI {ci[0] * 100:.1f}-{ci[1] * 100:.1f}%)")
    att = ex["attribution"]
    print(f"\nsymptom attribution ({att.get('method', '')})"
          f" - how much each finding supports the call (base score {att.get('base_score')}):")
    for s in att.get("attributions", [])[:6]:
        print(f"  {s['hpo_name']:<44} {s['contribution']:+.4f}"
              f"  ({s['weight_pct']:5.1f}% of evidence)"
              f"  without it: {s['score_without']:.3f}")

    cbr = ex["case_based_reasoning"]
    print(f"\ncase-based reasoning ({'FAISS' if xai.case_index._faiss is not None else 'cosine over embeddings'}"
          f", {len(cbr)} nearest confirmed Indian cases):")
    for c in cbr:
        dx_name = c.get("confirmed_diagnosis") or c.get("disease_name") or "(unlabelled)"
        print(f"  sim={c['similarity']:.4f}  {dx_name:<30}"
              f"  shared={c['n_shared']} finding(s)  {c.get('state', '')}/{c.get('community', '')}"
              f"  case={c.get('case_id')}")

    ga = ex["graph_attention"]
    print(f"\ngraph attention: {len(ga.get('nodes', []))} nodes, {len(ga.get('links', []))} links"
          f"  ({ga.get('note', '')[:64]}...)")
    for e in (ga.get("links") or [])[:5]:
        print(f"  {e['source']:<14} -[{e['relation']}]-> {e['target']:<14} w={e['weight']:.3f}")

    ta = ex.get("text_attention") or {}
    top_tokens = sorted(ta.get("tokens", []), key=lambda t: -t["weight"])[:8]
    if top_tokens:
        print("\ntext attention (BERTViz-ready, mapping confidences): " + ", ".join(
            f"{t['token']}({t['weight']:.2f})" for t in top_tokens))

    pm = ex.get("phenotype_map") or {}
    points = pm.get("points", [])
    if points:
        patient = next((p for p in points if p.get("kind") == "patient"), None)
        near = sorted((p for p in points if p.get("kind") == "disease"),
                      key=lambda p: (p["x"] - patient["x"]) ** 2 + (p["y"] - patient["y"]) ** 2)[:3] \
            if patient else []
        print(f"\nphenotype map ({pm.get('method')}): {len(points)} points projected; "
              f"closest diseases to the patient: {', '.join(p['label'] for p in near)}")

    print("\nplain-language narrative (Hindi) - first lines:")
    md = (ex.get("narrative") or {}).get("markdown", "")
    for line in [ln for ln in md.split("\n") if ln.strip()][:3]:
        print("  " + line[:150])
    return bundle


def stage_5_pgx() -> dict:
    rule("MODULE 5 - Pharmacogenomic risk engine (Indian allele frequencies)")
    from ml_services.pharmacogenomics.pgx_engine import PGxEngine

    pgx = PGxEngine()
    drugs = ["Warfarin", "Clopidogrel", "Carbamazepine", "Codeine", "Azathioprine", "Isoniazid"]
    result = pgx.check_drugs(drugs, state=PATIENT["state"], ethnicity="South Asian", sex=PATIENT["sex"])
    genes = {}
    for a in result["alerts"]:
        genes[a["gene"]] = a["phenotype_probabilities"]
    print("population-derived phenotype probabilities (Hardy-Weinberg on Indian allele freqs):")
    for gene, probs in genes.items():
        pretty = ", ".join(f"{k}={v * 100:.1f}%" for k, v in probs.items() if v > 0)
        print(f"  {gene:<10} {pretty}")
    print("\nper-drug guidance:")
    for a in result["alerts"]:
        print(f"  {a['drug']:<16} gene={a['gene']:<8} {a['severity'].upper():<10}"
              f" status={a['inferred_status']} ({a['probability_of_risk_status'] * 100:.1f}%)"
              f"  evidence={a['evidence_level']}")
        if a.get("recommendation"):
            print(f"      action: {a['recommendation'][:104]}")
        if a.get("alternatives"):
            print(f"      consider: {', '.join(a['alternatives'][:3])}")
        if a.get("allele_frequency") is not None:
            print(f"      {a['gene']} risk-allele frequency {a['allele_frequency']}"
                  f"  ({a.get('af_source', '')}; {a.get('af_match', '')})")
    high = [a for a in result["alerts"] if a["severity"] in ("high", "critical")]
    print(f"\n{len(high)} of {len(result['alerts'])} alerts are high/critical severity.")
    print(f"drugs with no PGx rule on file: {result.get('drugs_without_pgx_rule')}")
    return result


def stage_6_reproductive() -> dict:
    rule("MODULE 6 - Reproductive & prenatal genetic risk counselling")
    from ml_services.reproductive.carrier_counselor import CarrierCounselor
    from ml_services.reproductive.punnett import offspring_risk_from_carrier_probs, simulate_offspring

    counselor = CarrierCounselor()
    assessment = counselor.couple_assessment(PARTNER_A, PARTNER_B, top_n=6)
    print(f"consanguinity    : {'YES' if assessment.get('couple_consanguineous') else 'no'}"
          f"   (inbreeding coefficient F = {assessment.get('inbreeding_coefficient', 0):.4f})")
    print(f"state factor     : {assessment.get('state')} consanguinity rate "
          f"{assessment.get('state_consanguinity_rate', 0) * 100:.1f}%"
          f"  regional flag={assessment.get('regional_consanguinity_flag')}")
    print(f"overall risk band: {assessment.get('risk_band', '').upper()}")
    print("\ntop reproductive risks for this couple:")
    for r in assessment["top_risks"][:6]:
        ca = r["carrier_probability_partner_a"]["probability"]
        cb = r["carrier_probability_partner_b"]["probability"]
        print(f"  {r['disease_name']:<32} {r['gene']:<8} carrier p={ca:.4f} x {cb:.4f}"
              f"  -> affected child {r['child_affected_probability'] * 100:.4f}%"
              f"  1-in-{r['one_in_n_children'] if r['one_in_n_children'] else '-'}")

    top = assessment["top_risks"][0]
    print(f"\nPunnett / simulation for {top['disease_name']} (both parents assumed carriers):")
    sq = offspring_risk_from_carrier_probs(1.0, 1.0, mode="autosomal recessive")
    print(f"  affected {sq['affected_child_probability'] * 100:.1f}%  "
          f"carrier {sq['carrier_child_probability'] * 100:.1f}%  "
          f"unaffected non-carrier {sq['unaffected_child_probability'] * 100:.1f}%")
    sim = simulate_offspring(1.0, 1.0, n=20000,
                             inbreeding_coefficient=assessment.get("inbreeding_coefficient", 0.0))
    print(f"  20k simulated offspring: { {k: round(v, 4) for k, v in sim.items() if isinstance(v, (int, float))} }")

    print("\nrecommended screening:")
    for s in assessment.get("recommended_screening", [])[:4]:
        print(f"  - {s['condition']}: {s['test'][:88]}")
        print(f"      timing: {s['timing']}")
    if assessment.get("government_schemes"):
        print("\nfinancial / policy support to mention during counselling:")
        for s in assessment["government_schemes"][:3]:
            print(f"  - {s.get('name', '')}: {str(s.get('benefit', ''))[:88]}")
    return assessment


def stage_report(dx: dict, pgx: dict, repro: dict) -> dict:
    rule("REPORTS - multilingual clinician / family documents")
    from ml_services.reproductive.report_generator import (
        generate_carrier_report,
        generate_diagnosis_summary,
        generate_pgx_report,
    )

    out = {}
    for lang in ("en", "hi", "ta"):
        out[f"diagnosis_{lang}"] = generate_diagnosis_summary(dx, lang=lang)
    out["pgx_en"] = generate_pgx_report(pgx, lang="en")
    out["carrier_hi"] = generate_carrier_report(repro, lang="hi")

    REPORTS.mkdir(parents=True, exist_ok=True)
    saved = []
    for name, rep in out.items():
        p = REPORTS / f"demo_{name}.md"
        p.write_text(rep.get("markdown", ""), encoding="utf-8")
        saved.append(p.name)
    print("generated reports:")
    for s in saved:
        print(f"  reports/{s}")
    print("\nsample (Hindi family summary, first 12 lines):")
    for line in out["carrier_hi"].get("markdown", "").split("\n")[:12]:
        print("  " + line)
    return out


def stage_9_triage() -> dict:
    rule("MODULE 9 - ASHA worker / rural interface (offline triage)")
    from ml_services.asha.triage_engine import TriageEngine

    engine = TriageEngine()
    # Answers use the real ASHA questionnaire ids (Hindi yes/no + free values).
    answers = {
        "q_age": 8,
        "q_development": "nahi",      # not sitting / talking -> red flag
        "q_weakness": "haan",          # falls often, uses hands to rise -> red flag
        "q_feeding": "nahi",           # not gaining weight -> failure to thrive
        "q_pallor": "thoda",
        "q_recurrent_infections": "haan",
        "q_urine": "haan",             # dark urine -> hemolysis suspected (G6PD context)
        "q_family": "haan",
    }
    patient = {**PATIENT, "village": "Kallakurichi", "district": "Kallakurichi", "asha_id": "ASHA-TN-0142"}
    triage = engine.triage_answers(answers, patient=patient)
    print(f"triage colour   : {triage['triage_color'].upper()}"
          f"   ({len(triage.get('red_flags', []))} red flag(s))")
    print(f"findings sent   : {triage.get('reported_symptoms')}")
    print(f"hpo from ASHA   : {triage.get('hpo_ids')}")
    print(f"action (EN)     : {triage.get('recommendation', '')}")
    print(f"action (HI)     : {triage.get('recommendation_hi', '')}")
    print(f"refer to        : {triage.get('referral_facility', 'n/a')}")
    print("\nred flags tripped:")
    for f in triage.get("red_flag_details", []):
        print(f"  - {f['red_flag']}: {f['why']}")
    offline = engine.to_offline_record(triage)
    print(f"\noffline record (SQLite -> syncs on 2G/4G reconnect): "
          f"{json.dumps(offline, ensure_ascii=False)[:200]}...")
    print("\nreferral letter (Hindi, first 4 non-empty lines):")
    for line in [ln for ln in triage.get("referral_letter_hi", "").split("\n") if ln.strip()][:4]:
        print("  " + line[:118])
    return triage


def stage_10_learning() -> dict:
    rule("MODULE 10 - Continuous learning pipeline (PubMed -> reviewed KG update)")
    from ml_services.learning_pipeline.active_learning import ActiveLearningQueue
    from ml_services.learning_pipeline.drift import simulate_drift_example
    from ml_services.learning_pipeline.pubmed_scraper import fetch_pubmed
    from ml_services.learning_pipeline.triple_extraction import TripleExtractor

    feed = fetch_pubmed("Indian rare disease founder mutation genetics", retmax=5, offline=False)
    articles = feed.get("articles", [])
    print(f"pubmed E-utilities : {feed.get('n_total_articles', 0)} article(s)"
          f" (cached={feed.get('from_cache')})")
    extractor = TripleExtractor()
    triples: list[dict] = []
    for a in articles[:3]:
        print(f"  PMID {a.get('pmid')} ({a.get('year')}) {a.get('title', '')[:78]}")
        triples += extractor.extract_from_abstract(a)
    print(f"\nextracted {len(triples)} candidate KG edge(s) (awaiting expert review):")
    for t in triples[:5]:
        print(f"  {t.get('subject')} -[{t.get('relation')}]-> {t.get('object')}"
              f"  conf={t.get('confidence', 0):.2f}"
              f"  pmid={t.get('source_pmid') or t.get('pmid', '')}")

    drift = simulate_drift_example()
    print(f"\ndrift monitor      : {drift['overall_status']}"
          f"   retraining needed={drift['retraining_needed']}")
    for c in drift.get("checks", [])[:3]:
        print(f"  {c.get('metric', ''):<20} {c.get('status', '')}"
              f"  {('psi=' + format(c['psi'], '.3f')) if 'psi' in c else ''}")

    queue = ActiveLearningQueue()
    print(f"\nactive-learning queue: {len(queue.items)} item(s) awaiting expert labels"
          f"  (capacity {queue.capacity})")
    return {"triples": triples, "drift": drift, "queue_size": len(queue.items)}


def stage_8_federated() -> dict:
    rule("MODULE 8 - Federated learning across simulated hospitals (DP)")
    from ml_services.federated.fl_server import FederatedSimulator

    sim = FederatedSimulator(n_clients=6, seed=7)
    out_clients = [{"client_id": c.client_id, "archetype": c.archetype,
                    "n_cases": c.n, "note": c.note} for c in sim.clients]
    print("client data distribution (non-IID by state/community archetype):")
    for c in out_clients[:6]:
        print(f"  {c.get('client_id', ''):<13} n={c.get('n_cases', 0):<4}"
              f" {c.get('archetype', ''):<24} {c.get('note', '')[:54]}")
    report = sim.dataset_report()
    if report.get("note"):
        print(f"  non-IID check: {report['note'][:120]}")
    out = sim.train(rounds=8, algorithm="fedavg", sigma=0.35, clip_norm=0.5, secure_agg=True)
    print(f"\nrounds={out['rounds']}  clients={out['n_clients']}"
          f"  final mean client accuracy={out['final_mean_accuracy']:.3f}")
    print("  learning curve: " + " -> ".join(
        f"{h['mean_client_accuracy']:.3f}" for h in out.get("history", [])))
    dp = out.get("differential_privacy") or {}
    print(f"privacy budget   : sigma={dp.get('sigma')} clip={dp.get('clip_norm')}"
          f" epsilon={dp.get('epsilon_estimate')}"
          f"  secure_agg={out.get('secure_aggregation')}")
    print("\nbyproduct - community health signal for district officers (no patient data leaves a node):")
    epi = sim.epidemiology_map()
    print(f"  per-client disease counts: {json.dumps(epi.get('per_client', {}), ensure_ascii=False)[:180]}")
    print(f"  national totals            : {epi.get('totals')}")
    print(f"  suppressed small cells     : {len(epi.get('suppressed_cells', []))}")
    print(f"  {epi.get('privacy_note', '')[:130]}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="", help="also dump the full result bundle to this path")
    args = ap.parse_args()

    print(BANNER)
    print("GENOMIND-INDIA  ::  end-to-end platform demo")
    print("Synthetic composite patient - no real patient data.")
    print(BANNER)

    ner = stage_1_ner()
    mapped = stage_2_hpo(ner)
    dx = stage_4_diagnosis(mapped["hpo_ids"])
    xai = stage_7_xai(mapped["hpo_ids"])
    pgx = stage_5_pgx()
    repro = stage_6_reproductive()
    reports = stage_report(dx, pgx, repro)
    triage = stage_9_triage()
    learning = stage_10_learning()
    fl = stage_8_federated()

    rule("DEMO COMPLETE")
    print(f"NER engine            : {ner.get('engine')}")
    print(f"HPO terms mapped      : {len(mapped['hpo_ids'])}")
    print(f"top differential      : {dx['results'][0]['disease_name']} "
          f"({dx['results'][0]['probability'] * 100:.1f}%)")
    print(f"top PGx alert         : {pgx['alerts'][0]['drug']} "
          f"({pgx['alerts'][0]['severity']}, {pgx['alerts'][0]['gene']})")
    print(f"top reproductive risk : {repro['top_risks'][0]['disease_name']} "
          f"({repro['top_risks'][0]['child_affected_probability'] * 100:.4f}% affected child)")
    print(f"triage                : {triage['triage_color']}")
    print(f"reports written       : {len(reports)} -> reports/")

    if args.json:
        bundle = {"ner": ner, "hpo": mapped, "diagnosis": dx, "xai": xai, "pgx": pgx,
                  "reproductive": repro, "triage": triage, "learning": learning, "federated": fl}
        Path(args.json).write_text(json.dumps(bundle, ensure_ascii=False, indent=2, default=str),
                                   encoding="utf-8")
        print(f"full bundle           : {args.json}")


if __name__ == "__main__":
    main()
