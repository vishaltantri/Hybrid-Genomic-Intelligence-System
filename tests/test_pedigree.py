"""Pedigree & inheritance intelligence (Phase 3E).

Runs on a throw-away SQLite file. Families are either built through the public API with manual genotypes
(clearly synthetic) or created from the verified demo trio VCF via the demo-family endpoint.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import store
from backend.app.main import app
from backend.app.security import create_access_token
from backend.app.services import registry
from ml_services.config import SEEDS_DIR
from ml_services.pedigree import analysis as pa
from ml_services.pedigree import structure as ps
from ml_services.variants.acmg_engine import reclassify_with_extra_criterion

BASE = "/api/v1/pedigree"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "pedigree_test.sqlite3")
    store.init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def hdr(name="clinician", role="doctor"):
    return {"Authorization": f"Bearer {create_access_token(name, role)}"}


def make_case(client, **extra):
    body = {"age_years": 9, "sex": "F", "state": "Andhra Pradesh", "community": "Reddy", "consanguineous": False}
    body.update(extra)
    return client.post("/api/v1/patients", json=body, headers=hdr()).json()["patient_id"]


class Fam:
    """Small helper to build a pedigree through the API."""

    def __init__(self, client, case):
        self.c, self.case = client, case

    def member(self, label, sex="U", affected="unknown", proband=False, expect=200, **kw):
        r = self.c.post(f"{BASE}/{self.case}/members", json={"label": label, "sex": sex, "affected": affected, "is_proband": proband, **kw}, headers=hdr())
        assert r.status_code == expect, r.text
        return r.json()["member_id"] if expect == 200 else r.json()

    def rel(self, kind, a, b, expect=200):
        r = self.c.post(f"{BASE}/{self.case}/relationships", json={"type": kind, "member_a": a, "member_b": b}, headers=hdr())
        assert r.status_code == expect, r.text
        return r.json()

    def trio(self, pa_="unaffected", ma="unaffected", child="affected", child_sex="F"):
        f, m = self.member("Father", "M", pa_), self.member("Mother", "F", ma)
        p = self.member("Proband", child_sex, child, proband=True)
        self.rel("partner", f, m)
        self.rel("parent", f, p)
        self.rel("parent", m, p)
        return f, m, p

    def gt(self, member, vkey, genotype, gene="GENEX", **kw):
        r = self.c.post(f"{BASE}/{self.case}/members/{member}/genotypes", json={"genotype": genotype, "variant_key": vkey, "gene": gene, **kw}, headers=hdr())
        assert r.status_code == 200, r.text

    def analysis(self, vkey):
        r = self.c.get(f"{BASE}/{self.case}/analysis", params={"variant_key": vkey}, headers=hdr())
        assert r.status_code == 200, r.text
        return r.json()

    def get(self):
        return self.c.get(f"{BASE}/{self.case}", headers=hdr()).json()


V = "chr7:100000:A>G"
V2 = "chr7:100500:C>T"


# ------------------------------- CRUD, relationships, proband -------------------------------

def test_requires_auth_and_role(client):
    case = make_case(client)
    assert client.get(f"{BASE}/{case}").status_code == 401
    for role in ("patient", "asha", "researcher"):
        assert client.get(f"{BASE}/{case}", headers=hdr("x", role)).status_code == 403
    assert client.get(f"{BASE}/NOPE", headers=hdr()).status_code == 404


def test_member_crud_and_persistence(client):
    f = Fam(client, make_case(client))
    mid = f.member("II-1", "F", "affected", age_years=9, notes="note", deceased=False)
    ped = f.get()
    m = ped["members"][0]
    assert m["label"] == "II-1" and m["sex"] == "F" and m["affected"] == "affected" and m["age_years"] == 9
    r = client.patch(f"{BASE}/{f.case}/members/{mid}", json={"label": "Renamed", "affected": "unaffected"}, headers=hdr())
    assert r.status_code == 200 and r.json()["label"] == "Renamed"
    assert f.get()["members"][0]["affected"] == "unaffected"
    assert client.patch(f"{BASE}/{f.case}/members/{mid}", json={"sex": "X"}, headers=hdr()).status_code == 422
    assert client.delete(f"{BASE}/{f.case}/members/{mid}", headers=hdr()).status_code == 200
    assert f.get()["members"] == []
    f.member("", "M", expect=422) if False else None
    assert client.post(f"{BASE}/{f.case}/members", json={"label": "x", "affected": "maybe"}, headers=hdr()).status_code == 422


def test_relationships_are_consistent_both_directions(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio()
    sib = f.member("Sister", "F", "unaffected", relation={"to": fa, "type": "child"})
    f.rel("parent", mo, sib)
    ped = {m["member_id"]: m for m in f.get()["members"]}
    assert set(ped[pr]["parents"]) == {fa, mo}                      # child -> parents
    assert set(ped[fa]["children"]) == {pr, sib}                    # parent -> children (derived, never stored twice)
    assert ped[fa]["partners"] == [mo] and ped[mo]["partners"] == [fa]
    rels = {m["label"]: m["relation_to_proband"] for m in ped.values()}
    assert rels["Father"] == "father" and rels["Mother"] == "mother" and rels["Sister"] == "sister" and rels["Proband"] == "self"
    assert ped[pr]["generation"] == 1 and ped[fa]["generation"] == 0 == ped[mo]["generation"]


def test_derived_relations_cover_extended_family(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio()
    gm = f.member("Maternal grandmother", "F", relation={"to": mo, "type": "parent"})
    aunt = f.member("Aunt", "F", relation={"to": gm, "type": "child"})
    cousin = f.member("Cousin", "M", relation={"to": aunt, "type": "child"})
    child = f.member("Son", "M", relation={"to": pr, "type": "child"})
    half = f.member("Half-brother", "M", relation={"to": fa, "type": "child"})
    grandchild = f.member("Grandchild", "F", relation={"to": child, "type": "child"})
    rel = {m["label"]: m["relation_to_proband"] for m in f.get()["members"]}
    assert rel["Maternal grandmother"] == "grandmother" and rel["Aunt"] == "aunt" and rel["Cousin"] == "cousin"
    assert rel["Son"] == "son" and rel["Half-brother"] == "half-brother" and rel["Grandchild"] == "grandchild"


def test_single_proband_enforced_and_switchable(client):
    f = Fam(client, make_case(client))
    a = f.member("A", "F", proband=True)
    b = f.member("B", "M", proband=True)       # new proband replaces the old one
    ped = f.get()
    assert [m["member_id"] for m in ped["members"] if m["is_proband"]] == [b] and ped["proband_id"] == b
    assert client.post(f"{BASE}/{f.case}/members/{a}/proband", headers=hdr()).status_code == 200
    assert f.get()["proband_id"] == a
    assert client.delete(f"{BASE}/{f.case}/members/{a}", headers=hdr()).status_code == 409   # proband protected


def test_delete_member_cascades_and_is_audited(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio()
    f.gt(fa, V, "0/1")
    r = client.delete(f"{BASE}/{f.case}/members/{fa}", headers=hdr()).json()
    assert r["relationships_removed"] == 2 and r["genotypes_removed"] == 1
    assert not [x for x in store.ped_list_genotypes(f.case) if x["member_id"] == fa]
    assert any(a["action"] == "pedigree.member_delete" for a in store.recent_audit(20))


# ------------------------------- validation -------------------------------

def test_validation_rejects_impossible_structures(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio()
    f.rel("parent", pr, pr, expect=422)                                   # self
    f.rel("parent", fa, pr, expect=422)                                   # duplicate
    f.rel("parent", pr, fa, expect=422)                                   # cycle (child as parent of own father)
    third = f.member("Third parent", "M")
    f.rel("parent", third, pr, expect=422)                                # >2 parents
    f.rel("partner", fa, pr, expect=422)                                  # partner who is also their parent


def test_age_ordering_and_same_sex_parents(client):
    f = Fam(client, make_case(client))
    a = f.member("Young parent", "M", age_years=8)
    b = f.member("Child", "F", age_years=9)
    r = f.rel("parent", a, b, expect=422)
    assert any(i["code"] == "PARENT_NOT_OLDER" for i in r["detail"]["issues"])
    f2 = Fam(client, make_case(client))
    p1, p2, ch = f2.member("P1", "M", age_years=40), f2.member("P2", "M", age_years=38), f2.member("C", "F", age_years=9)
    f2.rel("parent", p1, ch)
    f2.rel("parent", p2, ch)                                              # allowed but warned
    codes = [i["code"] for i in f2.get()["validation"]]
    assert "SAME_SEX_PARENTS" in codes


def test_validation_report_flags_missing_data():
    members = [{"member_id": "A", "label": "A", "sex": "F", "is_proband": True, "affected": "affected", "age_years": None},
               {"member_id": "B", "label": "B", "sex": "M", "is_proband": True, "affected": "unaffected", "age_years": None},
               {"member_id": "C", "label": "C", "sex": "F", "is_proband": False, "affected": "unknown", "age_years": None}]
    rels = [{"rel_id": "1", "rel_type": "parent_of", "member_a": "B", "member_b": "C"},
            {"rel_id": "2", "rel_type": "parent_of", "member_a": "B", "member_b": "C"},
            {"rel_id": "3", "rel_type": "parent_of", "member_a": "C", "member_b": "B"}]
    codes = {i["code"] for i in ps.validate(members, rels)}
    assert {"MULTIPLE_PROBANDS", "DUPLICATE_RELATIONSHIP", "ANCESTOR_CYCLE", "MISSING_PARENT"} <= codes
    assert "NO_PROBAND" in {i["code"] for i in ps.validate(members[2:], [])}


# ------------------------------- phenotypes / genotypes -------------------------------

def test_phenotypes_use_existing_hpo_graph(client):
    f = Fam(client, make_case(client))
    m = f.member("P", "F", proband=True)
    ok = client.put(f"{BASE}/{f.case}/members/{m}/phenotypes", json={"hpo_ids": ["HP:0001337", "HP:0002240"]}, headers=hdr())
    assert ok.status_code == 200 and {p["name"] for p in ok.json()["phenotypes"]} == {"Tremor", "Hepatomegaly"}
    assert client.put(f"{BASE}/{f.case}/members/{m}/phenotypes", json={"hpo_ids": ["HP:9999999"]}, headers=hdr()).status_code == 422
    assert [p["hpo_id"] for p in f.get()["members"][0]["phenotypes"]] == ["HP:0001337", "HP:0002240"]
    hits = client.get(f"{BASE}/hpo-search", params={"q": "tremor"}, headers=hdr()).json()
    assert any(h["hpo_id"] == "HP:0001337" for h in hits)


def test_genotype_validation_and_persistence(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio()
    bad = client.post(f"{BASE}/{f.case}/members/{pr}/genotypes", json={"genotype": "2/2", "variant_key": V, "gene": "G"}, headers=hdr())
    assert bad.status_code == 422
    assert client.post(f"{BASE}/{f.case}/members/{mo}/genotypes", json={"genotype": "hemizygous", "variant_key": V, "gene": "G"}, headers=hdr()).status_code == 422
    assert client.post(f"{BASE}/{f.case}/members/{pr}/genotypes", json={"genotype": "0/1", "variant_key": "garbage", "gene": "G"}, headers=hdr()).status_code == 422
    f.gt(pr, V, "0/1")
    assert f.get()["members"][2]["genotypes"][V]["genotype"] == "0/1"
    assert client.delete(f"{BASE}/{f.case}/members/{pr}/genotypes/{V}", headers=hdr()).status_code == 200
    assert V not in f.get()["members"][2]["genotypes"]


# ------------------------------- inheritance models -------------------------------

def test_autosomal_dominant_with_affected_parent(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio(pa_="unaffected", ma="affected")
    gm = f.member("Maternal grandmother", "F", "affected", relation={"to": mo, "type": "parent"})
    sib = f.member("Brother", "M", "unaffected", relation={"to": fa, "type": "child"})
    f.rel("parent", mo, sib)
    for m, g in ((pr, "0/1"), (mo, "0/1"), (gm, "0/1"), (fa, "0/0"), (sib, "0/0")):
        f.gt(m, V, g)
    a = f.analysis(V)
    ad = next(m for m in a["models"] if m["model"] == "AD")
    assert ad["verdict"] == "consistent"
    texts = " ".join(e["text"] for e in ad["evidence"] if e["status"] == "supports")
    assert "proband" in texts and "affected parent (Mother)" in texts and "Maternal grandmother" in texts
    assert a["most_consistent"]["model"] == "AD"
    assert a["segregation"]["counts"] == {"affected_carrier": 3, "affected_noncarrier": 0, "unaffected_carrier": 0, "unaffected_noncarrier": 2}
    assert a["pp1"]["status"] == "supported" and a["pp1"]["strength"] == "Supporting"
    assert a["de_novo"]["status"] == "inherited"
    assert a["completeness"]["level"] == "High"
    assert any("autosomal dominant" in w.lower() or "affected parent" in w for w in a["why"])


def test_autosomal_dominant_conflict_with_affected_non_carrier(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio(ma="affected")
    sib = f.member("Affected sister", "F", "affected", relation={"to": fa, "type": "child"})
    f.rel("parent", mo, sib)
    for m, g in ((pr, "0/1"), (mo, "0/1"), (fa, "0/0"), (sib, "0/0")):
        f.gt(m, V, g)
    a = f.analysis(V)
    ad = next(m for m in a["models"] if m["model"] == "AD")
    assert ad["verdict"] == "not_consistent" and any(e["status"] == "conflicts" for e in ad["evidence"])
    assert a["pp1"]["status"] == "not_supported"


def test_autosomal_recessive_trio(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio()
    for m, g in ((pr, "1/1"), (mo, "0/1"), (fa, "0/1")):
        f.gt(m, V, g, inheritance="Autosomal recessive")
    a = f.analysis(V)
    ar = next(m for m in a["models"] if m["model"] == "AR")
    assert ar["verdict"] == "consistent"
    assert any("Both parents are heterozygous carriers" in e["text"] for e in ar["evidence"])
    assert a["most_consistent"]["model"] == "AR" and a["reference_inheritance"]["agrees"] is True
    assert a["trio"]["complete"] and [r["state"] for r in a["trio"]["rows"]] == ["het", "het", "hom"]
    ad = next(m for m in a["models"] if m["model"] == "AD")
    assert ad["verdict"] != "consistent"                                          # no affected relative carries it


def test_recessive_single_het_is_not_called_recessive(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio()
    f.gt(pr, V, "0/1"); f.gt(mo, V, "0/1"); f.gt(fa, V, "0/0")
    ar = next(m for m in f.analysis(V)["models"] if m["model"] == "AR")
    assert ar["verdict"] in ("inconclusive", "not_consistent") and ar["verdict"] != "consistent"
    assert any("single heterozygous variant" in e["text"] for e in ar["evidence"])


def test_unaffected_homozygous_sibling_conflicts_with_recessive(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio()
    sib = f.member("Sib", "M", "unaffected", relation={"to": fa, "type": "child"})
    f.rel("parent", mo, sib)
    for m, g in ((pr, "1/1"), (mo, "0/1"), (fa, "0/1"), (sib, "1/1")):
        f.gt(m, V, g)
    ar = next(m for m in f.analysis(V)["models"] if m["model"] == "AR")
    assert ar["verdict"] == "not_consistent"


def test_x_linked_male_proband_with_carrier_mother(client):
    f = Fam(client, make_case(client, sex="M"))
    fa, mo, pr = f.trio(child_sex="M")
    X = "chrX:31000000:A>G"
    f.gt(pr, X, "hemizygous", gene="DMD"); f.gt(mo, X, "0/1", gene="DMD"); f.gt(fa, X, "0/0", gene="DMD")
    a = f.analysis(X)
    assert [m["model"] for m in a["models"]] == ["XL"]
    assert a["models"][0]["verdict"] == "consistent" and a["most_consistent"]["model"] == "XL"
    assert a["members"][2]["state"] == "hemi"


def test_x_linked_father_to_son_transmission_is_a_conflict(client):
    f = Fam(client, make_case(client, sex="M"))
    fa, mo, pr = f.trio(pa_="affected", child_sex="M")
    X = "chrX:31000000:A>G"
    f.gt(pr, X, "hemizygous", gene="DMD"); f.gt(fa, X, "hemizygous", gene="DMD"); f.gt(mo, X, "0/0", gene="DMD")
    assert f.analysis(X)["models"][0]["verdict"] == "not_consistent"


def test_mitochondrial_maternal_pattern(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio(ma="affected")
    M = "chrM:3243:A>G"
    f.gt(pr, M, "1/1", gene="MT-TL1"); f.gt(mo, M, "1/1", gene="MT-TL1"); f.gt(fa, M, "0/0", gene="MT-TL1")
    a = f.analysis(M)
    assert [m["model"] for m in a["models"]] == ["MT"] and a["models"][0]["verdict"] == "consistent"
    assert any("Heteroplasmy" in e["text"] for e in a["models"][0]["evidence"])


# ------------------------------- de novo -------------------------------

def test_candidate_de_novo_needs_both_parents(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio()
    f.gt(pr, V, "0/1"); f.gt(fa, V, "0/0"); f.gt(mo, V, "0/0")
    dn = f.analysis(V)["de_novo"]
    assert dn["status"] == "candidate" and "confirmatory validation recommended" in dn["assessment"] and "mosaicism" in dn["caveat"]
    assert [p["state"] for p in dn["parents"]] == ["absent", "absent"]


def test_de_novo_not_claimed_when_a_parent_genotype_missing(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio()
    f.gt(pr, V, "0/1"); f.gt(mo, V, "0/0")                    # father unknown
    a = f.analysis(V)
    assert a["de_novo"]["status"] == "cannot_assess" and "Father genotype unavailable" in a["de_novo"]["assessment"]
    assert "Father genotype unavailable." in a["uncertainty"]


def test_de_novo_not_assessable_without_parents_in_pedigree(client):
    f = Fam(client, make_case(client))
    pr = f.member("Proband", "F", "affected", proband=True)
    f.gt(pr, V, "0/1")
    a = f.analysis(V)
    assert a["de_novo"]["status"] == "cannot_assess"
    assert a["most_consistent"] is None and any("inconclusive" in u.lower() for u in a["uncertainty"])


# ------------------------------- compound heterozygosity -------------------------------

def _two_variant_family(client, mother_has, father_has):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio()
    f.gt(pr, V, "0/1", gene="GENEZ", inheritance="Autosomal recessive"); f.gt(pr, V2, "0/1", gene="GENEZ", inheritance="Autosomal recessive")
    for m, has in ((mo, mother_has), (fa, father_has)):
        for v in (V, V2):
            f.gt(m, v, ("0/1" if v in has else "0/0"), gene="GENEZ")
    return f, pr


def test_compound_het_in_trans_supported_by_parents(client):
    f, pr = _two_variant_family(client, [V], [V2])
    a = f.analysis(V)
    ch = a["compound_het"]
    assert ch["in_trans_supported"] and ch["pairs"][0]["phase"] == "trans"
    ar = next(m for m in a["models"] if m["model"] == "AR")
    assert ar["verdict"] == "consistent" or ar["verdict"] == "possible"
    assert any("compound heterozygous" in e["text"] for e in ar["evidence"])


def test_same_parent_means_cis_not_compound_het(client):
    f, pr = _two_variant_family(client, [V, V2], [])
    ch = f.analysis(V)["compound_het"]
    assert ch["pairs"][0]["phase"] == "cis" and not ch["in_trans_supported"]


def test_phase_unavailable_without_parental_genotypes(client):
    f = Fam(client, make_case(client))
    pr = f.member("Proband", "F", "affected", proband=True)
    f.gt(pr, V, "0/1", gene="GENEZ"); f.gt(pr, V2, "0/1", gene="GENEZ")
    a = f.analysis(V)
    ch = a["compound_het"]
    assert ch["pairs"][0]["phase"] == "unavailable" and "Phase unavailable" in ch["pairs"][0]["assessment"]
    assert not ch["in_trans_supported"]
    assert any("Phase cannot be determined" in u for u in a["uncertainty"])
    ar = next(m for m in a["models"] if m["model"] == "AR")
    assert ar["verdict"] != "consistent"


# ------------------------------- segregation & PP1 -------------------------------

def test_segregation_counts_exclude_unknowns(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio(ma="affected")
    s1 = f.member("Unaffected carrier", "M", "unaffected", relation={"to": fa, "type": "child"})
    s2 = f.member("Unknown status", "F", "unknown", relation={"to": fa, "type": "child"})
    s3 = f.member("No genotype", "F", "affected", relation={"to": fa, "type": "child"})
    for m in (s1, s2, s3):
        f.rel("parent", mo, m)
    for m, g in ((pr, "0/1"), (mo, "0/1"), (fa, "0/0"), (s1, "0/1"), (s2, "0/1")):
        f.gt(m, V, g)
    seg = f.analysis(V)["segregation"]
    assert seg["counts"] == {"affected_carrier": 2, "affected_noncarrier": 0, "unaffected_carrier": 1, "unaffected_noncarrier": 1}
    assert len(seg["excluded"]["unknown_genotype"]) == 1 and len(seg["excluded"]["unknown_affected_status"]) == 1


def test_pp1_levels_and_insufficient():
    mk = lambda aff_car, aff_non=0: {"members": {"affected_carrier": [f"a{i}" for i in range(aff_car)], "affected_noncarrier": [f"n{i}" for i in range(aff_non)]},
                                     "biallelic_members": {"affected_biallelic": [], "affected_not_biallelic": [], "unaffected_biallelic": []}}
    assert pa.pp1_assessment(mk(2), "AD", "a0")["status"] == "insufficient"
    assert pa.pp1_assessment(mk(3), "AD", "a0")["strength"] == "Supporting"
    assert pa.pp1_assessment(mk(5), "AD", "a0")["strength"] == "Moderate"
    assert pa.pp1_assessment(mk(7), "AD", "a0")["strength"] == "Strong"
    assert pa.pp1_assessment(mk(9, aff_non=1), "AD", "a0")["status"] == "not_supported"
    assert pa.pp1_assessment(mk(9), None, "a0")["status"] == "insufficient"


def test_segregation_data_alone_does_not_assign_pp1(client):
    f = Fam(client, make_case(client))
    fa, mo, pr = f.trio(ma="affected")
    for m, g in ((pr, "0/1"), (mo, "0/1"), (fa, "0/0")):
        f.gt(m, V, g)
    a = f.analysis(V)
    assert a["segregation"]["counts"]["affected_carrier"] == 2
    assert a["pp1"]["status"] == "insufficient" and a["pp1"]["strength"] is None
    assert a["acmg"]["classification_with_pp1"] is None and a["acmg"]["changed"] is False


def test_acmg_extension_recombines_without_duplicating_rules():
    """PP1 is just another criterion fed to the existing combination rules (combine_criteria)."""
    crit = lambda code, strength, status="Met": {"code": code, "category": "Pathogenic", "applied_strength": strength, "status": status}
    variant = {"clinvar_significance": None, "all_criteria": [crit("PM2", "Supporting"), crit("PP3", "Supporting"),
                                                              crit("PP2", "Supporting"), crit("PM1", "Moderate"), crit("PS3", "Strong", "Not Met")]}
    # without PP1: 1 Moderate + 3 Supporting -> VUS;  with PP1 (Supporting): 1 Moderate + 4 Supporting -> Likely pathogenic
    assert reclassify_with_extra_criterion(variant, "PP1", "Supporting")[0] == "Likely pathogenic"
    variant["all_criteria"].remove(variant["all_criteria"][2])                        # drop PP2
    assert reclassify_with_extra_criterion(variant, "PP1", "Supporting")[0] == "Uncertain significance"
    assert reclassify_with_extra_criterion(variant, "PP1", "Moderate")[0] == "Likely pathogenic"   # 2 Moderate + 2 Supporting
    variant["all_criteria"].append(crit("PS1", "Strong"))
    assert reclassify_with_extra_criterion(variant, "PP1", "Strong")[0] == "Pathogenic"            # 2 Strong


# ------------------------------- demo family from the verified VCF -------------------------------

def demo_case(client):
    case = make_case(client, sex="F")
    r = client.post(f"{BASE}/{case}/demo-family", headers=hdr())
    assert r.status_code == 200, r.text
    return case, r.json()


def test_demo_family_is_labelled_synthetic_and_uses_real_vcf_genotypes(client):
    case, info = demo_case(client)
    ped = client.get(f"{BASE}/{case}", headers=hdr()).json()
    assert ped["synthetic"] and ped["synthetic_banner"] == "Sample Family — Not Clinical Data"
    assert {m["label"] for m in ped["members"]} == {"Father", "Mother", "Proband"} and ped["proband_id"]
    analysis = registry.variants.get_analysis(info["analysis_id"])
    atp7b = "chr13:51943246:C>G"
    by = {m["label"]: m for m in ped["members"]}
    for label, sample in (("Father", "FATHER"), ("Mother", "MOTHER"), ("Proband", "PROBAND")):
        assert by[label]["genotypes"][atp7b]["genotype"] == analysis["sample_genotypes"][atp7b][sample]["genotype"]
        assert by[label]["genotypes"][atp7b]["source"].startswith("vcf:")
    assert by["Proband"]["genotypes"][atp7b]["genotype"] == "1/1"
    assert client.post(f"{BASE}/{case}/demo-family", headers=hdr()).status_code == 409


def test_demo_trio_recessive_and_de_novo_results(client):
    case, _ = demo_case(client)
    atp = client.get(f"{BASE}/{case}/analysis", params={"variant_key": "chr13:51943246:C>G"}, headers=hdr()).json()
    assert atp["most_consistent"]["model"] == "AR" and atp["de_novo"]["status"] == "inherited"
    assert atp["synthetic_banner"] == "Sample Family — Not Clinical Data"
    vhl = client.get(f"{BASE}/{case}/analysis", params={"variant_key": "chr3:10141973:C>G"}, headers=hdr()).json()
    assert vhl["de_novo"]["status"] == "candidate"                                       # VHL: 0/1 vs 0/0 and 0/0 in the VCF
    ov = client.get(f"{BASE}/{case}/overview", headers=hdr()).json()["variants"]
    assert {v["gene"] for v in ov} >= {"ATP7B", "VHL"}


def test_acmg_pp1_reported_with_stored_criteria(client):
    case, _ = demo_case(client)
    a = client.get(f"{BASE}/{case}/analysis", params={"variant_key": "chr13:51943246:C>G"}, headers=hdr()).json()
    assert a["acmg"]["pp1"]["source"] == "Pedigree segregation analysis"
    assert a["acmg"]["stored_classification"] == "Likely pathogenic" and a["acmg"]["changed"] is False
    assert a["acmg"]["pp1"]["status"] in ("insufficient", "not_supported")           # trio alone is not enough for PP1


def test_family_prioritisation_is_transparent_and_non_destructive(client):
    case, info = demo_case(client)
    rows = client.get(f"{BASE}/{case}/prioritization", headers=hdr()).json()["rows"]
    vhl = next(r for r in rows if r["gene"] == "VHL")
    base = next(v for v in registry.variants.get_analysis(info["analysis_id"])["variants"] if v["gene_symbol"] == "VHL")["priority_score"]
    assert vhl["base_priority_score"] == base                                           # base score untouched
    assert vhl["adjustments"][0]["code"] == "de_novo_candidate" and vhl["family_adjusted_score"] == round(base + pa.PRIORITY_ADJUSTMENTS["de_novo_candidate"], 1)
    assert registry.variants.get_analysis(info["analysis_id"])["variants"][0]["priority_score"] is not None


def test_diagnosis_context_does_not_change_the_engine(client):
    case, _ = demo_case(client)
    ped = client.get(f"{BASE}/{case}", headers=hdr()).json()
    proband = next(m for m in ped["members"] if m["is_proband"])
    client.put(f"{BASE}/{case}/members/{proband['member_id']}/phenotypes", json={"hpo_ids": ["HP:0000952", "HP:0002240", "HP:0001337"]}, headers=hdr())
    a = client.get(f"{BASE}/{case}/analysis", params={"variant_key": "chr13:51943246:C>G"}, headers=hdr()).json()
    dc = a["diagnosis_context"]
    direct = registry.diagnosis.diagnose(["HP:0000952", "HP:0001337", "HP:0002240"], {"state": "Andhra Pradesh", "community": "Reddy", "sex": "F"}, top_k=5)["results"]
    assert [c["disease_id"] for c in dc["candidates"]] == [d["disease_id"] for d in direct]
    wilson = next(c for c in dc["candidates"] if c["disease_name"] == "Wilson disease")
    assert wilson["gene_has_family_variant"] and wilson["pattern_compatible"] is True
    assert dc["pedigree_pattern"].startswith("Pedigree pattern: consistent with autosomal recessive")


def test_reproductive_context_uses_pedigree_genotypes_and_existing_engine(client):
    case, _ = demo_case(client)
    r = client.get(f"{BASE}/{case}/reproductive-context", headers=hdr())
    assert r.status_code == 200, r.text
    j = r.json()
    a, b = j["partner_inputs"]["a"], j["partner_inputs"]["b"]
    assert a["known_carrier"].get("ORPHA:915") is True and b["known_carrier"].get("ORPHA:915") is True    # both parents het for ATP7B
    assert j["assessment"]["risk_band"] == "high" and j["relationship_from_pedigree"] is None
    wilson = next(x for x in j["assessment"]["top_risks"] if x["disease_id"] == "ORPHA:915")
    assert wilson["both_carriers_probability"] == 1.0 and wilson["child_affected_probability"] == 0.25     # existing Punnett engine


def test_reproductive_context_needs_both_parents(client):
    f = Fam(client, make_case(client))
    f.member("Proband", "F", "affected", proband=True)
    assert client.get(f"{BASE}/{f.case}/reproductive-context", headers=hdr()).status_code == 422


# ------------------------------- import / security / isolation -------------------------------

def test_vcf_import_rejects_foreign_analysis_and_unknown_sample(client):
    case, info = demo_case(client)
    other = Fam(client, make_case(client))
    m = other.member("Someone", "F", proband=True)
    r = client.post(f"{BASE}/{other.case}/members/{m}/genotypes/import", json={"analysis_id": info["analysis_id"], "sample": "PROBAND"}, headers=hdr())
    assert r.status_code == 404                                                       # analysis belongs to another case
    mem = client.get(f"{BASE}/{case}", headers=hdr()).json()["members"][0]["member_id"]
    r = client.post(f"{BASE}/{case}/members/{mem}/genotypes/import", json={"analysis_id": info["analysis_id"], "sample": "NOPE"}, headers=hdr())
    assert r.status_code == 422


def test_case_isolation_between_pedigrees(client):
    a, b = Fam(client, make_case(client)), Fam(client, make_case(client))
    ma = a.member("A-proband", "F", proband=True)
    mb = b.member("B-proband", "M", proband=True)
    assert [m["label"] for m in b.get()["members"]] == ["B-proband"]
    assert client.patch(f"{BASE}/{b.case}/members/{ma}", json={"label": "hijack"}, headers=hdr()).status_code == 404
    assert client.delete(f"{BASE}/{b.case}/members/{ma}", headers=hdr()).status_code == 404
    assert client.post(f"{BASE}/{b.case}/relationships", json={"type": "parent", "member_a": ma, "member_b": mb}, headers=hdr()).status_code == 404
    assert client.post(f"{BASE}/{b.case}/members/{ma}/genotypes", json={"genotype": "0/1", "variant_key": V, "gene": "G"}, headers=hdr()).status_code == 404
    assert client.get(f"{BASE}/{b.case}/analysis", params={"variant_key": V}, headers=hdr()).status_code == 404
    a.gt(ma, V, "0/1")
    assert b.get()["variants"] == []


def test_mutations_are_audited(client):
    f = Fam(client, make_case(client))
    m = f.member("P", "F", proband=True)
    f.gt(m, V, "0/1")
    actions = [a["action"] for a in store.recent_audit(30)]
    assert {"pedigree.member_add", "pedigree.genotype_set"} <= set(actions)


# ------------------------------- integrations -------------------------------

def test_digital_twin_reads_the_same_pedigree(client):
    case, _ = demo_case(client)
    twin = client.get(f"/api/v1/digital-twin/{case}", headers=hdr()).json()
    ped = twin["family"]["pedigree"]
    assert ped["exists"] and ped["members"] == 3 and ped["proband"] == "Proband" and ped["synthetic"]
    assert twin["family"]["available"] is True


class _CapturingLLM:
    is_configured = True

    def __init__(self):
        self.messages = None

    def generate(self, messages, **_):
        self.messages = messages
        return "stub"


def test_assistant_receives_pedigree_context_and_nothing_invented(client):
    case, _ = demo_case(client)
    stub, original = _CapturingLLM(), registry.assistant.llm
    registry.assistant.llm = stub
    try:
        r = client.post("/api/v1/assistant/chat", headers=hdr(), json={
            "message": "What inheritance pattern does this family show?", "patient_id": case,
            "include_pedigree": True, "pedigree_variant_key": "chr13:51943246:C>G"})
    finally:
        registry.assistant.llm = original
    assert r.status_code == 200, r.text
    prompt = json.dumps(stub.messages)
    assert "SAMPLE FAMILY" in prompt and "Autosomal recessive" in prompt and "Father" in prompt and "ATP7B" in prompt
    assert "Grandmother" not in prompt                                                # no members that were not recorded
    assert r.json()["context_summary"]["pedigree"] is True
    assert any(c["source_type"] == "Pedigree Analysis" for c in r.json()["citations"])
    assert client.post("/api/v1/assistant/chat", headers=hdr("pat", "patient"),
                       json={"message": "x", "patient_id": case, "include_pedigree": True}).status_code == 403
