"""Family genotype analysis (Phase 3E): trio table, inheritance models, segregation, de novo, compound
heterozygosity, PP1 and transparent family-aware prioritisation.

Principles
 * Nothing is inferred from the *shape* of the pedigree. Every statement is computed from the recorded
   genotypes, affected statuses and parent-child links of this case.
 * Missing data stays missing. Unknown genotype is never treated as reference; every result carries the list of
   what could not be assessed and why.
 * Models are assessed, not asserted: verdict is one of consistent / possible / not_consistent / inconclusive.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ml_services.pedigree.structure import Graph

# ------------------------------- configuration (documented, adjustable) -------------------------------

# PP1 (co-segregation). Strength is a *heuristic* mapping from the number of affected family members that carry the
# variant (proband included); it is not a validated likelihood-ratio calculation and assumes full penetrance.
# Any affected non-carrier / unaffected biallelic member makes the evidence "not supported".
PP1_STRENGTH_BY_AFFECTED_CARRIERS: List[Tuple[int, str]] = [(7, "Strong"), (5, "Moderate"), (3, "Supporting")]

# Family-aware prioritisation: each adjustment is added to the stored Phase 3B priority score (0-100) and listed with
# its reason. The stored score itself is never modified.
PRIORITY_ADJUSTMENTS = {
    "de_novo_candidate": +8.0,
    "segregation_supported": +6.0,
    "parents_both_carriers_biallelic_proband": +6.0,
    "compound_het_in_trans": +6.0,
    "affected_non_carrier": -10.0,
    "unaffected_biallelic": -8.0,
    "recessive_single_het_proband": -6.0,
}

BENIGN = {"Benign", "Likely benign"}
CARRIER_STATES = ("het", "hom", "hemi")

# ------------------------------- genotype handling -------------------------------

VALID_GENOTYPES = ("0/0", "0/1", "1/1", "hemizygous", "unknown")


def state_of(genotype: Optional[str], sex: str, chrom: str) -> str:
    """'absent' | 'het' | 'hom' | 'hemi' | 'unknown' for one member at one variant."""
    if genotype in (None, "", "unknown"):
        return "unknown"
    male_hemi = chrom in ("chrX", "chrY") and sex == "M" and chrom != "chrPAR"
    if genotype == "hemizygous":
        return "hemi"
    if genotype == "0/0":
        return "absent"
    if genotype == "0/1":
        return "het"
    if genotype == "1/1":
        return "hemi" if male_hemi else "hom"
    return "unknown"


def is_carrier(state: str) -> bool:
    return state in CARRIER_STATES


STATE_TEXT = {"het": "heterozygous", "hom": "homozygous", "hemi": "hemizygous", "absent": "absent (reference)", "unknown": "genotype unavailable"}


class Family:
    """A pedigree plus its genotypes, ready for analysis."""

    def __init__(self, members: List[dict], rels: List[dict], genotypes: List[dict], variants: List[dict]):
        self.g = Graph(members, rels)
        self.members = self.g.members
        self.variants = {v["variant_key"]: v for v in variants}
        self.gt: Dict[Tuple[str, str], str] = {(x["member_id"], x["variant_key"]): x["genotype"] for x in genotypes}
        probands = [m for m in members if m.get("is_proband")]
        self.proband = probands[0] if probands else None

    def chrom(self, vkey: str) -> str:
        return (self.variants.get(vkey) or {}).get("chrom") or ""

    def state(self, mid: str, vkey: str) -> str:
        m = self.members[mid]
        return state_of(self.gt.get((mid, vkey)), m["sex"], self.chrom(vkey))

    def affected(self, mid: str) -> Optional[bool]:
        a = self.members[mid].get("affected")
        return True if a == "affected" else False if a == "unaffected" else None

    def label(self, mid: str) -> str:
        return self.members[mid]["label"]

    def parents(self, mid: str) -> List[dict]:
        return [self.members[p] for p in self.g.parents.get(mid, [])]

    def known_gene_variants(self, gene: str) -> List[dict]:
        return [v for v in self.variants.values() if v.get("gene") == gene]


# ------------------------------- trio / table -------------------------------

def member_states(fam: Family, vkey: str) -> List[dict]:
    rows = []
    for mid, m in fam.members.items():
        st = fam.state(mid, vkey)
        rows.append({
            "member_id": mid, "label": m["label"], "sex": m["sex"], "affected": m["affected"],
            "is_proband": bool(m.get("is_proband")), "state": st, "carrier": is_carrier(st) if st != "unknown" else None,
            "genotype": fam.gt.get((mid, vkey)),
        })
    return rows


def trio_table(fam: Family, vkey: str) -> dict:
    p = fam.proband
    if not p:
        return {"available": False, "note": "No proband is designated."}
    father, mother = fam.g.father(p["member_id"]), fam.g.mother(p["member_id"])

    def row(role: str, m: Optional[dict]) -> dict:
        if not m:
            return {"role": role, "member_id": None, "label": None, "state": "unavailable", "affected": None, "note": f"No {role.lower()} recorded in the pedigree"}
        st = fam.state(m["member_id"], vkey)
        return {"role": role, "member_id": m["member_id"], "label": m["label"], "state": st, "affected": m["affected"], "note": None}

    rows = [row("Father", father), row("Mother", mother), row("Proband", p)]
    return {"available": bool(father or mother), "rows": rows,
            "complete": bool(father and mother),
            "note": None if (father and mother) else "Trio incomplete: " + ", ".join(r["role"] for r in rows if r["state"] == "unavailable") + " not recorded."}


# ------------------------------- segregation -------------------------------

def segregation(fam: Family, vkey: str) -> dict:
    cats = {"affected_carrier": [], "affected_noncarrier": [], "unaffected_carrier": [], "unaffected_noncarrier": []}
    bi = {"affected_biallelic": [], "affected_not_biallelic": [], "unaffected_biallelic": [], "unaffected_not_biallelic": []}
    unk_gt, unk_status = [], []
    for mid in fam.members:
        st, aff = fam.state(mid, vkey), fam.affected(mid)
        if st == "unknown":
            unk_gt.append(mid)
            continue
        if aff is None:
            unk_status.append(mid)
            continue
        carrier = is_carrier(st)
        cats[("affected_" if aff else "unaffected_") + ("carrier" if carrier else "noncarrier")].append(mid)
        biallelic = st in ("hom", "hemi")
        bi[("affected_" if aff else "unaffected_") + ("biallelic" if biallelic else "not_biallelic")].append(mid)
    informative = sum(len(v) for v in cats.values())
    return {
        "counts": {k: len(v) for k, v in cats.items()},
        "members": cats,
        "biallelic_counts": {k: len(v) for k, v in bi.items()},
        "biallelic_members": bi,
        "excluded": {"unknown_genotype": unk_gt, "unknown_affected_status": unk_status},
        "informative_members": informative,
        "sufficient": informative >= 3,
        "note": None if informative >= 3 else "Insufficient family members with both genotype and affected status for a segregation assessment.",
    }


def pp1_assessment(seg: dict, model: Optional[str], proband_id: Optional[str]) -> dict:
    """PP1 status from segregation counts. `model` is 'AD', 'AR', 'XL', 'MT' or None."""
    src = "Pedigree segregation analysis"
    if model is None:
        return {"code": "PP1", "status": "insufficient", "strength": None, "source": src,
                "reason": "No inheritance model is established for this variant in this family, so co-segregation cannot be evaluated.",
                "informative_affected_carriers": 0, "conflicts": 0, "thresholds": PP1_STRENGTH_BY_AFFECTED_CARRIERS}
    if model == "AR":
        pos = seg["biallelic_members"]["affected_biallelic"]
        conflicts = seg["biallelic_members"]["affected_not_biallelic"] + seg["biallelic_members"]["unaffected_biallelic"]
        unit = "affected member(s) with the biallelic genotype"
    else:
        pos = seg["members"]["affected_carrier"]
        conflicts = seg["members"]["affected_noncarrier"]
        unit = "affected member(s) carrying the variant"
    n = len(pos)
    base = {"code": "PP1", "source": src, "informative_affected_carriers": n, "conflicts": len(conflicts),
            "conflict_members": conflicts, "thresholds": PP1_STRENGTH_BY_AFFECTED_CARRIERS, "model_used": model}
    if conflicts:
        return {**base, "status": "not_supported", "strength": None,
                "reason": f"{len(conflicts)} member(s) contradict co-segregation under the {model} model "
                          "(affected without the expected genotype, or unaffected with it); phenocopy, incomplete penetrance or "
                          "genotype errors would need to be excluded."}
    for need, strength in PP1_STRENGTH_BY_AFFECTED_CARRIERS:
        if n >= need:
            return {**base, "status": "supported", "strength": strength,
                    "reason": f"{n} {unit} (proband included) and no contradicting member; strength is a heuristic mapping, assuming full penetrance."}
    return {**base, "status": "insufficient", "strength": None,
            "reason": f"Only {n} {unit} (proband included); at least {PP1_STRENGTH_BY_AFFECTED_CARRIERS[-1][0]} are needed for supporting-level PP1."}


# ------------------------------- de novo -------------------------------

def de_novo(fam: Family, vkey: str) -> dict:
    p = fam.proband
    caveat = ("Parentage is not verified and sequencing quality (depth, genotype quality) and parental mosaicism are not assessed here; "
              "confirmatory validation is recommended before reporting as de novo.")
    if not p:
        return {"status": "cannot_assess", "assessment": "No proband designated.", "parents": [], "caveat": caveat}
    pid = p["member_id"]
    ps = fam.state(pid, vkey)
    if ps == "unknown":
        return {"status": "cannot_assess", "assessment": "Proband genotype unavailable.", "parents": [], "caveat": caveat}
    if not is_carrier(ps):
        return {"status": "not_applicable", "assessment": "Variant is absent in the proband.", "parents": [], "caveat": None}
    father, mother = fam.g.father(pid), fam.g.mother(pid)
    chrom = fam.chrom(vkey)
    need = [("Mother", mother)] if (chrom == "chrX" and p["sex"] == "M") else [("Father", father), ("Mother", mother)]
    parents, unknowns, carriers, absent = [], [], [], []
    for role, m in need:
        if not m:
            parents.append({"role": role, "state": "unavailable", "label": None})
            unknowns.append(f"{role} not recorded in the pedigree")
            continue
        st = fam.state(m["member_id"], vkey)
        parents.append({"role": role, "state": st, "label": m["label"], "member_id": m["member_id"]})
        if st == "unknown":
            unknowns.append(f"{role} genotype unavailable")
        elif is_carrier(st):
            carriers.append(role)
        else:
            absent.append(role)
    if carriers:
        return {"status": "inherited", "assessment": f"Variant present in {' and '.join(carriers).lower()}; not de novo.", "parents": parents,
                "uncertainty": unknowns, "caveat": None}
    if unknowns:
        return {"status": "cannot_assess", "assessment": "De novo status cannot be assessed: " + "; ".join(unknowns) + ".", "parents": parents,
                "uncertainty": unknowns, "caveat": None}
    return {"status": "candidate", "assessment": "Candidate de novo; confirmatory validation recommended.", "parents": parents, "uncertainty": [], "caveat": caveat}


# ------------------------------- compound heterozygosity -------------------------------

def _origin(fam: Family, mid: str, vkey: str) -> str:
    """Parental origin of an allele carried by `mid`: maternal / paternal / ambiguous / unknown / de_novo_candidate."""
    f, m = fam.g.father(mid), fam.g.mother(mid)
    if not f or not m:
        return "unknown"
    fs, ms = fam.state(f["member_id"], vkey), fam.state(m["member_id"], vkey)
    if "unknown" in (fs, ms):
        return "unknown"
    fc, mc = is_carrier(fs), is_carrier(ms)
    if fc and mc:
        return "ambiguous"
    if mc:
        return "maternal"
    if fc:
        return "paternal"
    return "de_novo_candidate"


def compound_het(fam: Family, gene: str, member_id: str) -> Optional[dict]:
    vs = [v for v in fam.known_gene_variants(gene) if v.get("classification") not in BENIGN]
    het = [v for v in vs if fam.state(member_id, v["variant_key"]) == "het"]
    if len(het) < 2:
        return None
    pairs = []
    for i in range(len(het)):
        for j in range(i + 1, len(het)):
            a, b = het[i], het[j]
            oa, ob = _origin(fam, member_id, a["variant_key"]), _origin(fam, member_id, b["variant_key"])
            if {oa, ob} == {"maternal", "paternal"}:
                phase, text = "trans", "In trans (phase supported by parental genotypes: one allele maternal, one paternal)."
            elif oa == ob and oa in ("maternal", "paternal"):
                phase, text = "cis", f"Both alleles inherited from the {oa} side, so they are on the same parental haplotype (cis); not compound heterozygous."
            else:
                phase, text = "unavailable", "Phase unavailable."
                why = []
                for v, o in ((a, oa), (b, ob)):
                    if o == "unknown":
                        why.append(f"{v.get('hgvs') or v['variant_key']}: parental genotypes incomplete")
                    elif o == "ambiguous":
                        why.append(f"{v.get('hgvs') or v['variant_key']}: carried by both parents")
                    elif o == "de_novo_candidate":
                        why.append(f"{v.get('hgvs') or v['variant_key']}: possible de novo allele")
                if why:
                    text += " " + "; ".join(why) + ". Two heterozygous variants alone do not establish compound heterozygosity."
            pairs.append({"variant_a": a["variant_key"], "variant_b": b["variant_key"], "origin_a": oa, "origin_b": ob, "phase": phase, "assessment": text,
                          "hgvs_a": a.get("hgvs"), "hgvs_b": b.get("hgvs")})
    return {"gene": gene, "member_id": member_id, "n_variants": len(het), "pairs": pairs,
            "in_trans_supported": any(p["phase"] == "trans" for p in pairs)}


# ------------------------------- inheritance models -------------------------------

def _ev(status: str, text: str) -> dict:
    return {"status": status, "text": text}


def _completeness(fam: Family, vkey: str) -> dict:
    p = fam.proband
    parents_known = 0
    if p:
        for par in fam.parents(p["member_id"]):
            if fam.state(par["member_id"], vkey) != "unknown":
                parents_known += 1
    informative = [mid for mid in fam.members if (not p or mid != p["member_id"]) and fam.state(mid, vkey) != "unknown" and fam.affected(mid) is not None]
    if parents_known >= 2 and len(informative) >= 4:
        level = "High"
    elif parents_known >= 1 or len(informative) >= 2:
        level = "Moderate"
    else:
        level = "Low"
    return {"level": level, "parents_with_genotype": parents_known, "informative_relatives": len(informative)}


def _relatives(fam: Family, vkey: str, exclude: str) -> Dict[str, List[str]]:
    out = {"aff_car": [], "aff_non": [], "unaff_car": [], "unaff_non": []}
    for mid in fam.members:
        if mid == exclude:
            continue
        st, aff = fam.state(mid, vkey), fam.affected(mid)
        if st == "unknown" or aff is None:
            continue
        out[("aff_" if aff else "unaff_") + ("car" if is_carrier(st) else "non")].append(mid)
    return out


def _names(fam: Family, ids: List[str]) -> str:
    return ", ".join(fam.label(i) for i in ids)


def assess_ad(fam: Family, vkey: str, seg: dict) -> dict:
    p = fam.proband
    ev: List[dict] = []
    res = {"model": "AD", "label": "Autosomal dominant"}
    ps = fam.state(p["member_id"], vkey)
    if ps == "unknown":
        return {**res, "verdict": "inconclusive", "evidence": [_ev("unknown", "Proband genotype unavailable.")]}
    if not is_carrier(ps):
        return {**res, "verdict": "not_consistent", "evidence": [_ev("conflicts", "Variant is absent in the proband.")]}
    ev.append(_ev("supports", f"Variant present in the proband ({STATE_TEXT[ps]})."))
    if ps == "hom":
        ev.append(_ev("note", "Proband is homozygous; a recessive model should also be considered."))
    if fam.affected(p["member_id"]) is not True:
        ev.append(_ev("note", "Proband is not recorded as affected."))
    rel = _relatives(fam, vkey, p["member_id"])
    parents = fam.parents(p["member_id"])
    aff_parent_car = [x["member_id"] for x in parents if x["member_id"] in rel["aff_car"]]
    if aff_parent_car:
        ev.append(_ev("supports", f"Variant present in affected parent ({_names(fam, aff_parent_car)})."))
    other_aff = [m for m in rel["aff_car"] if m not in aff_parent_car]
    if other_aff:
        ev.append(_ev("supports", f"Variant shared by affected relative(s): {_names(fam, other_aff)}."))
    if rel["unaff_car"]:
        ev.append(_ev("note", f"Unaffected carrier(s) ({_names(fam, rel['unaff_car'])}) require reduced penetrance, variable expressivity or age-dependent onset."))
    if rel["aff_non"]:
        ev.append(_ev("conflicts", f"Affected relative(s) without the variant ({_names(fam, rel['aff_non'])}): phenocopy, locus heterogeneity or genotype error would need to be excluded."))
    unknown_parents = [x["label"] for x in parents if fam.state(x["member_id"], vkey) == "unknown"]
    if len(parents) < 2:
        ev.append(_ev("unknown", f"{2 - len(parents)} parent(s) not recorded in the pedigree."))
    for lbl in unknown_parents:
        ev.append(_ev("unknown", f"{lbl} genotype unavailable."))
    dn = de_novo(fam, vkey)
    if dn["status"] == "candidate":
        ev.append(_ev("supports", "Both parents tested negative: a de novo dominant event is possible (see de novo assessment)."))
    if rel["aff_non"]:
        verdict = "not_consistent"
    elif aff_parent_car or other_aff:
        verdict = "consistent"
    elif dn["status"] == "candidate":
        verdict = "possible"
    elif unknown_parents or len(parents) < 2:
        verdict = "inconclusive"
    else:
        verdict = "possible"
    return {**res, "verdict": verdict, "evidence": ev}


def assess_ar(fam: Family, vkey: str, seg: dict) -> dict:
    p = fam.proband
    pid = p["member_id"]
    ev: List[dict] = []
    res = {"model": "AR", "label": "Autosomal recessive"}
    ps = fam.state(pid, vkey)
    if ps == "unknown":
        return {**res, "verdict": "inconclusive", "evidence": [_ev("unknown", "Proband genotype unavailable.")]}
    gene = (fam.variants.get(vkey) or {}).get("gene")
    ch = compound_het(fam, gene, pid) if gene else None
    biallelic = ps == "hom"
    trans = bool(ch and ch["in_trans_supported"])
    if biallelic:
        ev.append(_ev("supports", "Proband is homozygous for the variant."))
    elif ps == "het" and trans:
        ev.append(_ev("supports", f"Proband carries a second variant in {gene} in trans (phase supported by parental genotypes): compound heterozygous."))
    elif ps == "het" and ch and any(p_["phase"] == "unavailable" for p_ in ch["pairs"]):
        ev.append(_ev("unknown", f"Proband has multiple heterozygous variants in {gene} but phase is unavailable; compound heterozygosity is not established."))
    elif ps == "het":
        ev.append(_ev("conflicts", "Proband is heterozygous; a single heterozygous variant does not explain a recessive condition unless a second variant is found."))
    else:
        return {**res, "verdict": "not_consistent", "evidence": [_ev("conflicts", "Variant is absent in the proband.")]}
    parents = fam.parents(pid)
    states = [(x, fam.state(x["member_id"], vkey)) for x in parents]
    het_par = [x for x, s in states if s == "het"]
    if len(het_par) == 2:
        ev.append(_ev("supports", "Both parents are heterozygous carriers."))
    for x, s in states:
        if s == "hom" and fam.affected(x["member_id"]) is False:
            ev.append(_ev("conflicts", f"{x['label']} is homozygous but unaffected (reduced penetrance or genotype error)."))
    if biallelic and len(het_par) == 1 and any(s == "absent" for _, s in states):
        ev.append(_ev("conflicts", "Only one parent carries the variant (consider deletion, uniparental disomy, a de novo second hit or non-paternity)."))
    for x, s in states:
        if s == "unknown":
            ev.append(_ev("unknown", f"{x['label']} genotype unavailable."))
    if len(parents) < 2:
        ev.append(_ev("unknown", f"{2 - len(parents)} parent(s) not recorded in the pedigree."))
    rel = _relatives(fam, vkey, pid)
    sibs = [m for m in fam.members if m != pid and set(fam.g.parents.get(m, [])) & set(fam.g.parents.get(pid, []))]
    aff_bi = [m for m in sibs if m in seg["biallelic_members"]["affected_biallelic"]]
    if aff_bi:
        ev.append(_ev("supports", f"Affected sibling(s) share the biallelic genotype ({_names(fam, aff_bi)})."))
    unaff_bi = seg["biallelic_members"]["unaffected_biallelic"]
    if unaff_bi:
        ev.append(_ev("conflicts", f"Unaffected member(s) with the biallelic genotype: {_names(fam, unaff_bi)}."))
    aff_not_bi = [m for m in seg["biallelic_members"]["affected_not_biallelic"] if m != pid]
    if aff_not_bi:
        ev.append(_ev("conflicts", f"Affected member(s) without the biallelic genotype: {_names(fam, aff_not_bi)}."))
    conflicts = [e for e in ev if e["status"] == "conflicts"]
    parents_ok = len(het_par) == 2
    if (biallelic or trans) and not conflicts:
        verdict = "consistent" if parents_ok else "possible"
    elif conflicts:
        verdict = "not_consistent"
    else:
        verdict = "inconclusive"
    return {**res, "verdict": verdict, "evidence": ev}


def assess_xl(fam: Family, vkey: str, seg: dict) -> dict:
    p = fam.proband
    pid = p["member_id"]
    ev: List[dict] = []
    res = {"model": "XL", "label": "X-linked"}
    ps = fam.state(pid, vkey)
    if ps == "unknown":
        return {**res, "verdict": "inconclusive", "evidence": [_ev("unknown", "Proband genotype unavailable.")]}
    if not is_carrier(ps):
        return {**res, "verdict": "not_consistent", "evidence": [_ev("conflicts", "Variant is absent in the proband.")]}
    ev.append(_ev("supports", f"Variant present in the proband ({STATE_TEXT[ps]}, sex {p['sex']})."))
    if p["sex"] == "F" and ps == "het":
        ev.append(_ev("note", "Heterozygous female: X-linked dominant inheritance or skewed X-inactivation would be needed to explain an affected status."))
    mother, father = fam.g.mother(pid), fam.g.father(pid)
    if mother:
        ms = fam.state(mother["member_id"], vkey)
        if is_carrier(ms):
            ev.append(_ev("supports", f"Mother carries the variant ({STATE_TEXT[ms]})."))
        elif ms == "absent":
            ev.append(_ev("note", "Mother is negative: de novo or maternal germline mosaicism possible."))
        else:
            ev.append(_ev("unknown", "Mother genotype unavailable."))
    else:
        ev.append(_ev("unknown", "Mother not recorded in the pedigree."))
    if father and p["sex"] == "M":
        fs = fam.state(father["member_id"], vkey)
        if is_carrier(fs):
            ev.append(_ev("conflicts", "Father carries the variant and has a son carrying it: X-linked father-to-son transmission is not possible."))
    aff_non_males = [m for m in seg["members"]["affected_noncarrier"] if fam.members[m]["sex"] == "M"]
    if aff_non_males:
        ev.append(_ev("conflicts", f"Affected male(s) without the variant: {_names(fam, aff_non_males)}."))
    aff_car_rel = [m for m in seg["members"]["affected_carrier"] if m != pid]
    if aff_car_rel:
        ev.append(_ev("supports", f"Affected relative(s) carry the variant: {_names(fam, aff_car_rel)}."))
    conflicts = [e for e in ev if e["status"] == "conflicts"]
    mother_carrier = bool(mother and is_carrier(fam.state(mother["member_id"], vkey)))
    if conflicts:
        verdict = "not_consistent"
    elif p["sex"] == "M" and ps in ("hemi", "hom") and mother_carrier:
        verdict = "consistent"
    elif p["sex"] == "M" and ps in ("hemi", "hom"):
        verdict = "possible" if mother and fam.state(mother["member_id"], vkey) == "absent" else "inconclusive"
    else:
        verdict = "inconclusive"
    return {**res, "verdict": verdict, "evidence": ev}


def assess_mt(fam: Family, vkey: str, seg: dict) -> dict:
    p = fam.proband
    pid = p["member_id"]
    ev: List[dict] = []
    res = {"model": "MT", "label": "Mitochondrial (maternal)"}
    ps = fam.state(pid, vkey)
    if ps == "unknown":
        return {**res, "verdict": "inconclusive", "evidence": [_ev("unknown", "Proband genotype unavailable.")]}
    if not is_carrier(ps):
        return {**res, "verdict": "not_consistent", "evidence": [_ev("conflicts", "Variant is absent in the proband.")]}
    ev.append(_ev("supports", "Variant present in the proband."))
    mother = fam.g.mother(pid)
    if mother:
        ms = fam.state(mother["member_id"], vkey)
        ev.append(_ev("supports", "Mother carries the variant.") if is_carrier(ms) else
                  _ev("conflicts", "Mother is negative (heteroplasmy below detection or de novo mtDNA change would be needed).") if ms == "absent" else
                  _ev("unknown", "Mother genotype unavailable."))
    else:
        ev.append(_ev("unknown", "Mother not recorded in the pedigree."))
    bad = []
    for mid, m in fam.members.items():
        if m["sex"] == "M" and is_carrier(fam.state(mid, vkey)):
            for c in fam.g.children.get(mid, []):
                if is_carrier(fam.state(c, vkey)) and not (fam.g.mother(c) and is_carrier(fam.state(fam.g.mother(c)["member_id"], vkey))):
                    bad.append(f"{fam.label(mid)} -> {fam.label(c)}")
    if bad:
        ev.append(_ev("conflicts", "Carrier child of a carrier father whose mother is not a carrier: paternal transmission is not expected for mtDNA (" + "; ".join(bad) + ")."))
    ev.append(_ev("note", "Heteroplasmy level and threshold effects are not modelled."))
    conflicts = [e for e in ev if e["status"] == "conflicts"]
    mother_car = bool(mother and is_carrier(fam.state(mother["member_id"], vkey)))
    verdict = "not_consistent" if conflicts else ("consistent" if mother_car else "inconclusive")
    return {**res, "verdict": verdict, "evidence": ev}


def _normalise_reference(text: Optional[str]) -> Optional[str]:
    t = (text or "").lower()
    if "x-linked" in t or "x linked" in t:
        return "XL"
    if "mitochondrial" in t:
        return "MT"
    if "recessive" in t:
        return "AR"
    if "dominant" in t:
        return "AD"
    return None


def analyse_variant(fam: Family, vkey: str) -> dict:
    """Full family analysis for one variant. Pure function of the recorded data."""
    meta = fam.variants.get(vkey) or {}
    if not fam.proband:
        return {"variant": meta, "available": False,
                "uncertainty": ["No proband is designated; inheritance analysis needs a proband."], "models": [], "most_consistent": None}
    chrom = meta.get("chrom") or ""
    seg = segregation(fam, vkey)
    if chrom == "chrM":
        models = [assess_mt(fam, vkey, seg)]
    elif chrom == "chrX":
        models = [assess_xl(fam, vkey, seg)]
    else:
        models = [assess_ad(fam, vkey, seg), assess_ar(fam, vkey, seg)]
    comp = _completeness(fam, vkey)
    for m in models:
        m["completeness"] = comp["level"]
    order = {"consistent": 0, "possible": 1, "inconclusive": 2, "not_consistent": 3}
    ranked = sorted(models, key=lambda m: order[m["verdict"]])
    best = ranked[0] if ranked and ranked[0]["verdict"] in ("consistent", "possible") else None
    tied = [m for m in models if best and m["verdict"] == best["verdict"]]
    if len(tied) > 1:
        best = None if best["verdict"] == "possible" else best  # several equally good models: do not force one
    ref = _normalise_reference(meta.get("inheritance"))
    if best and best["verdict"] == "possible" and ref and ref != best["model"]:
        # weak ("possible") support for a model that contradicts the knowledge-graph reference must not be headlined
        best = None
    model_for_pp1 = best["model"] if best else ref
    if ref and model_for_pp1 is None:
        model_for_pp1 = ref
    pp1 = pp1_assessment(seg, model_for_pp1, fam.proband["member_id"])
    if model_for_pp1 is None and any(any(e["status"] == "conflicts" for e in m["evidence"]) for m in models)             and all(m["verdict"] == "not_consistent" for m in models):
        pp1 = {**pp1, "status": "not_supported",
               "reason": "Every tested inheritance model is contradicted by the recorded genotypes, so co-segregation is not supported."}
    dn = de_novo(fam, vkey)
    gene = meta.get("gene")
    ch = compound_het(fam, gene, fam.proband["member_id"]) if gene else None
    trio = trio_table(fam, vkey)

    uncertainty: List[str] = []
    for m in models:
        for e in m["evidence"]:
            if e["status"] == "unknown" and e["text"] not in uncertainty:
                uncertainty.append(e["text"])
    if not seg["sufficient"]:
        uncertainty.append(seg["note"])
    if ch and any(p_["phase"] == "unavailable" for p_ in ch["pairs"]):
        uncertainty.append("Phase cannot be determined for multiple heterozygous variants in " + gene + ".")
    if not best:
        uncertainty.append("Inheritance pattern inconclusive.")
    why: List[str] = []
    if best:
        why = [e["text"] for e in best["evidence"] if e["status"] == "supports"]
    return {
        "available": True, "variant": meta, "variant_key": vkey,
        "members": member_states(fam, vkey), "trio": trio, "segregation": seg,
        "models": models, "most_consistent": ({"model": best["model"], "label": best["label"], "verdict": best["verdict"]} if best else None),
        "reference_inheritance": {"text": meta.get("inheritance"), "model": ref,
                                  "agrees": (best["model"] == ref) if (best and ref) else None},
        "de_novo": dn, "compound_het": ch, "pp1": pp1, "completeness": comp,
        "why": why, "uncertainty": uncertainty,
    }


# ------------------------------- family-aware prioritisation -------------------------------

def family_prioritisation(fam: Family) -> List[dict]:
    """Each registered variant: stored base score + transparent family adjustments. The base score is never altered."""
    rows = []
    if not fam.proband:
        return rows
    pid = fam.proband["member_id"]
    for vkey, meta in fam.variants.items():
        if meta.get("classification") in BENIGN:
            continue
        ps = fam.state(pid, vkey)
        if not is_carrier(ps):
            continue
        a = analyse_variant(fam, vkey)
        adj: List[dict] = []

        def add(code: str, why: str):
            adj.append({"code": code, "delta": PRIORITY_ADJUSTMENTS[code], "reason": why})

        if a["de_novo"]["status"] == "candidate":
            add("de_novo_candidate", "Candidate de novo: both parents tested negative.")
        if a["pp1"]["status"] == "supported":
            add("segregation_supported", f"Co-segregation supported ({a['pp1']['informative_affected_carriers']} affected carriers, no contradiction).")
        seg = a["segregation"]
        if seg["members"]["affected_noncarrier"]:
            add("affected_non_carrier", "Affected relative(s) without the variant: " + ", ".join(fam.label(m) for m in seg["members"]["affected_noncarrier"]) + ".")
        if seg["biallelic_members"]["unaffected_biallelic"] and meta.get("inheritance") and "recessive" in meta["inheritance"].lower():
            add("unaffected_biallelic", "Unaffected member(s) are biallelic for a recessive-condition variant.")
        ar = next((m for m in a["models"] if m["model"] == "AR"), None)
        if ar and ps == "hom" and ar["verdict"] == "consistent":
            add("parents_both_carriers_biallelic_proband", "Homozygous proband with both parents heterozygous carriers.")
        if a["compound_het"] and a["compound_het"]["in_trans_supported"]:
            add("compound_het_in_trans", "A second variant in the same gene is in trans (phase supported).")
        ref = a["reference_inheritance"]["model"]
        if ref == "AR" and ps == "het" and not (a["compound_het"] and a["compound_het"]["in_trans_supported"]):
            add("recessive_single_het_proband", "Recessive condition but only one heterozygous variant (no second hit established in trans).")
        base = meta.get("priority_score")
        total = round(sum(x["delta"] for x in adj), 1)
        rows.append({
            "variant_key": vkey, "gene": meta.get("gene"), "hgvs": meta.get("hgvs"), "classification": meta.get("classification"),
            "base_priority_score": base, "adjustments": adj, "total_adjustment": total,
            "family_adjusted_score": None if base is None else round(max(0.0, min(100.0, base + total)), 1),
            "most_consistent_model": (a["most_consistent"] or {}).get("label"),
        })
    rows.sort(key=lambda r: (-(r["family_adjusted_score"] if r["family_adjusted_score"] is not None else -1), r["variant_key"]))
    return rows
