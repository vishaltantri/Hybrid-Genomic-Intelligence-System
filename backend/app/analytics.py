"""Phase 16: real, privacy-preserving aggregate analytics computed from the live database.

Rules: every number is a COUNT or ratio over stored rows; nothing is estimated or back-filled. Aggregates never carry
patient identifiers. Researchers (aggregate-only role) get small-cell suppression. Results are cached briefly.
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from datetime import date, datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from backend.app import store

MIN_CELL = int(os.environ.get("GENOMERA_MIN_CELL", "5"))   # applied to researcher role only
CACHE_TTL = float(os.environ.get("GENOMERA_ANALYTICS_TTL", "15"))
MIN_SERIES_POINTS = 3
MIN_CASES_FOR_COOCCURRENCE = 10
_CACHE: Dict[tuple, Tuple[float, object]] = {}

MODEL_SCORE_NOTE = "Model score: a ranked statistical suggestion from the diagnosis engine. It is not a clinical diagnosis."


class AnalyticsError(ValueError):
    pass


def clear_cache() -> None:
    _CACHE.clear()


def cached(key: tuple, fn: Callable[[], object]):
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def parse_range(start: Optional[str], end: Optional[str]) -> Tuple[str, str]:
    def one(v: Optional[str], default: str) -> str:
        if not v:
            return default
        try:
            return date.fromisoformat(v).isoformat()
        except ValueError as exc:
            raise AnalyticsError(f"Invalid date '{v}'. Use YYYY-MM-DD.") from exc
    s, e = one(start, "0001-01-01"), one(end, "9999-12-31")
    if s > e:
        raise AnalyticsError("The start date is after the end date.")
    return s, e


def _rows(sql: str, args: Iterable = ()) -> List[dict]:
    with store._connect() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(args)).fetchall()]


def _one(sql: str, args: Iterable = ()) -> int:
    with store._connect() as conn:
        return conn.execute(sql, tuple(args)).fetchone()[0] or 0


def suppress(counts: Dict[str, int], role: str) -> Tuple[List[dict], int]:
    """Bar-chart rows sorted by count. For researchers, categories below MIN_CELL are merged into one suppressed bucket."""
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if role != "researcher":
        return [{"label": k, "count": v} for k, v in items], 0
    keep = [{"label": k, "count": v} for k, v in items if v >= MIN_CELL]
    hidden = sum(v for k, v in items if v < MIN_CELL)
    return keep, hidden


def _section(data: dict, role: str, note: Optional[str] = None) -> dict:
    return {**data, "privacy": {"identifiers_included": False, "small_cell_suppression": MIN_CELL if role == "researcher" else None}, **({"note": note} if note else {})}


# ------------------------------------------------------------------ variants source

def _variant_records(registry) -> Tuple[List[dict], int]:
    """(variant rows with analysis timestamp, analysis count). Rows are identifier-free copies of what is aggregated."""
    out, n = [], 0
    for a in registry.variants.list_analyses():
        full = registry.variants.get_analysis(a["analysis_id"]) or {}
        n += 1
        ts = datetime.fromtimestamp(a["timestamp"], timezone.utc).isoformat()   # engine stores epoch seconds
        for v in full.get("variants", []):
            out.append({"ts": ts, "gene": v.get("gene_symbol"), "acmg": v.get("acmg_classification"),
                        "clinvar": v.get("clinvar_significance"), "disease": v.get("disease_name"),
                        "pgx_gene": v.get("gene_symbol") if v.get("pgx_star_allele") else None,
                        "variant_id": v.get("variant_id"), "analysis_id": a["analysis_id"]})
    return out, n


def _in_range(ts: Optional[str], s: str, e: str) -> bool:
    d = (ts or "")[:10]
    return s <= d <= e


# ------------------------------------------------------------------ sections

def overview(registry, role: str, start: Optional[str], end: Optional[str]) -> dict:
    s, e = parse_range(start, end)
    def build():
        total = _one("SELECT COUNT(*) FROM patients WHERE substr(created_utc,1,10) BETWEEN ? AND ?", (s, e))
        wf = {r["status"]: r["n"] for r in _rows("SELECT w.status AS status, COUNT(*) AS n FROM case_workflow w JOIN patients p ON p.patient_id=w.case_id "
                                                 "WHERE substr(p.created_utc,1,10) BETWEEN ? AND ? GROUP BY w.status", (s, e))}
        no_wf = total - sum(wf.values())
        completed = wf.get("closed", 0)
        diag = _rows("SELECT COUNT(*) AS n, COUNT(DISTINCT patient_id) AS c FROM clinical_events WHERE kind='diagnosis' AND substr(created_utc,1,10) BETWEEN ? AND ?", (s, e))[0]
        vrecs, n_an = _variant_records(registry)
        vrecs = [v for v in vrecs if _in_range(v["ts"], s, e)]
        reviewed = _one("SELECT COUNT(DISTINCT case_id || '|' || variant_id) FROM case_evidence WHERE variant_id IS NOT NULL AND substr(added_utc,1,10) BETWEEN ? AND ?", (s, e))
        audit = lambda *acts: _one(f"SELECT COUNT(*) FROM audit_log WHERE action IN ({','.join('?' * len(acts))}) AND substr(ts,1,10) BETWEEN ? AND ?", (*acts, s, e))
        reports = _one("SELECT COUNT(*) FROM case_reports WHERE substr(created_utc,1,10) BETWEEN ? AND ?", (s, e))
        final = _one("SELECT COUNT(*) FROM case_reports WHERE status='final' AND substr(created_utc,1,10) BETWEEN ? AND ?", (s, e))
        return {
            "range": {"from": s, "to": e},
            "metrics": {
                "total_cases": total,
                "active_cases": total - completed,
                "completed_cases": completed,
                "variants_in_analyses": len(vrecs),
                "variants_reviewed": reviewed,
                "diagnosis_runs": diag["n"],
                "cases_with_diagnosis_run": diag["c"],
                "pgx_analyses": audit("pgx.case_view", "pgx.check"),
                "reproductive_analyses": audit("repro.analysis", "reproductive.couple_risk"),
                "reports_generated": reports,
                "reports_finalized": final,
                "pending_reviews": wf.get("in_review", 0),
            },
            "definitions": {
                "active_cases": "Cases whose workflow status is not 'closed' (cases without a workflow record count as 'new').",
                "completed_cases": "Cases whose workflow status is 'closed'.",
                "variants_reviewed": "Distinct case-variant pairs for which a clinician saved evidence.",
                "variants_in_analyses": "Variants in VCF analyses stored by the server (analyses are persisted in the variant_analyses table and survive restarts).",
                "pending_reviews": "Cases whose workflow status is 'in_review'.",
                "pgx_analyses / reproductive_analyses": "Counts of analyses run (audit log). PGx and reproductive results are computed on demand and are not stored per patient.",
            },
            "workflow_breakdown": {**wf, **({"new": wf.get("new", 0) + no_wf} if no_wf else {})},
        }
    return _section(cached(("overview", s, e), build), role)


def _bucket(ts: str, interval: str) -> str:
    d = date.fromisoformat(ts[:10])
    if interval == "month":
        return d.strftime("%Y-%m")
    if interval == "week":
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    return d.isoformat()


SERIES = {
    "cases": ("SELECT created_utc AS ts FROM patients", "Cases created"),
    "reports": ("SELECT created_utc AS ts FROM case_reports", "Reports generated"),
    "diagnoses": ("SELECT created_utc AS ts FROM clinical_events WHERE kind='diagnosis'", "Diagnosis runs"),
    "referrals": ("SELECT created_utc AS ts FROM referrals", "ASHA referrals"),
    "workflow_completions": ("SELECT utc AS ts FROM workflow_history WHERE action='status' AND to_value='closed'", "Cases closed"),
    "variant_reviews": ("SELECT added_utc AS ts FROM case_evidence WHERE variant_id IS NOT NULL", "Variant evidence saved"),
}


def timeseries(metric: str, interval: str, start: Optional[str], end: Optional[str], role: str) -> dict:
    if metric not in SERIES:
        raise AnalyticsError(f"Unknown metric '{metric}'. Choose one of: {', '.join(SERIES)}.")
    if interval not in ("day", "week", "month"):
        raise AnalyticsError("interval must be day, week or month.")
    s, e = parse_range(start, end)
    def build():
        sql, title = SERIES[metric]
        rows = _rows(sql)
        c = Counter(_bucket(r["ts"], interval) for r in rows if r["ts"] and s <= r["ts"][:10] <= e)
        pts = [{"bucket": k, "count": c[k]} for k in sorted(c)]
        suff = len(pts) >= MIN_SERIES_POINTS
        return {"metric": metric, "title": title, "interval": interval, "range": {"from": s, "to": e}, "points": pts, "total": sum(c.values()),
                "state": "ok" if suff else ("No data in range" if not pts else "Insufficient data for a trend"),
                "note": None if suff else f"A trend needs at least {MIN_SERIES_POINTS} time buckets; {len(pts)} found. Only observed buckets are shown."}
    return _section(cached(("ts", metric, interval, s, e), build), role)


def variants(registry, role: str, start: Optional[str], end: Optional[str]) -> dict:
    s, e = parse_range(start, end)
    def build():
        recs, n_an = _variant_records(registry)
        recs = [v for v in recs if _in_range(v["ts"], s, e)]
        reviewed_pairs = {(r["case_id"], r["variant_id"]) for r in _rows("SELECT case_id, variant_id FROM case_evidence WHERE variant_id IS NOT NULL")}
        reviewed = sum(1 for v in recs if v["variant_id"] in {p[1] for p in reviewed_pairs})
        return {"range": {"from": s, "to": e}, "analyses": n_an, "total_variants": len(recs),
                "acmg": dict(Counter(v["acmg"] or "Not classified" for v in recs)),
                "clinvar": dict(Counter(v["clinvar"] or "Not documented" for v in recs)),
                "genes": dict(Counter(v["gene"] or "Gene not documented" for v in recs)),
                "diseases": dict(Counter(v["disease"] for v in recs if v["disease"])),
                "reviewed": reviewed, "unreviewed": len(recs) - reviewed}
    raw = cached(("variants", s, e), build)
    out = {k: v for k, v in raw.items() if k not in ("acmg", "clinvar", "genes", "diseases")}
    for k in ("acmg", "clinvar", "genes", "diseases"):
        rows, hidden = suppress(raw[k], role)
        out[k] = rows[:15] if k in ("genes", "diseases") else rows
        out[f"{k}_suppressed"] = hidden
    out["state"] = "ok" if raw["total_variants"] else "No variant analyses in range"
    return _section(out, role, "Reviewed = a clinician saved evidence for that variant. ACMG classes are computed by the rule engine, not clinically validated.")


def _hpo_ids(payload: dict) -> List[str]:
    out = []
    for h in payload.get("hpo_profile", []) or []:
        if isinstance(h, str):
            out.append(h)
        elif isinstance(h, dict) and (h.get("hpo_id") or h.get("id")):
            out.append(h.get("hpo_id") or h.get("id"))
    return out


def phenotypes(registry, role: str, start: Optional[str], end: Optional[str]) -> dict:
    s, e = parse_range(start, end)
    def build():
        n_cases = _one("SELECT COUNT(*) FROM patients WHERE substr(created_utc,1,10) BETWEEN ? AND ?", (s, e))
        per_case: Dict[str, set] = {}
        names: Dict[str, str] = {}
        for ev in _rows("SELECT patient_id, payload FROM clinical_events WHERE kind='hpo_profile' AND substr(created_utc,1,10) BETWEEN ? AND ?", (s, e)):
            pl = json.loads(ev["payload"] or "{}")
            per_case.setdefault(ev["patient_id"], set()).update(_hpo_ids(pl))
            for it in pl.get("hpo_profile", []) or []:
                if isinstance(it, dict) and it.get("hpo_id") and it.get("name"):
                    names[it["hpo_id"]] = it["name"]
        freq = Counter(h for ids in per_case.values() for h in ids)
        names = {h: names.get(h, h) for h in freq}
        with_hpo = sum(1 for ids in per_case.values() if ids)
        co = None
        if len(per_case) >= MIN_CASES_FOR_COOCCURRENCE:
            pair = Counter()
            for ids in per_case.values():
                s_ids = sorted(ids)
                for i in range(len(s_ids)):
                    for j in range(i + 1, len(s_ids)):
                        pair[(s_ids[i], s_ids[j])] += 1
            co = [{"a": a, "b": b, "cases": n} for (a, b), n in pair.most_common(10) if n >= 2]
        return {"range": {"from": s, "to": e}, "cases": n_cases, "cases_with_phenotypes": with_hpo,
                "coverage_pct": round(100 * with_hpo / n_cases, 1) if n_cases else None,
                "mean_terms_per_phenotyped_case": round(sum(len(v) for v in per_case.values()) / with_hpo, 2) if with_hpo else None,
                "frequencies": {f"{names[h]} ({h})": n for h, n in freq.items()}, "cooccurrence": co,
                "cooccurrence_state": "ok" if co is not None else f"Insufficient data: needs at least {MIN_CASES_FOR_COOCCURRENCE} phenotyped cases ({len(per_case)} found)"}
    raw = cached(("pheno", s, e), build)
    out = {k: v for k, v in raw.items() if k != "frequencies"}
    rows, hidden = suppress(raw["frequencies"], role)
    out["frequencies"], out["frequencies_suppressed"] = rows[:20], hidden
    if role == "researcher":
        out["cooccurrence"] = None
        out["cooccurrence_state"] = "Not available for this role (re-identification risk)."
    out["state"] = "ok" if raw["cases_with_phenotypes"] else "No phenotyped cases in range"
    return _section(out, role, "Phenotype clusters and phenotype-disease relationships are not computed: they need far more cases than a single-site deployment holds, and small samples would be misleading.")


def diagnoses(role: str, start: Optional[str], end: Optional[str]) -> dict:
    s, e = parse_range(start, end)
    def build():
        latest: Dict[str, dict] = {}
        for ev in _rows("SELECT patient_id, payload, created_utc FROM clinical_events WHERE kind='diagnosis' AND substr(created_utc,1,10) BETWEEN ? AND ? ORDER BY created_utc", (s, e)):
            latest[ev["patient_id"]] = json.loads(ev["payload"] or "{}")
        top, probs, inh = Counter(), [], Counter()
        for p in latest.values():
            r = (p.get("results") or [None])[0]
            if r:
                top[r.get("disease_name") or r.get("disease_id") or "Not documented"] += 1
                inh[r.get("inheritance") or "Not documented"] += 1
                if isinstance(r.get("probability"), (int, float)):
                    probs.append(r["probability"])
        cases = [r["patient_id"] for r in _rows("SELECT patient_id FROM patients WHERE substr(created_utc,1,10) BETWEEN ? AND ?", (s, e))]
        finals = {r["case_id"] for r in _rows("SELECT DISTINCT case_id FROM case_reports WHERE status='final'")}
        no_run = sum(1 for c in cases if c not in latest)
        return {"range": {"from": s, "to": e}, "cases_with_diagnosis_run": len(latest), "top_diagnosis": dict(top), "inheritance": dict(inh),
                "model_score": {"mean_top1": round(sum(probs) / len(probs), 3) if probs else None, "n": len(probs), "label": "Model score (not a clinical diagnosis)"},
                "unresolved": {"no_diagnosis_run": no_run, "diagnosed_no_final_report": sum(1 for c in cases if c in latest and c not in finals), "with_final_report": sum(1 for c in cases if c in finals)}}
    raw = cached(("dx", s, e), build)
    out = {k: v for k, v in raw.items() if k not in ("top_diagnosis", "inheritance")}
    for k in ("top_diagnosis", "inheritance"):
        rows, hidden = suppress(raw[k], role)
        out[k], out[f"{k}_suppressed"] = rows[:15], hidden
    out["state"] = "ok" if raw["cases_with_diagnosis_run"] else "No diagnosis runs in range"
    return _section(out, role, MODEL_SCORE_NOTE + " Uses each case's most recent diagnosis run.")


def pgx(registry, role: str, start: Optional[str], end: Optional[str]) -> dict:
    s, e = parse_range(start, end)
    def build():
        recs, _ = _variant_records(registry)
        recs = [v for v in recs if _in_range(v["ts"], s, e) and v["pgx_gene"]]
        runs = _rows("SELECT action, COUNT(*) AS n FROM audit_log WHERE action IN ('pgx.case_view','pgx.check') AND substr(ts,1,10) BETWEEN ? AND ? GROUP BY action", (s, e))
        drugs = Counter()
        for r in _rows("SELECT detail FROM audit_log WHERE action='pgx.check' AND substr(ts,1,10) BETWEEN ? AND ?", (s, e)):
            for d in (r["detail"] or "").replace("drugs=", "").split(","):
                if d.strip():
                    drugs[d.strip().lower()] += 1
        return {"range": {"from": s, "to": e}, "analyses_run": {r["action"]: r["n"] for r in runs}, "pgx_relevant_variants": len(recs),
                "genes": dict(Counter(v["pgx_gene"] for v in recs)), "medications_screened": dict(drugs)}
    raw = cached(("pgx", s, e), build)
    out = {k: v for k, v in raw.items() if k not in ("genes", "medications_screened")}
    for k in ("genes", "medications_screened"):
        rows, hidden = suppress(raw[k], role)
        out[k], out[f"{k}_suppressed"] = rows[:15], hidden
    out["state"] = "ok" if (raw["pgx_relevant_variants"] or raw["analyses_run"]) else "No PGx activity in range"
    return _section(out, role, "Phenotype categories (metabolizer status) and per-patient findings are computed on demand and not stored, so they cannot be aggregated.")


def reproductive(role: str, start: Optional[str], end: Optional[str]) -> dict:
    s, e = parse_range(start, end)
    def build():
        bands = Counter()
        n = 0
        for r in _rows("SELECT action, detail FROM audit_log WHERE action IN ('repro.analysis','reproductive.couple_risk') AND substr(ts,1,10) BETWEEN ? AND ?", (s, e)):
            n += 1
            if r["action"] == "repro.analysis" and (r["detail"] or "").startswith("band="):
                bands[r["detail"][5:]] += 1
        return {"range": {"from": s, "to": e}, "analyses_run": n, "risk_bands": dict(bands)}
    raw = cached(("repro", s, e), build)
    rows, hidden = suppress(raw["risk_bands"], role)
    return _section({"range": raw["range"], "analyses_run": raw["analyses_run"], "risk_bands": rows, "risk_bands_suppressed": hidden,
                     "state": "ok" if raw["analyses_run"] else "No reproductive analyses in range"}, role,
                    "Only counts and risk bands are aggregated. Couples, genotypes and carrier status are never included. Inheritance patterns and scenario types are not stored per analysis.")


def to_csv(rows: List[dict], columns: List[str]) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rows:
        w.writerow([("'" + str(r.get(c)) if str(r.get(c) or "").startswith(("=", "+", "-", "@")) else r.get(c, "")) for c in columns])   # neutralise CSV formula injection
    return buf.getvalue()
