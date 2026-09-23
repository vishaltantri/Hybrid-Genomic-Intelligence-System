"""Module 5/6 tests: PGx inference, Bayesian carrier math, lab parsing, reports."""
from __future__ import annotations

import pytest

from ml_services.pharmacogenomics.pgx_engine import PGxEngine, hardy_weinberg
from ml_services.reproductive import lab_report_parser, pedigree
from ml_services.reproductive.carrier_counselor import CarrierCounselor
from ml_services.reproductive.punnett import (
    offspring_risk_from_carrier_probs,
    punnett_square,
    simulate_offspring,
    x_linked_cross,
)
from ml_services.reproductive.report_generator import generate_carrier_report, generate_pgx_report


@pytest.fixture(scope="module")
def pgx():
    return PGxEngine()


@pytest.fixture(scope="module")
def counselor():
    return CarrierCounselor()


# ------------------------------ PGx ------------------------------

def test_hardy_weinberg_sums_to_one():
    hw = hardy_weinberg(0.3)
    assert abs(sum(hw.values()) - 1.0) < 1e-9
    assert hw["hom_risk"] == pytest.approx(0.09)


def test_x_linked_hw_male_female_differ():
    male = hardy_weinberg(0.07, x_linked=True, sex="M")
    female = hardy_weinberg(0.07, x_linked=True, sex="F")
    assert male["hemizygous_risk"] == pytest.approx(0.07)
    assert "hom_risk" in female and female["hom_risk"] < 0.01


def test_indian_allele_frequency_lookup_resolves_state(pgx):
    """A state must resolve to its regional frequency (or tribal belt) rather than falling
    straight through to the pan-Indian average."""
    ap = pgx.allele_frequency("CYP2C19", state="Andhra Pradesh")
    assert ap["match"] in ("state", "region", "tribal_belt")
    assert ap["af"] > 0.25  # South Asian CYP2C19*2 is far higher than European
    assert ap["af"] >= pgx.allele_frequency("CYP2C19")["af"]
    pan = pgx.allele_frequency("CYP2C19")
    assert pan["match"] == "pan_indian"


def test_g6pd_tribal_state_uses_tribal_frequency(pgx):
    tribal = pgx.allele_frequency("G6PD", state="Chhattisgarh")
    pan = pgx.allele_frequency("G6PD")
    assert tribal["af"] >= pan["af"]


def test_combined_gene_string_falls_back_to_first_gene(pgx):
    af = pgx.allele_frequency("CYP2C9+CYP4F2")
    assert af["af"] > 0  # resolves via CYP2C9 rather than returning 0


def test_metabolizer_probabilities_sum_to_one(pgx):
    inf = pgx.infer_metabolizer_probabilities("CYP2C19", state="Tamil Nadu")
    assert abs(sum(inf["phenotype_probabilities"].values()) - 1.0) < 0.01
    assert inf["phenotype_probabilities"]["intermediate_metabolizer"] > 0.3


def test_g6pd_female_risk_lower_than_male(pgx):
    male = pgx.infer_metabolizer_probabilities("G6PD", x_linked=True, sex="M")
    female = pgx.infer_metabolizer_probabilities("G6PD", x_linked=True, sex="F")
    assert male["phenotype_probabilities"]["deficient"] > female["phenotype_probabilities"]["deficient"]


def test_clopidogrel_alert_is_critical(pgx):
    result = pgx.check_drugs(["clopidogrel"], state="Andhra Pradesh", ethnicity="Dravidian")
    alert = result["alerts"][0]
    assert alert["gene"] == "CYP2C19"
    assert alert["severity"] == "critical"
    assert alert["recommendation"]
    assert alert["patient_explanation_hi"]


def test_alerts_deduplicated_per_drug_gene(pgx):
    result = pgx.check_drugs(["clopidogrel", "warfarin"], state="Punjab")
    keys = [(a["drug"], a["gene"]) for a in result["alerts"]]
    assert len(keys) == len(set(keys))


def test_primaquine_triggers_g6pd_alert(pgx):
    result = pgx.check_drugs(["primaquine"], state="Chhattisgarh", ethnicity="Tribal-Central")
    alert = next(a for a in result["alerts"] if a["gene"] == "G6PD")
    assert alert["severity"] == "critical"
    assert "avoid" in alert["recommendation"].lower() or "do not" in alert["recommendation"].lower()


def test_known_genotype_overrides_population_inference(pgx):
    result = pgx.check_drugs(["clopidogrel"], state="Kerala",
                             known_genotypes={"CYP2C19": "poor_metabolizer"})
    alert = result["alerts"][0]
    assert alert["assumption"] == "known_genotype_override"
    assert alert["probability_of_risk_status"] == 1.0
    assert alert["inferred_status"] == "poor_metabolizer"


def test_drug_without_rule_is_reported_uninvolved(pgx):
    result = pgx.check_drugs(["paracetamol", "clopidogrel"])
    assert "paracetamol" in result["drugs_without_pgx_rule"]


def test_coverage_table_and_report(pgx):
    rows = pgx.drug_gene_table()
    assert len(rows) >= 15
    report = generate_pgx_report(pgx.check_drugs(["clopidogrel"], state="Bihar"), lang="hi")
    assert report["n_alerts"] >= 1
    assert "clopidogrel" in report["markdown"]


# ------------------------------ reproductive ------------------------------

