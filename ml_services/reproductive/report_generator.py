"""Plain-language multilingual report generation (Modules 6/7/9).

Strategy (deliberate, defensible engineering choice):
  1. Deterministic templates in Hindi + English built from structured results — always
     available, auditable, and never hallucinates a medical fact.
  2. Optional IndicBART/LLM "polish" step (ml_services.reproductive.report_generator
     .polish_with_indicator_model) that rewrites the templated sentences in a warmer
     register once the fine-tuned model exists (training recipe: see
     docs/TRAINING_RECIPES.md).
"""
from __future__ import annotations

from typing import Dict, List, Optional

LANG_NAMES = {"hi": "हिन्दी (Hindi)", "en": "English", "ta": "தமிழ் (Tamil)", "te": "తెలుగు (Telugu)"}

RISK_BAND_TEXT = {
    "hi": {"low": "कम जोखिम", "moderate": "मध्यम जोखिम", "high": "उच्च जोखिम"},
    "en": {"low": "low risk", "moderate": "moderate risk", "high": "high risk"},
}


def _pct(x: float) -> str:
    if x >= 0.01:
        return f"{x * 100:.1f}%"
    if x > 0:
        return f"{x * 100:.3f}%"
    return "0%"


def _one_in(x: float) -> str:
    return f"1 in {round(1 / x)}" if x > 0 else "not applicable"


def generate_carrier_report(assessment: Dict, lang: str = "hi", include_schemes: bool = True) -> dict:
    """Couple carrier-risk counseling report (Module 6 output contract)."""
    band = assessment.get("risk_band", "low")
    band_txt = RISK_BAND_TEXT.get(lang, RISK_BAND_TEXT["en"]).get(band, band)
    top = (assessment.get("top_risks") or [])[:5]
    cons = assessment.get("couple_consanguineous")

    if lang == "hi":
        lines = [
            "# वंशानुगत रोग जोखिम परामर्श रिपोर्ट",
            "",
            f"**कुल जोखिम श्रेणी:** {band_txt}",
            f"**राज्य:** {assessment.get('state', 'अज्ञात')} "
            f"(राज्य में निकट-संबंधी विवाह दर: {assessment.get('state_consanguinity_rate', 0) * 100:.1f}%)",
        ]
        if cons:
            lines.append(f"**निकट-संबंधी विवाह (consanguinity):** हाँ — जोखिम को "
                         f"{assessment.get('inbreeding_coefficient', 0):.4f} गुणांक से बढ़ाया गया है")
        lines += ["", "## सबसे महत्वपूर्ण जोखिम"]
        for r in top:
            lines.append(f"- **{r['disease_name']}** — बच्चे के प्रभावित होने की संभावना "
                         f"{_pct(r['child_affected_probability'])} ({_one_in(r['child_affected_probability'])})। "
                         f"माता-पिता दोनों वाहक होने की संभावना {_pct(r['both_carriers_probability'])}।")
        lines += ["", "## आगे क्या करें"]
        for s in assessment.get("recommended_screening", [])[:5]:
            lines.append(f"- **{s['condition']}:** {s['test']} — {s['timing']}")
        lines += ["", "## समझने योग्य बातें"]
        for point in assessment.get("counselling_points", [])[:4]:
            lines.append(f"- {point}")
        if include_schemes:
            lines += ["", "## सरकारी सहायता"]
            for s in assessment.get("government_schemes", [])[:4]:
                lines.append(f"- **{s['name']}:** {s['benefit'][:180]}")
        lines += ["", f"_{assessment.get('disclaimer', '')}_"]
    else:
        lines = [
            "# Reproductive Genetic Risk Counseling Report",
            "",
            f"**Overall risk band:** {band_txt}",
            f"**State:** {assessment.get('state', 'unknown')} "
            f"(state consanguinity rate: {assessment.get('state_consanguinity_rate', 0) * 100:.1f}%)",
        ]
        if cons:
            lines.append("**Consanguineous union:** yes — risk adjusted with inbreeding coefficient "
                         f"{assessment.get('inbreeding_coefficient', 0):.4f}")
        lines += ["", "## Highest-risk conditions"]
        for r in top:
            lines.append(f"- **{r['disease_name']}** — affected child probability "
                         f"{_pct(r['child_affected_probability'])} ({_one_in(r['child_affected_probability'])}); "
                         f"both-parents-carrier probability {_pct(r['both_carriers_probability'])}")
        lines += ["", "## Recommended next steps"]
        for s in assessment.get("recommended_screening", [])[:5]:
            lines.append(f"- **{s['condition']}:** {s['test']} — {s['timing']}")
        lines += ["", "## What this means"]
        for point in assessment.get("counselling_points", [])[:4]:
            lines.append(f"- {point}")
        if include_schemes:
            lines += ["", "## Government support"]
            for s in assessment.get("government_schemes", [])[:4]:
                lines.append(f"- **{s['name']}:** {s['benefit'][:180]}")
        lines += ["", f"_{assessment.get('disclaimer', '')}_"]

    return {
        "lang": lang,
        "format": "markdown",
        "markdown": "\n".join(lines),
        "sections": {"risk_band": band, "top_risks": [r["disease_name"] for r in top],
                     "n_screening_recommendations": len(assessment.get("recommended_screening", []))},
        "engine": "template",
    }


