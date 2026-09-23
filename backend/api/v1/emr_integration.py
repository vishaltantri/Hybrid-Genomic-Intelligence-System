"""EMR integration layer (Phase 6): FHIR R4 resources + ABDM-style health ID handling.

Mapping decisions documented for the EMR/DHIS integration review:
  * Patient            -> FHIR Patient with ABHA identifier (ABDM)
  * HPO phenotype      -> FHIR Observation (code system HPO, valueBoolean/CodeableConcept)
  * Differential dx    -> FHIR Condition with `evidence` referencing the Observation ids
  * PGx alert          -> FHIR DetectedIssue (severity mapped from our critical/high/medium/low)
  * Confirmatory tests -> FHIR ServiceRequest
  * Lab report values  -> FHIR Observation with UCUM units
FHIR codes use standard systems: http://loinc.org, http://hl7.org/fhir/sid/ucum, HPO.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from uuid import uuid4

FHIR_VERSION = "4.0.1"
SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"
HPO_SYSTEM = "http://human-phenotype-ontology.org"

SEVERITY_TO_FHIR = {"critical": "high", "high": "high", "medium": "moderate", "low": "low"}


def _full_url(kind: str, rid: str) -> str:
    return f"urn:uuid:{rid}" if kind == "contained" else f"Patient/{rid}"


def to_fhir_patient(patient: dict) -> dict:
    identifiers: List[dict] = []
    if patient.get("abha_id"):
        identifiers.append({
            "system": "https://healthid.ndhm.gov.in",
            "value": patient["abha_id"],
            "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                                 "code": "MR", "display": "Medical record number"}]},
        })
    identifiers.append({"system": "urn:genomind:patient-id", "value": patient["patient_id"]})
    return {
        "resourceType": "Patient",
        "id": patient["patient_id"],
        "identifier": identifiers,
        "gender": {"M": "male", "F": "female"}.get((patient.get("sex") or "").upper(), "unknown"),
        "address": [{"state": patient.get("state", ""), "district": patient.get("district", ""),
                     "country": "IN"}],
        "extension": [
            {
                "url": "urn:genomind:community",
                "valueString": patient.get("community", ""),
            },
            {
                "url": "urn:genomind:consanguinity",
                "valueBoolean": bool(patient.get("consanguineous")),
            },
        ],
        "meta": {"profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/Patient"]},
    }


def to_fhir_observations(patient_id: str, hpo_profile: List[dict], status: str = "preliminary") -> List[dict]:
    """One Observation per mapped HPO term, carrying the mapping confidence."""
    observations = []
    for item in hpo_profile:
        observations.append({
            "resourceType": "Observation",
            "id": f"obs-{uuid4().hex[:12]}",
            "status": status,
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                      "code": "exam", "display": "Exam"}]}],
            "code": {"coding": [{"system": HPO_SYSTEM, "code": item["hpo_id"],
                                 "display": item.get("hpo_name", item["hpo_id"])}],
                     "text": item.get("evidence_text", "")},
            "subject": {"reference": f"Patient/{patient_id}"},
            "valueBoolean": True,
            "extension": [
                {"url": "urn:genomind:mapping-confidence",
                 "valueDecimal": float(item.get("confidence", 0.0))},
                {"url": "urn:genomind:mapping-method", "valueString": item.get("method", "")},
            ],
        })
    return observations


def to_fhir_condition(patient_id: str, diagnosis_entry: dict, observation_ids: Optional[List[str]] = None,
                      recorded_by: str = "") -> dict:
    """Differential diagnosis as a Condition, with the driving findings as evidence."""
    evidence = []
    for driver in (diagnosis_entry.get("driving_symptoms") or [])[:5]:
        evidence.append({
            "code": [{"coding": [{"system": HPO_SYSTEM, "code": driver["patient_term"]}]}],
            "detail": [{"reference": f"Observation/{oid}"} for oid in (observation_ids or [])[:1]],
        })
    return {
        "resourceType": "Condition",
        "id": f"cond-{uuid4().hex[:12]}",
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                       "code": "active"}]},
        "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                                           "code": "provisional"}]},
        "code": {"coding": [{"system": "https://www.orpha.net", "code": diagnosis_entry["disease_id"],
                             "display": diagnosis_entry["disease_name"]}],
                 "text": diagnosis_entry["disease_name"]},
        "subject": {"reference": f"Patient/{patient_id}"},
        "evidence": evidence,
        "note": [{"text": f"GENOMIND-INDIA AI differential, probability "
                          f"{diagnosis_entry.get('probability', 0):.4f}. "
                          f"Recorder: {recorded_by or 'system'}. Requires clinician confirmation."}],
    }


def to_fhir_detected_issue(patient_id: str, alert: dict) -> dict:
    """Pharmacogenomic risk alert as a DetectedIssue."""
    return {
        "resourceType": "DetectedIssue",
        "id": f"issue-{uuid4().hex[:12]}",
        "status": "preliminary",
        "severity": SEVERITY_TO_FHIR.get(alert.get("severity", "medium"), "moderate"),
        "code": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                             "code": "DRG", "display": "Drug interaction alert"}],
                 "text": f"{alert['drug']} x {alert['gene']} pharmacogenomic risk"},
        "patient": {"reference": f"Patient/{patient_id}"},
        "identifiedDateTime": "",
        "detail": alert.get("recommendation", ""),
        "implicated": [{"display": alert["drug"]}],
        "reference": alert.get("url", ""),
        "extension": [
            {"url": "urn:genomind:inferred-status", "valueString": alert.get("inferred_status", "")},
            {"url": "urn:genomind:risk-probability",
             "valueDecimal": float(alert.get("probability_of_risk_status", 0.0))},
            {"url": "urn:genomind:allele-frequency",
             "valueDecimal": float(alert.get("allele_frequency") or 0.0)},
        ],
    }


def to_fhir_service_request(patient_id: str, disease_name: str, test_text: str) -> dict:
    return {
        "resourceType": "ServiceRequest",
        "id": f"sr-{uuid4().hex[:12]}",
        "status": "draft",
        "intent": "proposal",
        "category": [{"coding": [{"system": "http://snomed.info/sct", "code": "108252007",
                                  "display": "Laboratory procedure"}]}],
        "code": {"text": test_text},
        "subject": {"reference": f"Patient/{patient_id}"},
        "reasonCode": {"text": disease_name},
        "note": [{"text": "Suggested confirmatory investigation from the differential diagnosis engine."}],
    }


def to_fhir_bundle(patient: dict, hpo_profile: Optional[List[dict]] = None,
                   diagnosis: Optional[dict] = None, pgx_alerts: Optional[List[dict]] = None,
                   recorded_by: str = "") -> dict:
    """Assemble a transaction Bundle for EMR ingestion."""
    entries: List[dict] = []
    patient_resource = to_fhir_patient(patient)
    entries.append({"fullUrl": f"urn:uuid:{patient_resource['id']}", "resource": patient_resource,
                    "request": {"method": "PUT", "url": f"Patient/{patient_resource['id']}"}})

    observations = to_fhir_observations(patient["patient_id"], hpo_profile or []) if hpo_profile else []
    obs_ids = [o["id"] for o in observations]
    for o in observations:
        entries.append({"fullUrl": f"urn:uuid:{o['id']}", "resource": o,
                        "request": {"method": "POST", "url": "Observation"}})

    if diagnosis and diagnosis.get("results"):
        top = diagnosis["results"][0]
        cond = to_fhir_condition(patient["patient_id"], top, obs_ids, recorded_by)
        entries.append({"fullUrl": f"urn:uuid:{cond['id']}", "resource": cond,
                        "request": {"method": "POST", "url": "Condition"}})
        tests = (top.get("confirmatory_tests") or {}).get("first_line", [])
        for t in tests[:3]:
            sr = to_fhir_service_request(patient["patient_id"], top["disease_name"], t)
            entries.append({"fullUrl": f"urn:uuid:{sr['id']}", "resource": sr,
                            "request": {"method": "POST", "url": "ServiceRequest"}})

    for alert in (pgx_alerts or [])[:10]:
        issue = to_fhir_detected_issue(patient["patient_id"], alert)
        entries.append({"fullUrl": f"urn:uuid:{issue['id']}", "resource": issue,
                        "request": {"method": "POST", "url": "DetectedIssue"}})

    return {"resourceType": "Bundle", "id": f"bundle-{uuid4().hex[:12]}", "type": "transaction",
            "entry": entries,
            "meta": {"genomind": {"fhir_version": FHIR_VERSION,
                                  "generator": "GENOMIND-INDIA",
                                  "note": "AI-generated content must be reviewed before clinical use."}}}


def parse_fhir_observation(observation: dict) -> dict:
    """Inbound mapping: a lab Observation -> the internal lab-value structure."""
    values: Dict[str, dict] = {}
    code = observation.get("code", {})
    text = code.get("text") or ""
    for coding in code.get("coding", []) or []:
        if coding.get("system") == LOINC:
            text = text or coding.get("display", "")
    quantity = observation.get("valueQuantity") or {}
    if quantity:
        values[text.lower() or "unknown"] = {
            "value": quantity.get("value"),
            "unit": quantity.get("unit", ""),
            "loinc": next((c.get("code") for c in code.get("coding", []) or []
                           if c.get("system") == LOINC), ""),
        }
    elif observation.get("valueString"):
        values[text.lower() or "unknown"] = {"value": observation["valueString"], "unit": "", "loinc": ""}
    return values


if __name__ == "__main__":
    patient = {"patient_id": "PT-DEMO1", "sex": "M", "state": "Chhattisgarh", "district": "Kondagaon",
               "community": "Gond", "consanguineous": False, "abha_id": "12-3456-7890-1234"}
    profile = [{"hpo_id": "HP:0001878", "hpo_name": "Hemolytic anemia", "confidence": 0.92,
                "method": "dictionary", "evidence_text": "khoon ki kami"}]
    diagnosis = {"results": [{"disease_id": "ORPHA:232", "disease_name": "Sickle cell disease",
                              "probability": 0.61,
                              "driving_symptoms": [{"patient_term": "HP:0001878"}],
                              "confirmatory_tests": {"first_line": ["Sickling test", "HPLC"]}}]}
    pgx = [{"drug": "primaquine", "gene": "G6PD", "severity": "critical", "inferred_status": "deficient",
            "probability_of_risk_status": 0.075, "allele_frequency": 0.075, "recommendation": "Avoid primaquine"}]
    bundle = to_fhir_bundle(patient, profile, diagnosis, pgx, recorded_by="dr_demo")
    print(f"FHIR Bundle ({FHIR_VERSION}) with {len(bundle['entry'])} entries:")
    for e in bundle["entry"]:
        print(f"  {e['request']['method']:4s} {e['request']['url']:16s} <- {e['resource']['resourceType']}")
    print("\nInbound Observation parse:",
          parse_fhir_observation({"code": {"text": "HbA2", "coding": [{"system": LOINC, "code": "4547-6"}]},
                                  "valueQuantity": {"value": 5.2, "unit": "%"}}))
