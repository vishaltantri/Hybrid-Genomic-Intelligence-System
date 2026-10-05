"""Phase 11: versioned case reports with real backend PDF export."""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.app import store
from backend.app.hardening import rate_limit
from backend.app.security import require
from backend.app.services import registry
from ml_services.reports.service import SECTION_IDS, ReportError

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _run(fn, *a):
    try:
        return fn(*a)
    except ReportError as ex:
        raise HTTPException(status_code=ex.status, detail=str(ex))
    except LookupError as ex:
        raise HTTPException(status_code=404, detail=str(ex))


class GenerateIn(BaseModel):
    sections: Optional[List[str]] = None


@router.get("/sections")
def sections(user: dict = Depends(require("clinical:read"))):
    return {"sections": list(SECTION_IDS)}


@router.post("/case/{pid}")
def generate(pid: str, body: GenerateIn, user: dict = Depends(require("clinical:write")), _rl: None = Depends(rate_limit("report"))):
    r = _run(registry.reports.generate, pid, user["username"], body.sections)
    store.audit(user["username"], "report.generate", pid, f"{r['report_id']} v{r['version']}")
    return r


@router.get("/case/{pid}")
def versions(pid: str, user: dict = Depends(require("clinical:read"))):
    return store.report_list(pid)


@router.get("/{report_id}")
def get(report_id: str, user: dict = Depends(require("clinical:read"))):
    return _run(registry.reports.get, report_id)


@router.post("/{report_id}/refresh")
def refresh(report_id: str, user: dict = Depends(require("clinical:write"))):
    r = _run(registry.reports.refresh, report_id, user["username"])
    store.audit(user["username"], "report.refresh", r["case_id"], report_id)
    return r


@router.post("/{report_id}/finalize")
def finalize(report_id: str, user: dict = Depends(require("clinical:write"))):
    r = _run(registry.reports.finalize, report_id, user["username"])
    store.audit(user["username"], "report.finalize", r["case_id"], f"{report_id} v{r['version']}")
    wf = store.workflow_get(r["case_id"])
    if wf["assignee"] and wf["assignee"] != user["username"]:
        store.notify("report_final", f"Report {report_id} finalized for case {r['case_id']}", f"Version {r['version']}", r["case_id"],
                     recipient=wf["assignee"], created_by=user["username"])
    return r


@router.get("/{report_id}/pdf")
def pdf(report_id: str, user: dict = Depends(require("clinical:read")), _rl: None = Depends(rate_limit("report"))):
    data = _run(registry.reports.pdf, report_id)
    store.audit(user["username"], "report.pdf", report_id, f"{len(data)} bytes")
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{report_id}.pdf"'})


@router.get("/{report_id}/json")
def export_json(report_id: str, user: dict = Depends(require("clinical:read")), _rl: None = Depends(rate_limit("report"))):
    r = _run(registry.reports.get, report_id)
    store.audit(user["username"], "report.json", report_id, "")
    return Response(content=json.dumps(r, ensure_ascii=False, indent=1), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{report_id}.json"'})
