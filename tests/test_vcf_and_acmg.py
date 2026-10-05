"""Tests for VCF parsing, normalization, ACMG/AMP criteria evaluation, and variant API (Phase 3B)."""
import io
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.security import create_access_token
from ml_services.variants.acmg_engine import ACMGEngine
from ml_services.variants.annotator import VariantAnnotation, VariantAnnotator
from ml_services.variants.prioritizer import VariantPrioritizer
from ml_services.variants.vcf_parser import left_align_and_trim, normalize_chrom, parse_vcf_content


def test_normalize_chrom():
    assert normalize_chrom("1") == "chr1"
    assert normalize_chrom("chr1") == "chr1"
    assert normalize_chrom("CHR13") == "chr13"
    assert normalize_chrom("chrX") == "chrX"
    assert normalize_chrom("MT") == "chrM"
    assert normalize_chrom("chrM") == "chrM"


def test_left_align_and_trim():
    # Trim identical suffixes and prefixes
    pos, ref, alt = left_align_and_trim(100, "ATCT", "A")
    assert pos == 100
    assert ref == "ATCT"
    assert alt == "A"

    pos2, ref2, alt2 = left_align_and_trim(100, "AT", "ATT")
    # Suffix 'T' is trimmed first: pos remains 100, ref becomes 'A', alt becomes 'AT'
    assert pos2 == 100
    assert ref2 == "A"
    assert alt2 == "AT"


def test_parse_vcf_content_synthetic():
    vcf_text = """##fileformat=VCFv4.2
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE1
chr13\t51943246\trs121908298\tC\tG\t99.0\tPASS\tDP=50;GENE=ATP7B\tGT:DP:AD:GQ\t1/1:50:0,50:99
chr11\t5227002\trs334\tA\tT,C\t90.0\tPASS\tDP=40;GENE=HBB\tGT:DP:AD:GQ\t0/1:40:20,20:90
"""
    records, summary = parse_vcf_content(vcf_text)
    # Line 2 has multi-allelic ALT "T,C", so decomposed into 2 records => total 3 records
    assert len(records) == 3
    assert summary["samples"] == ["SAMPLE1"]
    assert records[0].norm_chrom == "chr13"
    assert records[0].norm_pos == 51943246
    assert records[0].genotype == "1/1"
    assert records[0].zygosity == "Homozygous"
    assert records[0].depth == 50


def test_variant_annotation_and_acmg():
    annotator = VariantAnnotator()
    acmg_engine = ACMGEngine()

    # Known pathogenic ATP7B variant in Wilson disease
    ann = annotator.annotate("chr13", 51943246, "C", "G")
    assert ann.gene_symbol == "ATP7B"
    assert ann.cdna == "c.2931C>G"
    assert ann.clinical_significance in ("Pathogenic", "Likely pathogenic")

    acmg = acmg_engine.evaluate(ann, patient_hpos=["HP:0200032"])
    assert acmg.classification in ("Pathogenic", "Likely pathogenic")
    # PM1 or PS1 should be met
    met_codes = [c.code for c in acmg.criteria_met if c.status == "Met"]
    assert any(c in met_codes for c in ("PS1", "PM1", "PP2", "PP3"))


def test_acmg_benign_ba1():
    acmg_engine = ACMGEngine()
    ann_benign = VariantAnnotation(
        variant_id="chr1:100:A>G",
        chrom="chr1",
        pos=100,
        ref="A",
        alt="G",
        af_indian=0.12,
        af_global=0.10,
        consequence="synonymous_variant",
        cadd_phred=5.0,
    )
    res = acmg_engine.evaluate(ann_benign)
    assert res.classification == "Benign"
    assert "BA1" in res.criteria_summary["met_benign"]


def test_variants_api_flow():
    client = TestClient(app)
    token = create_access_token("clinician", "doctor")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Fetch Demo VCF
    demo_resp = client.get("/api/v1/variants/demo-vcf", headers=headers)
    assert demo_resp.status_code == 200
    demo_data = demo_resp.json()
    assert "clinical_sample_trio.vcf" in demo_data["filename"]
    assert len(demo_data["content"]) > 0

    # 2. Upload Demo VCF
    files = {"file": ("test_trio.vcf", io.BytesIO(demo_data["content"].encode("utf-8")), "text/plain")}
    data = {"patient_id": "P001", "hpo_ids_json": '["HP:0200032", "HP:0001337"]'}

    upload_resp = client.post("/api/v1/variants/upload", headers=headers, files=files, data=data)
    assert upload_resp.status_code == 200
    upload_result = upload_resp.json()

    analysis_id = upload_result["analysis_id"]
    assert analysis_id.startswith("VCF-")
    assert upload_result["qc_metrics"]["total_variants"] >= 7
    assert upload_result["qc_metrics"]["pathogenic_count"] >= 1

    # 3. List analyses
    list_resp = client.get("/api/v1/variants/analyses", headers=headers)
    assert list_resp.status_code == 200
    analyses = list_resp.json()
    assert any(a["analysis_id"] == analysis_id for a in analyses)

    # 4. Get analysis detail
    detail_resp = client.get(f"/api/v1/variants/analyses/{analysis_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert len(detail["variants"]) >= 7

    # Top variant should have rank 1 and high priority
    top_var = detail["variants"][0]
    assert top_var["rank"] == 1
    assert top_var["priority_score"] > 50

    # 5. Get individual variant detail
    v_resp = client.get(f"/api/v1/variants/analyses/{analysis_id}/variants/{top_var['variant_id']}", headers=headers)
    assert v_resp.status_code == 200
    v_data = v_resp.json()
    assert v_data["variant_id"] == top_var["variant_id"]
    assert len(v_data["all_criteria"]) > 0

    # 6. Diagnosis Handoff
    handoff_diag = client.post(
        f"/api/v1/variants/analyses/{analysis_id}/diagnosis-handoff",
        headers=headers,
        json={"variant_ids": [top_var["variant_id"]], "hpo_ids": ["HP:0200032"]},
    )
    assert handoff_diag.status_code == 200
    diag_data = handoff_diag.json()
    assert "candidate_genes" in diag_data
    assert "diagnosis_result" in diag_data

    # 7. Report Handoff
    handoff_rep = client.post(
        f"/api/v1/variants/analyses/{analysis_id}/report-handoff",
        headers=headers,
        json={"patient_id": "P001", "include_acmg_matrix": True},
    )
    assert handoff_rep.status_code == 200
    rep_data = handoff_rep.json()
    assert rep_data["status"] == "ready_for_review"
    assert len(rep_data["reported_variants"]) >= 1
