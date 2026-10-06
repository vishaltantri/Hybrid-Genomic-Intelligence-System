"""PedigreeService (Phase 3E): persistence, validation and analysis orchestration for one case's pedigree.

A *case* is a patient record (case_id == patient_id), as everywhere else in Genomera. Members, relationships and
genotypes live in the pedigree_* tables; the proband may be linked to the patient's Variant Intelligence analysis, and
member genotypes can be imported from the sample columns of that analysis' VCF.

Every mutating call validates the *resulting* pedigree and refuses to persist a change that introduces a new
structural error (impossible loops, a third parent, a parent younger than the child, duplicate edges, ...).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from backend.app import store
from ml_services.pedigree import analysis as pa
from ml_services.pedigree import structure as ps
from ml_services.variants.acmg_engine import reclassify_with_extra_criterion

SYNTHETIC_BANNER = "Sample Family — Not Clinical Data"
MAX_IMPORT = 500


class PedigreeNotFound(LookupError):
    pass


class PedigreeError(ValueError):
    """Invalid request (HTTP 422 / 409). `issues` carries structured validation messages when relevant."""

    def __init__(self, message: str, issues: Optional[List[dict]] = None, status: int = 422):
        super().__init__(message)
        self.issues = issues or []
        self.status = status


def _issue_key(i: dict) -> Tuple[str, str, Tuple[str, ...]]:
    return (i["severity"], i["code"], tuple(sorted(i.get("members", []))))


class PedigreeService:
    def __init__(self, registry: Any):
        self.registry = registry

    # ------------------------------ helpers ------------------------------

    def _patient(self, case_id: str) -> dict:
        p = store.get_patient(case_id)
        if not p:
            raise PedigreeNotFound(f"Case '{case_id}' not found")
        return p

    def _member(self, case_id: str, member_id: str) -> dict:
        m = store.ped_get_member(case_id, member_id)
        if not m:
            raise PedigreeNotFound(f"Member '{member_id}' not found in case '{case_id}'")
        return m

    def _hpo_check(self, hpo_ids: List[str]) -> List[dict]:
        onto = self.registry.twin.ontology
        bad = [h for h in hpo_ids if not onto.known(h)]
        if bad:
            raise PedigreeError(f"Unknown HPO term(s): {', '.join(bad)} (not in the Genomera knowledge graph)")
        return [{"hpo_id": h, "name": onto.name(h)} for h in dict.fromkeys(hpo_ids)]

    @staticmethod
    def _clean_member(data: dict, partial: bool = False) -> dict:
        out: Dict[str, Any] = {}
        if "label" in data or not partial:
            label = (data.get("label") or "").strip()
            if not label:
                raise PedigreeError("A member needs a label (use an anonymised label such as 'Mother' or 'II-2').")
            out["label"] = label[:60]
        if "sex" in data or not partial:
            sex = (data.get("sex") or "U").upper()
            if sex not in ps.SEXES:
                raise PedigreeError("sex must be M, F or U")
            out["sex"] = sex
        if "affected" in data or not partial:
            aff = data.get("affected") or "unknown"
            if aff not in ps.AFFECTED_STATES:
                raise PedigreeError("affected must be affected, unaffected or unknown")
            out["affected"] = aff
        for k in ("age_years", "deceased", "vcf_sample", "notes", "layout_x", "layout_y", "synthetic"):
            if k in data:
                out[k] = data[k]
        if out.get("age_years") is not None and not (0 <= int(out["age_years"]) <= 120):
            raise PedigreeError("age_years must be between 0 and 120")
        return out

    def _guard(self, case_id: str, members: List[dict], rels: List[dict], before: Optional[List[dict]] = None) -> List[dict]:
        """Raise if the (members, rels) state has structural errors that were not already present."""
        before = before if before is not None else ps.validate(store.ped_list_members(case_id), store.ped_list_relationships(case_id))
        old = {_issue_key(i) for i in before if i["severity"] == "error"}
        after = ps.validate(members, rels)
        new = [i for i in after if i["severity"] == "error" and _issue_key(i) not in old]
        if new:
            raise PedigreeError(new[0]["message"], new)
        return [i for i in after if i["severity"] in ("warning",) and _issue_key(i) not in {_issue_key(b) for b in before}]

    # ------------------------------ read ------------------------------

    def get(self, case_id: str) -> dict:
        patient = self._patient(case_id)
        members = store.ped_list_members(case_id)
        rels = store.ped_list_relationships(case_id)
        genotypes = store.ped_list_genotypes(case_id)
        variants = store.ped_list_variants(case_id)
        g = ps.Graph(members, rels)
        aligned, raw = ps.compute_generations(g)
        proband = next((m for m in members if m["is_proband"]), None)
        derived = ps.derive_relations(g, proband["member_id"]) if proband else {}
        onto = self.registry.twin.ontology
        gt_by_member: Dict[str, Dict[str, dict]] = {}
        for x in genotypes:
            gt_by_member.setdefault(x["member_id"], {})[x["variant_key"]] = {"genotype": x["genotype"], "source": x["source"]}
        out_members = []
        for m in members:
            mid = m["member_id"]
            out_members.append({
                **m, "generation": aligned.get(mid, 0),
                "relation_to_proband": derived.get(mid),
                "parents": g.parents.get(mid, []), "children": g.children.get(mid, []), "partners": sorted(g.partners.get(mid, [])),
                "phenotypes": [{"hpo_id": h, "name": onto.name(h) or h} for h in m["hpo_ids"]],
                "genotypes": gt_by_member.get(mid, {}),
            })
        analyses = [{"analysis_id": a["analysis_id"], "filename": a["filename"], "samples": a["qc_metrics"].get("samples", []),
                     "total_variants": a["qc_metrics"]["total_variants"]}
                    for a in self.registry.variants.list_analyses() if a.get("patient_id") == case_id]
        synthetic = any(m["synthetic"] for m in members)
        return {
            "case_id": case_id,
            "patient": {"patient_id": case_id, "sex": patient.get("sex"), "age_years": patient.get("age_years"), "state": patient.get("state")},
            "members": out_members, "relationships": rels, "proband_id": proband["member_id"] if proband else None,
            "validation": ps.validate(members, rels),
            "variants": variants, "analyses_available": analyses,
            "synthetic": synthetic, "synthetic_banner": SYNTHETIC_BANNER if synthetic else None,
            "legend_note": "Affected / unaffected / carrier states are shown only where they were recorded or derived from genotypes.",
        }

    # ------------------------------ members ------------------------------

    def add_member(self, case_id: str, data: dict, user: str) -> dict:
        self._patient(case_id)
        clean = self._clean_member(data)
        hpo = data.get("hpo_ids") or []
        if hpo:
            self._hpo_check(hpo)
            clean["hpo_ids"] = list(dict.fromkeys(hpo))
        existing = store.ped_list_members(case_id)
        rel = data.get("relation")
        target = None
        if rel:
            target = self._member(case_id, rel.get("to"))
            if rel.get("type") not in ("parent", "child", "partner"):
                raise PedigreeError("relation.type must be parent, child or partner")
        want_proband = bool(data.get("is_proband"))
        created = store.ped_add_member(case_id, {**clean, "is_proband": False}, user)
        try:
            if rel:
                a, b, t = {"parent": (created["member_id"], target["member_id"], ps.PARENT_OF),
                           "child": (target["member_id"], created["member_id"], ps.PARENT_OF),
                           "partner": (target["member_id"], created["member_id"], ps.PARTNER)}[rel["type"]]
                self._add_rel_checked(case_id, t, a, b, user, existing_members=existing + [created])
        except PedigreeError:
            store.ped_delete_member(case_id, created["member_id"])
            raise
        if want_proband:
            store.ped_set_proband(case_id, created["member_id"])
        store.audit(user, "pedigree.member_add", case_id, f"{created['member_id']} {created['label']}")
        return store.ped_get_member(case_id, created["member_id"])

    def update_member(self, case_id: str, member_id: str, data: dict, user: str) -> dict:
        cur = self._member(case_id, member_id)
        clean = self._clean_member(data, partial=True)
        if "hpo_ids" in data:
            self._hpo_check(data["hpo_ids"] or [])
            clean["hpo_ids"] = list(dict.fromkeys(data["hpo_ids"] or []))
        members = [({**m, **clean} if m["member_id"] == member_id else m) for m in store.ped_list_members(case_id)]
        warnings = self._guard(case_id, members, store.ped_list_relationships(case_id))
        updated = store.ped_update_member(case_id, member_id, clean)
        if data.get("is_proband"):
            store.ped_set_proband(case_id, member_id)
            updated = store.ped_get_member(case_id, member_id)
        store.audit(user, "pedigree.member_update", case_id, f"{member_id} {','.join(sorted(clean))}")
        return {**updated, "warnings": warnings, "previous": {k: cur[k] for k in clean if k in cur}}

    def delete_member(self, case_id: str, member_id: str, user: str) -> dict:
        m = self._member(case_id, member_id)
        others = [x for x in store.ped_list_members(case_id) if x["member_id"] != member_id]
        if m["is_proband"] and others:
            raise PedigreeError("The proband cannot be deleted while other members exist; designate another proband first.", status=409)
        rels = store.ped_list_relationships(case_id)
        n_rel = sum(1 for r in rels if member_id in (r["member_a"], r["member_b"]))
        n_gt = sum(1 for x in store.ped_list_genotypes(case_id) if x["member_id"] == member_id)
        store.ped_delete_member(case_id, member_id)
        store.audit(user, "pedigree.member_delete", case_id, f"{member_id} {m['label']} (relationships={n_rel}, genotypes={n_gt})")
        return {"deleted": member_id, "relationships_removed": n_rel, "genotypes_removed": n_gt}

    def set_proband(self, case_id: str, member_id: str, user: str) -> dict:
        self._member(case_id, member_id)
        store.ped_set_proband(case_id, member_id)
        store.audit(user, "pedigree.proband_set", case_id, member_id)
        return store.ped_get_member(case_id, member_id)

    def set_phenotypes(self, case_id: str, member_id: str, hpo_ids: List[str], user: str) -> dict:
        self._member(case_id, member_id)
        detail = self._hpo_check(hpo_ids)
        store.ped_update_member(case_id, member_id, {"hpo_ids": [d["hpo_id"] for d in detail]})
        store.audit(user, "pedigree.phenotypes", case_id, f"{member_id} n={len(detail)}")
        return {"member_id": member_id, "phenotypes": detail}

    def search_hpo(self, query: str, limit: int = 12) -> List[dict]:
        q = (query or "").strip().lower()
        if len(q) < 2:
            return []
        out = []
        for n in self.registry.graph.by_type("Hpo"):
            name = (n.get("name") or "")
            if q in name.lower() or q in n["id"].lower() or any(q in s.lower() for s in n.get("synonyms", [])):
                out.append({"hpo_id": n["id"], "name": name})
                if len(out) >= limit:
                    break
        return out

    # ------------------------------ relationships ------------------------------

    def _add_rel_checked(self, case_id: str, rel_type: str, a: str, b: str, user: str, existing_members: Optional[List[dict]] = None) -> dict:
        members = existing_members or store.ped_list_members(case_id)
        rels = store.ped_list_relationships(case_id)
        if a == b:
            raise PedigreeError("A member cannot be connected to themselves.", [{"severity": "error", "code": "SELF_RELATION", "message": "A member cannot be connected to themselves.", "members": [a]}])
        key = lambda r: (r["rel_type"], r["member_a"], r["member_b"]) if r["rel_type"] == ps.PARENT_OF else (r["rel_type"],) + tuple(sorted((r["member_a"], r["member_b"])))
        new = {"rel_id": "NEW", "rel_type": rel_type, "member_a": a, "member_b": b}
        if key(new) in {key(r) for r in rels}:
            raise PedigreeError("This relationship already exists.", [{"severity": "error", "code": "DUPLICATE_RELATIONSHIP", "message": "This relationship already exists.", "members": [a, b]}])
        if rel_type == ps.PARENT_OF and ps.creates_cycle(ps.Graph(members, rels), a, b):
            raise PedigreeError("That would make a member their own ancestor (impossible parent-child loop).",
                                [{"severity": "error", "code": "ANCESTOR_CYCLE", "message": "That would make a member their own ancestor.", "members": [a, b]}])
        self._guard(case_id, members, rels + [new])
        rel = store.ped_add_relationship(case_id, rel_type, a, b, user)
        store.audit(user, "pedigree.relationship_add", case_id, f"{rel_type} {a}->{b}")
        return rel

    def add_relationship(self, case_id: str, rel_type: str, a: str, b: str, user: str) -> dict:
        """rel_type: 'parent' (a is parent of b), 'child' (a is child of b) or 'partner'."""
        self._member(case_id, a)
        self._member(case_id, b)
        if rel_type == "parent":
            return self._add_rel_checked(case_id, ps.PARENT_OF, a, b, user)
        if rel_type == "child":
            return self._add_rel_checked(case_id, ps.PARENT_OF, b, a, user)
        if rel_type in ("partner", "spouse"):
            return self._add_rel_checked(case_id, ps.PARTNER, a, b, user)
        raise PedigreeError("rel_type must be parent, child or partner")

    def delete_relationship(self, case_id: str, rel_id: str, user: str) -> None:
        if not store.ped_delete_relationship(case_id, rel_id):
            raise PedigreeNotFound(f"Relationship '{rel_id}' not found in case '{case_id}'")
        store.audit(user, "pedigree.relationship_delete", case_id, rel_id)

    # ------------------------------ variants & genotypes ------------------------------

    def _patient_analysis(self, case_id: str, analysis_id: str) -> dict:
        a = self.registry.variants.get_analysis(analysis_id)
        if not a or a.get("patient_id") != case_id:
            raise PedigreeNotFound(f"Analysis '{analysis_id}' is not linked to case '{case_id}' (or is no longer in memory)")
        return a

    @staticmethod
    def _variant_payload(v: dict, analysis_id: str) -> dict:
        return {
            "gene": v.get("gene_symbol"), "hgvs": v.get("cdna") or v.get("hgvs"), "chrom": v.get("chrom"), "pos": v.get("pos"),
            "ref": v.get("ref"), "alt": v.get("alt"), "classification": v.get("acmg_classification"),
            "priority_score": v.get("priority_score"), "inheritance": v.get("inheritance"),
            "disease_id": v.get("disease_id"), "disease_name": v.get("disease_name"), "clinvar_significance": v.get("clinvar_significance"),
            "met_criteria": [{"code": c["code"], "category": c["category"], "applied_strength": c["applied_strength"], "status": c["status"]}
                             for c in (v.get("all_criteria") or []) if c.get("status") == "Met"],
            "analysis_id": analysis_id, "source": "variant_intelligence",
        }

    def register_variant(self, case_id: str, data: dict) -> str:
        if data.get("analysis_id") and data.get("variant_id"):
            a = self._patient_analysis(case_id, data["analysis_id"])
            v = next((x for x in a["variants"] if x["variant_id"] == data["variant_id"]), None)
            if not v:
                raise PedigreeNotFound(f"Variant '{data['variant_id']}' not in analysis '{data['analysis_id']}'")
            store.ped_upsert_variant(case_id, v["variant_id"], self._variant_payload(v, a["analysis_id"]))
            return v["variant_id"]
        key = (data.get("variant_key") or "").strip()
        if key:
            known = {x["variant_key"] for x in store.ped_list_variants(case_id)}
            if key in known:
                return key
            m = re.match(r"^(chr[0-9XYM]+):(\d+):([ACGTN]+)>([ACGTN]+)$", key, re.I)
            if not m or not data.get("gene"):
                raise PedigreeError("A manual variant needs variant_key like chr13:51943246:C>G and a gene symbol")
            store.ped_upsert_variant(case_id, key, {
                "gene": data["gene"], "hgvs": data.get("hgvs"), "chrom": m.group(1), "pos": int(m.group(2)), "ref": m.group(3).upper(),
                "alt": m.group(4).upper(), "classification": data.get("classification") or "Uncertain significance",
                "inheritance": data.get("inheritance"), "source": "manual", "met_criteria": []})
            return key
        raise PedigreeError("Provide analysis_id + variant_id, or variant_key + gene")

    def set_genotype(self, case_id: str, member_id: str, data: dict, user: str) -> dict:
        m = self._member(case_id, member_id)
        gt = data.get("genotype")
        if gt not in pa.VALID_GENOTYPES:
            raise PedigreeError(f"genotype must be one of {', '.join(pa.VALID_GENOTYPES)}")
        if gt == "hemizygous" and m["sex"] != "M":
            raise PedigreeError("Only a male member can be hemizygous")
        key = self.register_variant(case_id, data)
        store.ped_set_genotype(case_id, member_id, key, gt, data.get("source") or "manual", user)
        store.audit(user, "pedigree.genotype_set", case_id, f"{member_id} {key} {gt}")
        return {"member_id": member_id, "variant_key": key, "genotype": gt}

    def delete_genotype(self, case_id: str, member_id: str, variant_key: str, user: str) -> None:
        self._member(case_id, member_id)
        if not store.ped_delete_genotype(case_id, member_id, variant_key):
            raise PedigreeNotFound("Genotype not found")
        store.audit(user, "pedigree.genotype_delete", case_id, f"{member_id} {variant_key}")

    def import_vcf_genotypes(self, case_id: str, member_id: str, analysis_id: str, sample: str, user: str) -> dict:
        self._member(case_id, member_id)
        a = self._patient_analysis(case_id, analysis_id)
        samples = a["qc_metrics"].get("samples", [])
        if sample not in samples:
            raise PedigreeError(f"Sample '{sample}' is not in the VCF (samples: {', '.join(samples) or 'none'})")
        sg = a.get("sample_genotypes") or {}
        n = 0
        for v in a["variants"][:MAX_IMPORT]:
            call = (sg.get(v["variant_id"]) or {}).get(sample)
            if not call:
                continue
            store.ped_upsert_variant(case_id, v["variant_id"], self._variant_payload(v, analysis_id))
            store.ped_set_genotype(case_id, member_id, v["variant_id"], call["genotype"], f"vcf:{analysis_id}:{sample}", user)
            n += 1
        store.ped_update_member(case_id, member_id, {"vcf_sample": sample})
        store.audit(user, "pedigree.vcf_import", case_id, f"{member_id} {analysis_id}:{sample} n={n}")
        return {"member_id": member_id, "analysis_id": analysis_id, "sample": sample, "genotypes_imported": n}

    # ------------------------------ analysis ------------------------------

    def family(self, case_id: str) -> pa.Family:
        self._patient(case_id)
        return pa.Family(store.ped_list_members(case_id), store.ped_list_relationships(case_id),
                         store.ped_list_genotypes(case_id), store.ped_list_variants(case_id))

    def analyse(self, case_id: str, variant_key: str) -> dict:
        fam = self.family(case_id)
        if variant_key not in fam.variants:
            raise PedigreeNotFound(f"Variant '{variant_key}' is not registered in this pedigree")
        res = pa.analyse_variant(fam, variant_key)
        res["acmg"] = self._acmg(fam, variant_key, res)
        res["diagnosis_context"] = self.diagnosis_context(case_id, variant_key, fam=fam, analysis=res)
        res["synthetic_banner"] = SYNTHETIC_BANNER if any(m["synthetic"] for m in fam.members.values()) else None
        return res

    def _acmg(self, fam: pa.Family, vkey: str, res: dict) -> dict:
        """Show PP1 and what it would do to the stored classification (not persisted, not applied automatically)."""
        meta = fam.variants[vkey]
        pp1 = res.get("pp1")
        out = {"pp1": pp1, "stored_classification": meta.get("classification"), "classification_with_pp1": None, "changed": False,
               "note": "PP1 is shown for review; the Variant Intelligence classification is not modified."}
        if pp1 and pp1["status"] == "supported" and meta.get("met_criteria") is not None:
            if not meta["met_criteria"] and meta.get("source") == "manual":
                out["note"] = "Manually entered variant: no ACMG criteria on record, so the classification cannot be recombined."
                return out
            cls, expl = reclassify_with_extra_criterion({"all_criteria": meta["met_criteria"], "clinvar_significance": meta.get("clinvar_significance")},
                                                        "PP1", pp1["strength"])
            out.update({"classification_with_pp1": cls, "changed": cls != meta.get("classification"), "explanation": expl})
        return out

    def overview(self, case_id: str) -> dict:
        fam = self.family(case_id)
        rows = []
        if fam.proband:
            pid = fam.proband["member_id"]
            for vkey, meta in fam.variants.items():
                st = fam.state(pid, vkey)
                if not pa.is_carrier(st):
                    continue
                a = pa.analyse_variant(fam, vkey)
                rows.append({"variant_key": vkey, "gene": meta.get("gene"), "hgvs": meta.get("hgvs"), "classification": meta.get("classification"),
                             "proband_state": st, "most_consistent": a["most_consistent"], "de_novo": a["de_novo"]["status"],
                             "compound_het": bool(a["compound_het"]), "pp1": a["pp1"]["status"], "completeness": a["completeness"]["level"]})
        return {"case_id": case_id, "variants": rows}

    def prioritisation(self, case_id: str) -> dict:
        fam = self.family(case_id)
        return {"case_id": case_id, "rows": pa.family_prioritisation(fam),
                "method": "Stored Phase 3B priority score + listed family adjustments (weights in ml_services/pedigree/analysis.py). "
                          "The stored score is never modified.", "weights": pa.PRIORITY_ADJUSTMENTS}

    def diagnosis_context(self, case_id: str, variant_key: Optional[str] = None, fam: Optional[pa.Family] = None, analysis: Optional[dict] = None) -> dict:
        fam = fam or self.family(case_id)
        patient = store.get_patient(case_id) or {}
        if not fam.proband or not fam.proband.get("hpo_ids"):
            return {"available": False, "note": "Insufficient data: the proband has no phenotypes recorded in the pedigree."}
        hpos = fam.proband["hpo_ids"]
        res = self.registry.diagnosis.diagnose(sorted(hpos), {"state": patient.get("state") or "", "community": patient.get("community") or "",
                                                              "sex": fam.proband["sex"] if fam.proband["sex"] in ("M", "F") else (patient.get("sex") or "")}, top_k=5)
        a = analysis
        best = (a or {}).get("most_consistent")
        gene = (fam.variants.get(variant_key) or {}).get("gene") if variant_key else None
        rows = []
        for r in res.get("results", []):
            ref = pa._normalise_reference(r.get("inheritance"))
            rows.append({"disease_id": r["disease_id"], "disease_name": r["disease_name"], "probability": r["probability"], "inheritance": r.get("inheritance"),
                         "genes": r.get("genes", []), "gene_has_family_variant": bool(gene and gene in r.get("genes", [])),
                         "pattern_compatible": (None if not (best and ref) else best["model"] == ref)})
        summary = None
        if best:
            summary = f"Pedigree pattern: {best['verdict'].replace('_', ' ')} with {best['label'].lower()} inheritance (evidence completeness {a['completeness']['level']})."
        elif a:
            summary = "Pedigree pattern: inconclusive for the selected variant."
        return {"available": True, "pedigree_pattern": summary, "candidates": rows,
                "note": "The diagnosis engine's ranking is unchanged (phenotype + population prior); the pedigree adds compatibility context only."}

    # ------------------------------ reproductive hand-off ------------------------------

    def reproductive_context(self, case_id: str, partner_a: Optional[str] = None, partner_b: Optional[str] = None) -> dict:
        fam = self.family(case_id)
        patient = store.get_patient(case_id) or {}
        g = fam.g
        if not partner_a or not partner_b:
            if not fam.proband:
                raise PedigreeError("No proband: choose the two partners explicitly.")
            pr = g.parents.get(fam.proband["member_id"], [])
            if len(pr) < 2:
                raise PedigreeError("Both parents of the proband must be recorded (or choose two partners explicitly) to estimate recurrence risk.")
            partner_a, partner_b = pr[0], pr[1]
        for x in (partner_a, partner_b):
            self._member(case_id, x)
        graph = self.registry.graph

        def partner(mid: str) -> dict:
            m = fam.members[mid]
            carrier: Dict[str, bool] = {}
            affected: Dict[str, bool] = {}
            for vkey, meta in fam.variants.items():
                if meta.get("classification") in pa.BENIGN or not meta.get("gene"):
                    continue
                st = fam.state(mid, vkey)
                if st == "unknown":
                    continue
                for d in graph.neighbors(meta["gene"], "ASSOCIATED_WITH"):
                    if d.get("type") != "Disease":
                        continue
                    inh = (d.get("inheritance") or "").lower()
                    if pa.is_carrier(st):
                        if "recessive" in inh and st == "het":
                            carrier[d["id"]] = True
                        if m["affected"] == "affected" and (st in ("hom", "hemi") or "dominant" in inh):
                            affected[d["id"]] = True
                    elif d["id"] not in carrier:
                        carrier.setdefault(d["id"], False)
            return {"state": patient.get("state"), "sex": m["sex"] if m["sex"] in ("M", "F") else None, "age": m.get("age_years"),
                    "known_carrier": carrier, "known_affected": affected}

        a, b = partner(partner_a), partner(partner_b)
        key = ps.consanguinity_key(g, partner_a, partner_b)
        if key in ("first_cousins", "uncle_niece", "second_cousins"):
            a["relationship"] = key
        result = self.registry.counselor.couple_assessment(a, b, top_n=10)
        return {"case_id": case_id, "partners": [{"member_id": partner_a, "label": fam.label(partner_a)}, {"member_id": partner_b, "label": fam.label(partner_b)}],
                "relationship_from_pedigree": key, "partner_inputs": {"a": a, "b": b}, "assessment": result,
                "note": "Carrier and affected statuses come from the pedigree's recorded genotypes via knowledge-graph gene-disease links; the Mendelian "
                        "calculation is the existing reproductive engine's."}

    # ------------------------------ summaries for Twin / AI ------------------------------

    def summary(self, case_id: str) -> dict:
        members = store.ped_list_members(case_id)
        if not members:
            return {"exists": False}
        rels = store.ped_list_relationships(case_id)
        issues = ps.validate(members, rels)
        fam = pa.Family(members, rels, store.ped_list_genotypes(case_id), store.ped_list_variants(case_id))
        ov = self.overview(case_id)["variants"]
        return {"exists": True, "members": len(members), "relationships": len(rels),
                "proband": next((m["label"] for m in members if m["is_proband"]), None),
                "affected": sum(1 for m in members if m["affected"] == "affected"),
                "validation_errors": sum(1 for i in issues if i["severity"] == "error"),
                "validation_warnings": sum(1 for i in issues if i["severity"] == "warning"),
                "synthetic": any(m["synthetic"] for m in members), "variants": ov}

    def ai_context(self, case_id: str, variant_key: Optional[str] = None) -> dict:
        data = self.get(case_id)
        lines = []
        if not data["members"]:
            lines.append("PEDIGREE: no family members are recorded for this case.")
        else:
            if data["synthetic"]:
                lines.append(SYNTHETIC_BANNER.upper() + ".")
            lines.append(f"PEDIGREE for case {case_id}: {len(data['members'])} members, proband = "
                         f"{next((m['label'] for m in data['members'] if m['is_proband']), 'not designated')}.")
            for m in data["members"]:
                lines.append(f"- {m['label']} ({m['relation_to_proband'] or 'relation unknown'}; sex {m['sex']}; {m['affected']}; "
                             f"HPO: {', '.join(p['name'] for p in m['phenotypes']) or 'none recorded'})")
            for i in data["validation"]:
                lines.append(f"VALIDATION {i['severity']}: {i['message']}")
        cites = [{"source_type": "Pedigree", "identifier": case_id, "title": f"Pedigree of case {case_id}",
                  "summary": f"{len(data['members'])} members", "reliability": "Recorded family data"}]
        if variant_key:
            try:
                a = self.analyse(case_id, variant_key)
            except PedigreeNotFound:
                a = None
            if a and a.get("available"):
                v = a["variant"]
                lines.append(f"SELECTED VARIANT {v.get('gene')} {v.get('hgvs')} ({v.get('classification')}).")
                for r in a["members"]:
                    lines.append(f"  genotype {r['label']}: {pa.STATE_TEXT[r['state']]} ({r['affected']})")
                for mdl in a["models"]:
                    lines.append(f"MODEL {mdl['label']}: {mdl['verdict']} — " + " | ".join(f"[{e['status']}] {e['text']}" for e in mdl["evidence"]))
                lines.append(f"DE NOVO: {a['de_novo']['assessment']}")
                if a["compound_het"]:
                    lines.append("COMPOUND HET: " + " | ".join(p["assessment"] for p in a["compound_het"]["pairs"]))
                lines.append(f"SEGREGATION counts: {a['segregation']['counts']}; PP1 {a['pp1']['status']} ({a['pp1']['reason']})")
                if a["uncertainty"]:
                    lines.append("UNCERTAINTY: " + "; ".join(a["uncertainty"]))
                lines.append(f"Evidence completeness: {a['completeness']['level']}")
                cites.append({"source_type": "Pedigree Analysis", "identifier": variant_key, "title": f"{v.get('gene')} family analysis",
                              "summary": (a["most_consistent"] or {}).get("label", "inconclusive"), "reliability": "Computational Inference"})
        return {"text": "\n".join(lines), "citations": cites, "summary": {"pedigree": True, "pedigree_variant": variant_key}}

    # ------------------------------ synthetic demo ------------------------------

    def demo_family(self, case_id: str, user: str) -> dict:
        """Synthetic/Test family from the verified demo trio VCF (sample columns PROBAND / MOTHER / FATHER)."""
        patient = self._patient(case_id)
        if store.ped_list_members(case_id):
            raise PedigreeError("This case already has a pedigree; the demo family can only be created on an empty one.", status=409)
        analyses = [a for a in self.registry.variants.list_analyses() if a.get("patient_id") == case_id and {"PROBAND", "MOTHER", "FATHER"} <= set(a["qc_metrics"].get("samples", []))]
        if analyses:
            analysis_id = analyses[0]["analysis_id"]
        else:
            from ml_services.config import SEEDS_DIR

            text = (SEEDS_DIR / "clinical_sample_trio.vcf").read_text(encoding="utf-8")
            hpo = self.registry.twin.ontology
            hp = sorted({h for h in (self.registry.twin.load_core(case_id)["hpo_ids"])})
            analysis_id = self.registry.variants.analyze_vcf(text, filename="clinical_sample_trio.vcf", patient_id=case_id,
                                                              patient_hpo_ids=hp, created_by=user)["analysis_id"]
        hp = self.registry.twin.load_core(case_id)["hpo_ids"]
        sex = patient.get("sex") if patient.get("sex") in ("M", "F") else "U"
        common = {"synthetic": True, "notes": SYNTHETIC_BANNER}
        father = self.add_member(case_id, {"label": "Father", "sex": "M", "affected": "unaffected", "vcf_sample": "FATHER", **common}, user)
        mother = self.add_member(case_id, {"label": "Mother", "sex": "F", "affected": "unaffected", "vcf_sample": "MOTHER", **common}, user)
        proband = self.add_member(case_id, {"label": "Proband", "sex": sex, "affected": "affected", "is_proband": True, "vcf_sample": "PROBAND",
                                            "age_years": patient.get("age_years"), "hpo_ids": hp, **common}, user)
        self.add_relationship(case_id, "partner", father["member_id"], mother["member_id"], user)
        self.add_relationship(case_id, "parent", father["member_id"], proband["member_id"], user)
        self.add_relationship(case_id, "parent", mother["member_id"], proband["member_id"], user)
        imported = {}
        for m in (father, mother, proband):
            imported[m["label"]] = self.import_vcf_genotypes(case_id, m["member_id"], analysis_id, m["vcf_sample"], user)["genotypes_imported"]
        return {"case_id": case_id, "analysis_id": analysis_id, "imported": imported, "banner": SYNTHETIC_BANNER}