def test_punnett_carrier_cross():
    out = punnett_square("Aa", "Aa")
    assert out["phenotypes"]["affected"] == 0.25
    assert out["phenotypes"]["carrier"] == 0.5
    assert len(out["grid"]) == 2 and len(out["grid"][0]) == 2


def test_analytic_matches_simulation():
    check = simulate_offspring(0.2, 0.2, n=8000)
    assert check["abs_difference"] < 0.02


def test_consanguinity_increases_offspring_risk():
    plain = offspring_risk_from_carrier_probs(0.02, 0.02)
    inbred = offspring_risk_from_carrier_probs(0.02, 0.02, inbreeding_coefficient=0.0625)
    assert inbred["affected_child_probability"] > plain["affected_child_probability"]


def test_x_linked_sons_half_when_mother_carrier():
    out = x_linked_cross("Xx", "XAY")
    assert out["sons_affected_probability"] == 0.5
    assert out["daughters_affected_probability"] == 0.0
    assert out["daughters_carrier_probability"] == 0.5


def test_x_linked_affected_father_affects_daughters():
    out = x_linked_cross("Xx", "XaY")
    assert out["daughters_affected_probability"] == 0.5


def test_obligate_carrier_from_affected_child(counselor):
    disease = next(d for d in counselor.diseases if d["disease_id"] == "ORPHA:231222")
    prob = counselor.carrier_probability({"family_history": {"ORPHA:231222": "affected_child"}}, disease)
    assert prob["probability"] == 1.0
    assert prob["method"] == "obligate_carrier"


def test_affected_sibling_gives_two_thirds(counselor):
    disease = next(d for d in counselor.diseases if d["disease_id"] == "ORPHA:231222")
    prob = counselor.carrier_probability({"family_history": {"ORPHA:231222": "affected_sibling"}}, disease)
    assert prob["probability"] == pytest.approx(2 / 3, abs=0.01)


def test_known_non_carrier_zeroes_risk(counselor):
    disease = next(d for d in counselor.diseases if d["disease_id"] == "ORPHA:231222")
    prob = counselor.carrier_probability({"known_carrier": {"ORPHA:231222": False}}, disease)
    assert prob["probability"] == 0.0


def test_community_founder_risk_applied(counselor):
    disease = next(d for d in counselor.diseases if d["disease_id"] == "ORPHA:231222")
    sindhi = counselor.carrier_probability({"community": "Sindhi"}, disease)
    generic = counselor.carrier_probability({"community": "Kannada"}, disease)
    assert sindhi["probability"] > generic["probability"]


def test_couple_assessment_bands_and_structure(counselor):
    result = counselor.couple_assessment(
        {"state": "Tamil Nadu", "community": "Tamil", "relationship": "first_cousins"},
        {"state": "Tamil Nadu", "community": "Tamil", "age": 31,
         "family_history": {"ORPHA:231222": "affected_sibling"}},
        top_n=8,
    )
    assert result["risk_band"] in ("low", "moderate", "high")
    assert result["couple_consanguineous"] is True
    assert result["inbreeding_coefficient"] == pytest.approx(0.0625)
    assert result["top_risks"][0]["child_affected_probability"] >= result["top_risks"][-1]["child_affected_probability"]
    assert result["recommended_screening"]
    assert result["government_schemes"]


def test_thalassemia_screening_recommended_for_carrier_couple(counselor):
    result = counselor.couple_assessment(
        {"state": "Maharashtra", "community": "Sindhi"},
        {"state": "Maharashtra", "community": "Sindhi"},
        top_n=10,
    )
    tests = " ".join(r["test"].lower() for r in result["recommended_screening"])
    assert "hplc" in tests or "hba2" in tests


def test_lab_parser_flags_thal_trait():
    text = "Hemoglobin 8.2 g/dL, MCV 68 fL, HbA2 5.2 %, ferritin 65 ng/mL"
    out = lab_report_parser.parse_text(text)
    flags = {f["flag"] for f in out["flags"]}
    assert "beta_thalassemia_trait_suspected" in flags
    assert out["values"]["hba2"]["value"] == 5.2


def test_lab_parser_critical_rules():
    out = lab_report_parser.parse_text("17-OHP 45 ng/mL and sodium low")
    assert any(f["severity"] == "critical" for f in out["flags"])


def test_lab_parser_prenatal_markers():
    out = lab_report_parser.parse_text("NT 4.2 mm, PAPP-A 0.3 MoM, free beta hCG 1.1 MoM")
    flags = {f["flag"] for f in out["flags"]}
    assert "increased_nuchal_translucency" in flags and "low_papp_a" in flags


def test_pedigree_outputs():
    ped = pedigree.build_pedigree(
        {"parents": [{"id": "P1", "name": "Father", "sex": "M"},
                     {"id": "P2", "name": "Mother", "sex": "F", "carrier": True}],
         "children": [{"id": "C1", "name": "Patient", "sex": "M", "affected": True}]},
        "Beta-thalassemia", consanguineous=True)
    assert ped["mermaid"].startswith("graph TD")
    assert "Father" in ped["ascii"]
    assert ped["consanguineous"] is True


def test_carrier_report_multilingual(counselor):
    result = counselor.couple_assessment({"state": "Punjab"}, {"state": "Punjab"}, top_n=5)
    hi = generate_carrier_report(result, lang="hi")
    en = generate_carrier_report(result, lang="en")
    assert "जोखिम" in hi["markdown"]
    assert "risk" in en["markdown"].lower()
    assert hi["sections"]["risk_band"] == result["risk_band"]