def generate_diagnosis_summary(diagnosis: Dict, lang: str = "hi", max_items: int = 3) -> dict:
    """Doctor/patient-facing explanation of a differential diagnosis (Module 7 narrative)."""
    results = (diagnosis.get("results") or [])[:max_items]
    if not results:
        text = ("इस phenotypic प्रोफ़ाइल के लिए कोई मिलान नहीं मिला।" if lang == "hi"
                else "No matching disease found for this phenotype profile.")
        return {"lang": lang, "markdown": text, "engine": "template"}

    top = results[0]
    lines: List[str] = []
    if lang == "hi":
        lines.append(f"# संभावित निदान: {top['disease_name']}")
        lines.append("")
        lines.append(f"**संभावना:** {_pct(top['probability'])} "
                     f"(विश्वास सीमा {_pct(top['probability_ci'][0])} – {_pct(top['probability_ci'][1])})")
        drivers = top.get("driving_symptoms") or []
        if drivers:
            lines.append("")
            lines.append("## कौन से लक्षण निर्णायक रहे")
            for d in drivers[:5]:
                lines.append(f"- {d['patient_term']} — योगदान {d['weight_pct']}% "
                             f"(विशिष्टता {d['specificity']:.2f})")
        missing = top.get("missing_findings") or []
        if missing:
            lines.append("")
            lines.append("## कौन से लक्षण जाँचे जाने चाहिए")
            for m in missing:
                lines.append(f"- {m['hpo_name']} ({m['hpo_id']})")
        tests = (top.get("confirmatory_tests") or {})
        if tests.get("first_line"):
            lines.append("")
            lines.append("## पुष्टि करने वाली जाँचें")
            for t in tests["first_line"][:4]:
                lines.append(f"- {t}")
        lines.append("")
        lines.append("## अन्य संभावनाएँ")
        for r in results[1:]:
            lines.append(f"- {r['disease_name']} ({_pct(r['probability'])})")
        lines.append("")
        pp = top.get("population_prior", {})
        if pp.get("india_notes"):
            lines.append("")
            lines.append("## भारत-विशिष्ट कारण")
            for note in pp["india_notes"]:
                lines.append(f"- {note}")
    else:
        lines.append(f"# Possible diagnosis: {top['disease_name']}")
        lines.append("")
        lines.append(f"**Probability:** {_pct(top['probability'])} "
                     f"(credible interval {_pct(top['probability_ci'][0])} – {_pct(top['probability_ci'][1])})")
        drivers = top.get("driving_symptoms") or []
        if drivers:
            lines.append("")
            lines.append("## Findings that drove this ranking")
            for d in drivers[:5]:
                lines.append(f"- {d['patient_term']} — contributed {d['weight_pct']}% "
                             f"(specificity {d['specificity']:.2f})")
        missing = top.get("missing_findings") or []
        if missing:
            lines.append("")
            lines.append("## Findings to look for")
            for m in missing:
                lines.append(f"- {m['hpo_name']} ({m['hpo_id']})")
        tests = (top.get("confirmatory_tests") or {})
        if tests.get("first_line"):
            lines.append("")
            lines.append("## Confirmatory tests")
            for t in tests["first_line"][:4]:
                lines.append(f"- {t}")
        lines.append("")
        lines.append("## Other possibilities")
        for r in results[1:]:
            lines.append(f"- {r['disease_name']} ({_pct(r['probability'])})")
        pp = top.get("population_prior", {})
        if pp.get("india_notes"):
            lines.append("")
            lines.append("## India-specific context")
            for note in pp["india_notes"]:
                lines.append(f"- {note}")

    return {"lang": lang, "format": "markdown", "markdown": "\n".join(lines), "engine": "template"}


