"""Lab report / prenatal screening parser (Module 6).

Reads text (or PDFs when pdfplumber is installed) of common Indian reports:
CBC, HPLC hemoglobinopathy screen, biochemical (ceruloplasmin, 17-OHP, TSH,
phenylalanine), newborn screening, and first-trimester combined screening
(NT scan, PAPP-A, free beta-hCG).

Extraction is regex based and deliberately conservative: every value carries the raw
matched string, and interpretations state the rule that fired so a clinician can audit.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

# analyte -> (regex, unit, expected range)
ANALYTE_PATTERNS = {
    "hemoglobin": (r"h(?:a)?emoglobin|(?:^|\s)hb(?:\s|$|\s*[:=])", "g/dL", (11.0, 17.0)),
    "hba2": (r"hba2|hb\s*a2", "%", (2.0, 3.5)),
    "hbf": (r"hbf|hb\s*f", "%", (0.0, 2.0)),
    "hbs": (r"hbs|hb\s*s", "%", (0.0, 0.0)),
    "mcv": (r"mcv", "fL", (80.0, 100.0)),
    "mch": (r"mch(?!c)", "pg", (27.0, 33.0)),
    "platelets": (r"platelet(?:s)?(?:\s*count)?|(?:^|\s)plt(?:\s|$)", "x10^3/uL", (150.0, 450.0)),
    "serum_ferritin": (r"ferritin", "ng/mL", (30.0, 300.0)),
    "ceruloplasmin": (r"ceruloplasmin", "mg/dL", (20.0, 60.0)),
    "urine_copper": (r"(?:24\s*h|24\s*hour)?\s*urinary?\s*copper|urine\s*copper", "ug/24h", (0.0, 40.0)),
    "17ohp": (r"17\s*[- ]?\s*oh\s*p(?:rogesterone)?", "ng/mL", (0.0, 2.0)),
    "tsh": (r"(?:^|\s)tsh(?:\s|$)", "mIU/L", (0.5, 4.5)),
    "phenylalanine": (r"phenylalanine|(?:^|\s)phe(?:\s|$)", "umol/L", (38.0, 120.0)),
    "sweat_chloride": (r"sweat\s*chloride", "mmol/L", (0.0, 40.0)),
    "creatine_kinase": (r"creatine\s*kinase|(?:^|\s)cpk(?:\s|$)|(?:^|\s)ck(?:\s|$)", "U/L", (20.0, 200.0)),
    "nt_mm": (r"(?:nuchal\s*translucency|(?:\s|^)nt(?:\s|$))", "mm", (0.0, 3.0)),
    "papp_a_mom": (r"papp\s*-?\s*a", "MoM", (0.5, 2.5)),
    "free_beta_hcg_mom": (r"(?:free\s*)?beta\s*-?\s*hcg", "MoM", (0.5, 2.5)),
    "afp_mom": (r"afp|alpha\s*feto\s*protein", "MoM", (0.5, 2.5)),
}

_NUM = r"([0-9]+(?:\.[0-9]+)?)"
TRAIT_MARKERS = ("trait", "carrier", "heterozygous", "het.", "abnormal haemoglobin", "abnormal hemoglobin")


def extract_from_text(text: str) -> Dict[str, dict]:
    """Find analyte values in free text. Returns {analyte: {value, unit, raw, out_of_range}}."""
    found: Dict[str, dict] = {}
    lowered = text.lower()
    for analyte, (pattern, unit, (lo, hi)) in ANALYTE_PATTERNS.items():
        # look for pattern followed by a number within ~40 chars
        regex = re.compile(pattern, re.IGNORECASE)
        for m in regex.finditer(text):
            window = text[m.end(): m.end() + 40]
            num = re.search(_NUM, window)
            if not num:
                continue
            value = float(num.group(1))
            found[analyte] = {
                "value": value,
                "unit": unit,
                "raw": text[m.start(): m.end() + num.end()],
                "out_of_range": not (lo <= value <= hi),
                "reference_range": [lo, hi],
            }
            break
    return found


def interpret(values: Dict[str, dict], text: str = "") -> List[dict]:
    """Apply Indian clinical rules to extracted values; returns flagged interpretations."""
    flags: List[dict] = []
    lowered = (text or "").lower()

    def v(name):
        x = values.get(name)
        return x["value"] if x else None

    hba2 = v("hba2")
    mcv = v("mcv")
    hb = v("hemoglobin")
    ferritin = v("serum_ferritin")
    if hba2 is not None and hba2 >= 3.5:
        flags.append({"flag": "beta_thalassemia_trait_suspected", "severity": "high",
                      "reason": f"HbA2 {hba2}% is >= 3.5% (diagnostic of beta-thalassemia trait in most labs)",
                      "next": "Confirm with partner carrier screening; consider HBB sequencing if both carriers"})
    if mcv is not None and mcv < 80 and (ferritin is None or ferritin >= 30):
        flags.append({"flag": "microcytic_hypochromic_likely_trait", "severity": "medium",
                      "reason": f"MCV {mcv} fL < 80 with adequate/normal ferritin",
                      "next": "Order HPLC (HbA2/HbF/HbS) to separate thalassemia trait from iron deficiency"})
    if v("hbf") is not None and v("hbf") > 2.0:
        flags.append({"flag": "raised_hbf", "severity": "medium",
                      "reason": f"HbF {v('hbf')}% above normal range",
                      "next": "Evaluate for thalassemia intermedia / HPFH / other hemoglobinopathy"})
    if v("hbs") is not None and v("hbs") > 0:
        flags.append({"flag": "hemoglobin_s_detected", "severity": "high",
                      "reason": f"HbS detected ({v('hbs')}%)",
                      "next": "Sickle cell counseling; confirm genotype (HbSS vs HbAS) and partner testing"})
    if v("ceruloplasmin") is not None and v("ceruloplasmin") < 20:
        flags.append({"flag": "low_ceruloplasmin_wilson_suspected", "severity": "high",
                      "reason": f"Serum ceruloplasmin {v('ceruloplasmin')} mg/dL (< 20 mg/dL)",
                      "next": "24-hour urinary copper, slit-lamp for Kayser-Fleischer ring, ATP7B testing"})
    if v("urine_copper") is not None and v("urine_copper") > 100:
        flags.append({"flag": "raised_urinary_copper", "severity": "high",
                      "reason": f"24-hour urinary copper {v('urine_copper')} ug/24h (>100 suggests Wilson disease)",
                      "next": "Hepatic and neurological evaluation; ATP7B sequencing"})
    if v("17ohp") is not None and v("17ohp") > 10:
        flags.append({"flag": "raised_17ohp_cah_suspected", "severity": "critical",
                      "reason": f"17-OHP {v('17ohp')} ng/mL is markedly raised",
                      "next": "Urgent pediatric endocrine review; electrolytes for salt-wasting crisis; CYP21A2 testing"})
    if v("tsh") is not None and v("tsh") > 10:
        flags.append({"flag": "raised_tsh_congenital_hypothyroidism", "severity": "high",
                      "reason": f"TSH {v('tsh')} mIU/L raised",
                      "next": "Start levothyroxine without delay (neurodevelopment is time critical); repeat confirmatory"})
    if v("phenylalanine") is not None and v("phenylalanine") > 120:
        flags.append({"flag": "raised_phenylalanine_pku_suspected", "severity": "critical",
                      "reason": f"Phenylalanine {v('phenylalanine')} umol/L (>120 umol/L)",
                      "next": "Immediate metabolic clinic referral; dietary phenylalanine restriction; PAH testing"})
    if v("sweat_chloride") is not None and v("sweat_chloride") >= 60:
        flags.append({"flag": "raised_sweat_chloride_cf_suspected", "severity": "high",
                      "reason": f"Sweat chloride {v('sweat_chloride')} mmol/L (>=60 diagnostic range)",
                      "next": "CFTR sequencing; pancreatic elastase; chest physiotherapy referral"})
    if v("creatine_kinase") is not None and v("creatine_kinase") > 1000:
        flags.append({"flag": "markedly_raised_ck_dystrophinopathy_suspected", "severity": "high",
                      "reason": f"CK {v('creatine_kinase')} U/L markedly raised",
                      "next": "DMD MLPA/sequencing (boys); carrier testing for mother; genetic counseling"})
    if v("nt_mm") is not None and v("nt_mm") >= 3.5:
        flags.append({"flag": "increased_nuchal_translucency", "severity": "high",
                      "reason": f"NT {v('nt_mm')} mm (>=3.5 mm is above the usual cut-off)",
                      "next": "Combined screening / NIPT counseling; fetal medicine referral; anomaly scan"})
    if v("papp_a_mom") is not None and v("papp_a_mom") < 0.4:
        flags.append({"flag": "low_papp_a", "severity": "medium",
                      "reason": f"PAPP-A {v('papp_a_mom')} MoM (<0.4 MoM)",
                      "next": "Risk calculation with NT and biochemistry; discuss screening vs diagnostic testing"})
    if v("platelets") is not None and v("platelets") < 100:
        flags.append({"flag": "thrombocytopenia", "severity": "medium",
                      "reason": f"Platelets {v('platelets')} x10^3/uL",
                      "next": "Evaluate for storage disorder / hypersplenism / marrow disease as clinically indicated"})
    if hb is not None and hb < 7:
        flags.append({"flag": "severe_anemia", "severity": "critical",
                      "reason": f"Hemoglobin {hb} g/dL",
                      "next": "Urgent transfusion assessment; investigate cause (thalassemia major, hemolysis, other)"})
    if any(marker in lowered for marker in TRAIT_MARKERS) and not any(
        f["flag"] in ("beta_thalassemia_trait_suspected", "microcytic_hypochromic_likely_trait") for f in flags
    ):
        flags.append({"flag": "reported_carrier_or_trait_status", "severity": "medium",
                      "reason": "Report text mentions trait/carrier/heterozygous status",
                      "next": "Record carrier status in the family record and screen the partner"})
    return flags


def parse_text(text: str) -> dict:
    values = extract_from_text(text)
    flags = interpret(values, text)
    return {
        "values": values,
        "flags": flags,
        "n_values_extracted": len(values),
        "critical_count": sum(1 for f in flags if f["severity"] == "critical"),
        "summary": (flags[0]["reason"] if flags else "No abnormal pattern detected in the extracted values."),
        "disclaimer": "Automated extraction from report text for triage support only; clinician review required.",
    }


def read_pdf(path: str | Path) -> str:
    """Extract text from a PDF using pdfplumber (optional dependency)."""
    try:
        import pdfplumber  # optional
    except ImportError as exc:
        raise RuntimeError(
            "PDF parsing needs pdfplumber: pip install pdfplumber. "
            "Alternatively paste the report text and call parse_text()."
        ) from exc
    parts: List[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def parse_file(path: str | Path) -> dict:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return parse_text(read_pdf(path))
    return parse_text(path.read_text(encoding="utf-8", errors="ignore"))


if __name__ == "__main__":
    sample = """
    SAMPLE LABORATORY REPORT (indian format)
    CBC: Hemoglobin 8.2 g/dL, MCV 68 fL, MCH 21 pg, Platelet count 180 x10^3/uL
    HPLC: HbA2 5.2 %, HbF 1.0 %, HbS 0.0 %
    Serum ferritin 65 ng/mL
    Impression: ? thalassemia trait
    """
    result = parse_text(sample)
    print(f"Extracted {result['n_values_extracted']} values; critical={result['critical_count']}")
    for f in result["flags"]:
        print(f"  [{f['severity']:8s}] {f['flag']}: {f['reason']}")
    print("summary:", result["summary"])
