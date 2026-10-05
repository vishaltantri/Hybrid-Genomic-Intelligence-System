"""Phase 16 analytics API. Aggregates only; no patient identifiers. Needs `analytics:read` (doctor, researcher, admin).

  GET /api/v1/analytics/overview?from=&to=
  GET /api/v1/analytics/timeseries?metric=&interval=&from=&to=
  GET /api/v1/analytics/{variants|phenotypes|diagnoses|pgx|reproductive}?from=&to=
  GET /api/v1/analytics/export?section=&format=csv|json&from=&to=
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from backend.app import analytics as an
from backend.app import store
from backend.app.hardening import rate_limit
from backend.app.security import require
from backend.app.services import registry

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])
Auth = Depends(require("analytics:read"))
DATE = dict(default=None, max_length=10, alias=None)


def _guard(fn, *a):
    try:
        return fn(*a)
    except an.AnalyticsError as ex:
        raise HTTPException(status_code=422, detail=str(ex))


@router.get("/overview")
def overview(from_: Optional[str] = Query(None, alias="from", max_length=10), to: Optional[str] = Query(None, max_length=10), user: dict = Auth):
    return _guard(an.overview, registry, user["role"], from_, to)


@router.get("/timeseries")
def timeseries(metric: str = Query("cases", max_length=30), interval: str = Query("day", max_length=8),
               from_: Optional[str] = Query(None, alias="from", max_length=10), to: Optional[str] = Query(None, max_length=10), user: dict = Auth):
    return _guard(an.timeseries, metric, interval, from_, to, user["role"])


@router.get("/variants")
def variants(from_: Optional[str] = Query(None, alias="from", max_length=10), to: Optional[str] = Query(None, max_length=10), user: dict = Auth):
    return _guard(an.variants, registry, user["role"], from_, to)


@router.get("/phenotypes")
def phenotypes(from_: Optional[str] = Query(None, alias="from", max_length=10), to: Optional[str] = Query(None, max_length=10), user: dict = Auth):
    return _guard(an.phenotypes, registry, user["role"], from_, to)


@router.get("/diagnoses")
def diagnoses(from_: Optional[str] = Query(None, alias="from", max_length=10), to: Optional[str] = Query(None, max_length=10), user: dict = Auth):
    return _guard(an.diagnoses, user["role"], from_, to)


@router.get("/pgx")
def pgx(from_: Optional[str] = Query(None, alias="from", max_length=10), to: Optional[str] = Query(None, max_length=10), user: dict = Auth):
    return _guard(an.pgx, registry, user["role"], from_, to)


@router.get("/reproductive")
def reproductive(from_: Optional[str] = Query(None, alias="from", max_length=10), to: Optional[str] = Query(None, max_length=10), user: dict = Auth):
    return _guard(an.reproductive, user["role"], from_, to)


SECTIONS = ("overview", "variants", "phenotypes", "diagnoses", "pgx", "reproductive")


def _flatten(section: str, data: dict) -> list:
    """Chart-shaped rows (section, series, label, count) for CSV."""
    rows = []
    if section == "overview":
        rows += [{"series": "metric", "label": k, "count": v} for k, v in data["metrics"].items()]
        rows += [{"series": "workflow", "label": k, "count": v} for k, v in data["workflow_breakdown"].items()]
        return rows
    for key, val in data.items():
        if isinstance(val, list) and val and isinstance(val[0], dict) and "count" in val[0]:
            rows += [{"series": key, "label": r["label"], "count": r["count"]} for r in val]
        elif key in ("analyses_run", "unresolved") and isinstance(val, dict):
            rows += [{"series": key, "label": k, "count": v} for k, v in val.items()]
        elif key in ("total_variants", "reviewed", "unreviewed", "cases", "cases_with_phenotypes", "cases_with_diagnosis_run", "pgx_relevant_variants"):
            rows.append({"series": "total", "label": key, "count": val})
    return rows


@router.get("/export")
def export(section: str = Query(..., max_length=20), format: str = Query("json", pattern="^(csv|json)$"),
           from_: Optional[str] = Query(None, alias="from", max_length=10), to: Optional[str] = Query(None, max_length=10), user: dict = Auth, _rl: None = Depends(rate_limit("export"))):
    if section not in SECTIONS and not section.startswith("timeseries:"):
        raise HTTPException(status_code=422, detail=f"Unknown section. Choose one of: {', '.join(SECTIONS)} or timeseries:<metric>.")
    role = user["role"]
    if section.startswith("timeseries:"):
        data = _guard(an.timeseries, section.split(":", 1)[1], "day", from_, to, role)
        rows = [{"series": data["metric"], "label": p["bucket"], "count": p["count"]} for p in data["points"]]
    else:
        fn = {"overview": lambda: an.overview(registry, role, from_, to), "variants": lambda: an.variants(registry, role, from_, to),
              "phenotypes": lambda: an.phenotypes(registry, role, from_, to), "diagnoses": lambda: an.diagnoses(role, from_, to),
              "pgx": lambda: an.pgx(registry, role, from_, to), "reproductive": lambda: an.reproductive(role, from_, to)}[section]
        data = _guard(fn)
        rows = _flatten(section, data)
    store.audit(user["username"], "analytics.export", section, f"format={format} rows={len(rows)}")
    name = section.replace(":", "_")
    if format == "csv":
        return Response(an.to_csv(rows, ["series", "label", "count"]), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="genomera_{name}.csv"'})
    return Response(json.dumps({"section": section, "data": data}, default=str), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="genomera_{name}.json"'})