def generate_pgx_report(pgx: Dict, lang: str = "hi") -> dict:
    alerts = pgx.get("alerts") or []
    lines: List[str] = []
    if lang == "hi":
        lines.append("# दवा-जीन जोखिम चेतावनी")
        lines.append("")
        lines.append(f"**सारांश:** {pgx.get('summary', {}).get('headline', '')}")
        for a in alerts:
            lines.append("")
            lines.append(f"## {a['drug']} × {a['gene']} — {a['severity']} जोखिम")
            lines.append(f"- अनुमानित स्थिति: {a['inferred_status']} "
                         f"(संभावना {_pct(a['probability_of_risk_status'])})")
            if a.get("allele_frequency"):
                lines.append(f"- भारतीय आबादी में allele frequency: {a['allele_frequency']:.3f} "
                             f"({a.get('af_match')}, स्रोत: {a.get('af_source', 'n/a')})")
            if a.get("recommendation"):
                lines.append(f"- सिफारिश: {a['recommendation']}")
            if a.get("alternatives"):
                lines.append(f"- विकल्प: {', '.join(a['alternatives'])}")
        lines.append("")
        lines.append(f"_{pgx.get('disclaimer', '')}_")
    else:
        lines.append("# Pharmacogenomic risk alerts")
        lines.append("")
        lines.append(f"**Summary:** {pgx.get('summary', {}).get('headline', '')}")
        for a in alerts:
            lines.append("")
            lines.append(f"## {a['drug']} × {a['gene']} — {a['severity']} risk")
            lines.append(f"- Inferred status: {a['inferred_status']} "
                         f"(probability {_pct(a['probability_of_risk_status'])})")
            if a.get("allele_frequency"):
                lines.append(f"- Indian allele frequency: {a['allele_frequency']:.3f} "
                             f"({a.get('af_match')}, source: {a.get('af_source', 'n/a')})")
            if a.get("recommendation"):
                lines.append(f"- Recommendation: {a['recommendation']}")
            if a.get("alternatives"):
                lines.append(f"- Alternatives: {', '.join(a['alternatives'])}")
        lines.append("")
        lines.append(f"_{pgx.get('disclaimer', '')}_")

    return {"lang": lang, "format": "markdown", "markdown": "\n".join(lines),
            "engine": "template", "n_alerts": len(alerts)}


def generate_triage_referral(triage: Dict, lang: str = "hi") -> dict:
    """Referral letter for ASHA workers (Module 9 output contract)."""
    color = triage.get("triage_color", "green")
    color_hi = {"green": "हरा (निगरानी)", "yellow": "पीला (PHC रेफर)", "red": "लाल (तुरंत विशेषज्ञ)"}.get(color, color)
    lines: List[str] = []
    if lang == "hi":
        lines.append("# स्वास्थ्य कार्यकर्ता रेफरल पत्र")
        lines.append("")
        lines.append(f"**ट्रायाज:** {color_hi}")
        lines.append(f"**रोगी:** {triage.get('patient_name', 'गोपनीय')}, "
                     f"आयु {triage.get('age', 'अज्ञात')}, गाँव {triage.get('village', 'अज्ञात')}, "
                     f"जिला {triage.get('district', 'अज्ञात')}")
        lines.append("")
        lines.append("## मुख्य लक्षण")
        for s in (triage.get("reported_symptoms") or [])[:6]:
            lines.append(f"- {s}")
        if triage.get("red_flags"):
            lines.append("")
            lines.append("## चेतावनी संकेत")
            for f in triage["red_flags"]:
                lines.append(f"- {f}")
        lines.append("")
        lines.append(f"## सिफारिश\n{triage.get('recommendation_hi') or triage.get('recommendation', '')}")
        if triage.get("referral_facility"):
            lines.append(f"\nरेफर केंद्र: {triage['referral_facility']}")
        lines.append(f"\n_{triage.get('disclaimer', '')}_")
    else:
        lines.append("# ASHA Worker Referral Letter")
        lines.append("")
        lines.append(f"**Triage:** {color.upper()}")
        lines.append(f"**Patient:** {triage.get('patient_name', 'confidential')}, "
                     f"age {triage.get('age', 'unknown')}, village {triage.get('village', 'unknown')}, "
                     f"district {triage.get('district', 'unknown')}")
        lines.append("")
        lines.append("## Reported symptoms")
        for s in (triage.get("reported_symptoms") or [])[:6]:
            lines.append(f"- {s}")
        if triage.get("red_flags"):
            lines.append("")
            lines.append("## Red flags")
            for f in triage["red_flags"]:
                lines.append(f"- {f}")
        lines.append("")
        lines.append(f"## Recommendation\n{triage.get('recommendation', '')}")
        if triage.get("referral_facility"):
            lines.append(f"\nRefer to: {triage['referral_facility']}")
        lines.append(f"\n_{triage.get('disclaimer', '')}_")

    return {"lang": lang, "format": "markdown", "markdown": "\n".join(lines), "engine": "template"}


def polish_with_indicator_model(markdown: str, lang: str = "hi", model_dir: Optional[str] = None) -> dict:
    """Optional IndicBART register-polish step.

    Training: LoRA fine-tune ai4bharat/IndicBARTSS on (structured JSON -> plain-language
    counselling text) pairs generated from the templates above plus clinician edits.
    Until that checkpoint exists this is a pass-through so no unverified medical text is
    ever produced by a general-purpose model.
    """
    try:
        import torch  # noqa: F401
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # noqa: F401
    except Exception:
        return {"markdown": markdown, "engine": "template_passthrough",
                "note": "IndicBART polish unavailable (transformers not installed); using audited templates."}
    if not model_dir:
        return {"markdown": markdown, "engine": "template_passthrough",
                "note": "No fine-tuned IndicBART checkpoint configured (set model_dir)."}
    return {"markdown": markdown, "engine": "template_passthrough",
            "note": f"Checkpoint {model_dir} present; wire tokenizer/generate here after training."}
