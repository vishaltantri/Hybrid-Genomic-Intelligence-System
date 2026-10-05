"""DigitalTwinService (Phase 3D): builds the Twin, snapshots, and runs persisted scenarios.

The service owns *no* clinical models. It composes data that other modules already produce
(patient store, Variant Intelligence session, DifferentialDiagnosisEngine, PGxEngine,
Knowledge Graph) into one versioned, provenance-tagged state object.

Isolation: the Twin is built strictly from records keyed by `patient_id`. Variant analyses
are only used if their own `patient_id` equals the requested patient, so Twin A can never
contain data from patient B. Scenarios and saved snapshots are stored per (patient, user).
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.app import store
from ml_services.twin import twin_state as ts
from ml_services.twin.anatomy import build_anatomy
from ml_services.twin.scenario_engine import SCENARIO_TYPES, UNSUPPORTED, DISCLAIMER, ScenarioEngine, ScenarioError

TWIN_SCHEMA_VERSION = "1.0"

CLINICAL_LIMITATIONS = [
    "Computational decision-support simulation - not a physiological measurement.",
    "No vitals, laboratory values, disease progression, treatment response or survival are modelled.",
    "Phenotype onset and severity are not recorded in the case data.",
    "Family structure, segregation and de novo status are not stored.",
]


class TwinNotFound(LookupError):
    pass


class DigitalTwinService:
    def __init__(self, registry: Any):
        self.registry = registry
        self._ontology: Optional[ts.HpoOntology] = None
        self._engine: Optional[ScenarioEngine] = None

    # ------------------------------ lazy deps ------------------------------

    @property
    def ontology(self) -> ts.HpoOntology:
        if self._ontology is None or self._ontology.graph is not self.registry.graph:
            self._ontology = ts.HpoOntology(self.registry.graph)
            self._engine = None
        return self._ontology

    @property
    def engine(self) -> ScenarioEngine:
        onto = self.ontology
        if self._engine is None:
            self._engine = ScenarioEngine(self.registry.graph, self.registry.diagnosis, self.registry.pgx, onto)
        return self._engine

    # ------------------------------ core assembly ------------------------------

    def _patient_analyses(self, patient_id: str) -> List[dict]:
        return [a for a in self.registry.variants.list_analyses() if a.get("patient_id") == patient_id]

    def load_core(self, patient_id: str, analysis_id: Optional[str] = None) -> dict:
        """Raw, targeted reads for one patient: 1 patient row, 1 events query, in-memory analyses."""
        patient = store.get_patient(patient_id)
        if not patient:
            raise TwinNotFound(f"Patient '{patient_id}' not found")
        events = sorted(store.list_events(patient_id), key=lambda e: e.get("created_utc") or "")
        analyses = self._patient_analyses(patient_id)
        selected = None
        if analysis_id:
            if analysis_id not in {a["analysis_id"] for a in analyses}:
                raise TwinNotFound(f"Analysis '{analysis_id}' is not linked to patient '{patient_id}'")
            selected = self.registry.variants.get_analysis(analysis_id)
        elif analyses:
            selected = self.registry.variants.get_analysis(analyses[0]["analysis_id"])  # newest first

        records = ts.collect_phenotype_records(patient, events)
        # drop HPO ids the graph cannot resolve from the *computational* set; they stay visible in the state
        hpo_ids = sorted(h for h in records if self.ontology.known(h))
        return {
            "patient": patient, "events": events, "analyses": analyses, "analysis": selected,
            "variants": list(selected["variants"]) if selected else [],
            "phenotype_records": records, "hpo_ids": hpo_ids,
            "context": {"state": patient.get("state") or "", "community": patient.get("community") or "",
                        "sex": patient.get("sex") or ""},
        }

    # ------------------------------ build twin ------------------------------

    def build_twin(self, patient_id: str, analysis_id: Optional[str] = None) -> dict:
        core = self.load_core(patient_id, analysis_id)
        patient, events, analysis = core["patient"], core["events"], core["analysis"]
        graph = self.registry.graph

        phenotype = ts.build_phenotype_state(core["phenotype_records"], self.ontology, events)
        genomic = ts.build_genomic_state(analysis, core["analyses"], core["hpo_ids"])
        diagnosis = ts.evaluate_diagnosis_state(self.registry.diagnosis, graph, core["hpo_ids"], core["context"],
                                                core["variants"], top_k=10, explain=True,
                                                _cache=self.engine._dx_cache)
        # "Missing" phenotypes are findings expected for the top diagnosis that are NOT documented.
        top = diagnosis.get("top_diagnosis")
        phenotype["expected_but_undocumented"] = (top or {}).get("missing_findings", []) if top else []
        phenotype["expected_for"] = top["disease_name"] if top else None
        pgx = ts.build_pgx_state(self.registry.pgx, core["variants"], patient)
        anatomy = build_anatomy(graph, self.ontology, phenotype, genomic.get("variants", []), diagnosis)
        family = ts.build_family_state(patient, analysis)
        # Phase 3E: the pedigree module owns the family representation; the Twin only reads its summary.
        family["pedigree"] = self.registry.pedigree.summary(patient_id)
        if family["pedigree"]["exists"]:
            family["available"], family["note"] = True, None
        timeline = ts.build_timeline(patient, events, core["analyses"])

        cons_rate = self.registry.diagnosis.state_consanguinity.get(
            self.registry.diagnosis._match_state(patient.get("state") or ""))
        demographic = {
            "age_years": patient.get("age_years"), "sex": patient.get("sex"), "state": patient.get("state"),
            "district": patient.get("district"), "community": patient.get("community"),
            "consanguineous": bool(patient.get("consanguineous")),
            "state_consanguinity_rate": cons_rate,
        }
        provenance = self._provenance(core, phenotype, diagnosis)
        twin = {
            "schema_version": TWIN_SCHEMA_VERSION,
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "identity": {"patient_id": patient["patient_id"], "case_id": patient["patient_id"],
                         "registered_utc": patient.get("created_utc"),
                         "case_note": "The patient record is the case; the platform has no separate case entity."},
            "demographic": demographic,
            "phenotype": phenotype, "genomic": genomic, "diagnosis": diagnosis,
            "pgx": pgx, "family": family, "timeline": timeline, "anatomy": anatomy,
            "provenance": provenance,
            "scenario_types": [{"id": k, "label": v} for k, v in SCENARIO_TYPES.items()],
            "unsupported_simulations": [{"id": k, "label": v,
                                         "message": "This simulation is not available from the current "
                                                    "clinical data/model."} for k, v in UNSUPPORTED.items()],
            "limitations": CLINICAL_LIMITATIONS,
            "disclaimer": DISCLAIMER,
        }
        twin["snapshot"] = self._snapshot_from_twin(twin)
        return twin

    def _provenance(self, core: dict, phenotype: dict, diagnosis: dict) -> List[dict]:
        out: List[dict] = [{
            "section": "identity", "source": "Patient registry", "ref": core["patient"]["patient_id"],
            "timestamp_utc": core["patient"].get("created_utc"), "detail": "Demographics and registration"}]
        seen = set()
        for rec in phenotype["observed"]:
            for s in rec["sources"]:
                key = (s["type"], s["ref"])
                if key in seen:
                    continue
                seen.add(key)
                out.append({"section": "phenotype", "source": s["label"], "ref": s["ref"],
                            "timestamp_utc": s.get("timestamp"), "detail": f"{s['type']}"})
        a = core["analysis"]
        if a:
            out.append({"section": "genomic", "source": "Variant Intelligence analysis", "ref": a["analysis_id"],
                        "timestamp_utc": ts._iso(a["timestamp"]), "detail": a["filename"]})
            out.append({"section": "pgx", "source": "Variant Intelligence analysis + PGx rule engine",
                        "ref": a["analysis_id"], "timestamp_utc": ts._iso(a["timestamp"]),
                        "detail": "Star alleles from the analysis; drug-gene rules from CPIC/PharmGKB seeds"})
        if diagnosis.get("available"):
            last = [e for e in core["events"] if e["kind"] == "diagnosis"]
            out.append({"section": "diagnosis", "source": "DifferentialDiagnosisEngine (computed now)",
                        "ref": diagnosis.get("engine"), "timestamp_utc": None,
                        "detail": "Run live on the Twin's phenotype state; last stored diagnosis event: "
                                  + (f"{last[-1]['event_id']} at {last[-1]['created_utc']}" if last else "none")})
        fam = (core["patient"].get("extra") or {})
        if fam.get("family_history") or fam.get("known_carrier") or fam.get("known_affected"):
            out.append({"section": "family", "source": "Patient record", "ref": core["patient"]["patient_id"],
                        "timestamp_utc": core["patient"].get("created_utc"), "detail": "Family history fields"})
        for ev in core["events"]:
            if ts._event_title(ev):
                out.append({"section": "timeline", "source": f"Clinical event ({ev['kind']})", "ref": ev["event_id"],
                            "timestamp_utc": ev["created_utc"], "detail": ""})
        return out

    # ------------------------------ snapshot ------------------------------

    def _snapshot_from_twin(self, twin: dict) -> dict:
        g, ph, dx = twin["genomic"], twin["phenotype"], twin["diagnosis"]
        c = g["counts"]
        top = dx.get("top_diagnosis")
        content = {
            "patient_id": twin["identity"]["patient_id"],
            "case_id": twin["identity"]["case_id"],
            "phenotypes": ph["count"],
            "variants": c["total"], "pathogenic": c["pathogenic"], "likely_pathogenic": c["likely_pathogenic"],
            "vus": c["vus"], "benign_or_likely_benign": c["benign_likely_benign"],
            "analysis_id": g.get("analysis_id"),
            "top_diagnosis": ({"disease_id": top["disease_id"], "disease_name": top["disease_name"],
                               "probability": top["probability"]} if top else None),
            "pgx_findings": [{"gene": f["gene"], "drug": f["drug"], "severity": f["severity"]}
                             for f in twin["pgx"]["findings"]],
            "sections_with_data": {k: bool(twin[k].get("available")) for k in
                                   ("phenotype", "genomic", "diagnosis", "pgx", "family", "timeline")},
            "hpo_ids": sorted(r["hpo_id"] for r in ph["observed"]),
        }
        stamps = [p["timestamp_utc"] for p in twin["provenance"] if p.get("timestamp_utc")]
        digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:12]
        return {**content, "snapshot_version": f"TS-{digest}", "last_updated_utc": max(stamps) if stamps else None,
                "generated_utc": twin["generated_utc"], "schema_version": TWIN_SCHEMA_VERSION}

    def build_snapshot(self, patient_id: str, analysis_id: Optional[str] = None) -> dict:
        return self.build_twin(patient_id, analysis_id)["snapshot"]

    def save_snapshot(self, patient_id: str, username: str, analysis_id: Optional[str] = None) -> dict:
        snap = self.build_snapshot(patient_id, analysis_id)
        prior = store.list_twin_records(patient_id, "snapshot", username, limit=500)
        snap = {**snap, "sequence": len(prior) + 1,
                "changed_since_previous": (not prior) or prior[0]["payload"]["snapshot_version"] != snap["snapshot_version"]}
        rec = store.add_twin_record(f"SNAP-{uuid.uuid4().hex[:8].upper()}", patient_id, "snapshot", username, snap)
        return {**snap, "record_id": rec["record_id"], "saved_utc": rec["created_utc"]}

    def list_snapshots(self, patient_id: str, username: str) -> List[dict]:
        return [{**r["payload"], "record_id": r["record_id"], "saved_utc": r["created_utc"]}
                for r in store.list_twin_records(patient_id, "snapshot", username)]

    # ------------------------------ timeline ------------------------------

    def build_timeline(self, patient_id: str) -> dict:
        patient = store.get_patient(patient_id)
        if not patient:
            raise TwinNotFound(f"Patient '{patient_id}' not found")
        return ts.build_timeline(patient, store.list_events(patient_id), self._patient_analyses(patient_id))

    # ------------------------------ scenarios ------------------------------

    def create_scenario(self, patient_id: str, username: str, spec: dict,
                        analysis_id: Optional[str] = None) -> dict:
        core = self.load_core(patient_id, analysis_id)       # raises TwinNotFound
        result = self.engine.run(core, spec)                  # raises ScenarioError
        result["patient_id"] = patient_id
        result["analysis_id"] = (core["analysis"] or {}).get("analysis_id")
        result["created_by"] = username
        result["created_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        result["baseline_snapshot_version"] = self._snapshot_version_for(core)
        store.add_twin_record(result["scenario_id"], patient_id, "scenario", username, result)
        return result

    def _snapshot_version_for(self, core: dict) -> str:
        # Cheap fingerprint of the exact inputs the baseline was computed from.
        key = json.dumps({"hpo": core["hpo_ids"], "analysis": (core["analysis"] or {}).get("analysis_id"),
                          "n_variants": len(core["variants"])}, sort_keys=True)
        return "BASE-" + hashlib.sha256(key.encode()).hexdigest()[:10]

    def get_scenario(self, patient_id: str, username: str, scenario_id: str) -> Optional[dict]:
        rec = store.get_twin_record(scenario_id, patient_id, username)
        return rec["payload"] if rec else None

    def list_scenarios(self, patient_id: str, username: str) -> List[dict]:
        return [{"scenario_id": r["record_id"], "name": r["payload"].get("name"),
                 "type": r["payload"].get("type"), "type_label": r["payload"].get("type_label"),
                 "created_utc": r["created_utc"],
                 "top_diagnosis_changed": (r["payload"].get("diff") or {}).get("top_diagnosis_changed")}
                for r in store.list_twin_records(patient_id, "scenario", username)]

    def delete_scenario(self, patient_id: str, username: str, scenario_id: str) -> bool:
        return store.delete_twin_record(scenario_id, patient_id, username)

    # ------------------------------ integrations ------------------------------

    def assistant_context(self, patient_id: str, username: str, scenario_id: Optional[str] = None,
                          analysis_id: Optional[str] = None) -> Dict[str, Any]:
        """Compact grounding text + citations for the AI Assistant (built from the live Twin)."""
        twin = self.build_twin(patient_id, analysis_id)
        snap, dx, g = twin["snapshot"], twin["diagnosis"], twin["genomic"]
        lines = [f"DIGITAL TWIN ({snap['snapshot_version']}, computational decision-support, not physiological): "
                 f"patient {patient_id}; {snap['phenotypes']} phenotypes; {snap['variants']} variants "
                 f"(P={snap['pathogenic']}, LP={snap['likely_pathogenic']}, VUS={snap['vus']})."]
        if dx.get("available"):
            lines.append("Twin differential: " + "; ".join(
                f"#{d['rank']} {d['disease_name']} p={d['probability']} "
                f"(P/LP variants={d['genomic_support']['pathogenic_or_likely']}, VUS={d['genomic_support']['vus']})"
                for d in dx["differential"][:5]))
        else:
            lines.append("Twin differential: " + (dx.get("note") or ts.INSUFFICIENT))
        if g.get("available"):
            lines.append("Top variants: " + "; ".join(
                f"{v['gene_symbol']} {v.get('cdna') or v.get('hgvs')} {v['acmg_classification']} "
                f"(priority {v['priority_score']})" for v in g["variants"][:5]))
        lines.append("PGx: " + ("; ".join(f"{f['drug']}/{f['gene']} {f['severity']}" for f in twin["pgx"]["findings"])
                                or twin["pgx"]["note"] or "no findings"))
        lines.append(f"Timeline: {twin['timeline']['note'] or str(len(twin['timeline']['events'])) + ' events'}.")
        cites = [{"source_type": "Digital Twin", "identifier": snap["snapshot_version"],
                  "title": f"Twin snapshot for {patient_id}",
                  "summary": f"{snap['phenotypes']} phenotypes, {snap['variants']} variants",
                  "reliability": "Computational Inference"}]
        summary = {"twin": True, "twin_snapshot": snap["snapshot_version"], "twin_scenario": None}
        if scenario_id:
            sc = self.get_scenario(patient_id, username, scenario_id)
            if not sc:
                raise TwinNotFound(f"Scenario '{scenario_id}' not found")
            lines.append(f"SCENARIO '{sc['name']}' ({sc['type_label']}): " + " | ".join(sc["explanation"]))
            lines.append("Scenario comparison: " + "; ".join(
                f"{r['label']}: {r['baseline']} -> {r['scenario']}" for r in sc["comparison"]))
            lines.append("Scenario limitations: " + " ".join(sc["limitations"]))
            cites.append({"source_type": "Digital Twin Scenario", "identifier": sc["scenario_id"],
                          "title": sc["name"], "summary": sc["type_label"],
                          "reliability": "Computational Inference"})
            summary["twin_scenario"] = scenario_id
        return {"text": "\n".join(lines), "citations": cites, "summary": summary}

    def report_handoff(self, patient_id: str, username: str, scenario_ids: List[str],
                       analysis_id: Optional[str] = None, note: str = "") -> dict:
        snap = self.build_snapshot(patient_id, analysis_id)
        scenarios = []
        for sid in scenario_ids:
            sc = self.get_scenario(patient_id, username, sid)
            if not sc:
                raise TwinNotFound(f"Scenario '{sid}' not found")
            scenarios.append({k: sc[k] for k in ("scenario_id", "name", "type_label", "modification", "comparison",
                                                 "explanation", "limitations", "created_utc")})
        bundle = {"patient_id": patient_id, "snapshot_version": snap["snapshot_version"], "snapshot": snap,
                  "scenarios": scenarios, "clinical_notes": note or "Digital Twin snapshot added to report.",
                  "disclaimer": DISCLAIMER, "added_by": username, "status": "ready_for_review"}
        event = store.add_event(patient_id, "twin_report_bundle", bundle)
        return {**bundle, "event_id": event["event_id"], "added_utc": event["created_utc"]}
