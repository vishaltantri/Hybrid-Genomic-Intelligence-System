"""Phase 14: case workflow (status, assignment, history) and persisted notifications."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app import store
from backend.app.security import require

router = APIRouter(prefix="/api/v1/workflow", tags=["workflow"])

STATUSES = ("new", "in_review", "awaiting_results", "report_ready", "closed")
TRANSITIONS = {
    "new": {"in_review", "closed"},
    "in_review": {"awaiting_results", "report_ready", "closed"},
    "awaiting_results": {"in_review", "report_ready", "closed"},
    "report_ready": {"in_review", "closed"},
    "closed": {"in_review"},
}
CLINICIAN_ROLES = ("doctor", "admin")


def _case(pid: str) -> dict:
    p = store.get_patient(pid)
    if not p:
        raise HTTPException(status_code=404, detail=f"Case '{pid}' not found")
    return p


# ----------------------------------------------------------------- notifications

@router.get("/notifications")
def notifications(unread: bool = False, user: dict = Depends(require("workflow:read"))):
    return store.notification_list(user["username"], user["role"], unread)


@router.get("/notifications/count")
def unread_count(user: dict = Depends(require("workflow:read"))):
    return {"unread": len(store.notification_list(user["username"], user["role"], True, 10000))}


@router.post("/notifications/read-all")
def read_all(user: dict = Depends(require("workflow:read"))):
    return {"marked": store.notification_mark_all(user["username"], user["role"])}


@router.post("/notifications/{nid}/read")
def read_one(nid: str, user: dict = Depends(require("workflow:read"))):
    if not store.notification_mark_read(nid, user["username"], user["role"]):
        raise HTTPException(status_code=404, detail="Notification not found")    # foreign ids are indistinguishable from missing
    return {"id": nid, "read": True}


# ----------------------------------------------------------------- case workflow

@router.get("/queue")
def queue(mine: bool = False, status: Optional[str] = None, user: dict = Depends(require("clinical:read"))):
    if status and status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"Status must be one of {list(STATUSES)}.")
    return store.workflow_queue(user["username"] if mine else None, status)


@router.get("/case/{pid}")
def get_workflow(pid: str, user: dict = Depends(require("clinical:read"))):
    _case(pid)
    w = store.workflow_get(pid)
    return {**w, "allowed_next": sorted(TRANSITIONS[w["status"]])}


class StatusIn(BaseModel):
    status: str
    note: str = Field(default="", max_length=500)


@router.post("/case/{pid}/status")
def set_status(pid: str, p: StatusIn, user: dict = Depends(require("workflow:write"))):
    _case(pid)
    cur = store.workflow_get(pid)
    if p.status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"Status must be one of {list(STATUSES)}.")
    if p.status == cur["status"] or p.status not in TRANSITIONS[cur["status"]]:
        raise HTTPException(status_code=409, detail=f"Cannot move a case from '{cur['status']}' to '{p.status}'.")
    out = store.workflow_set(pid, user["username"], status=p.status, note=p.note.strip())
    if cur["assignee"] and cur["assignee"] != user["username"]:
        store.notify("status_change", f"Case {pid} moved to {p.status}", p.note.strip(), pid, recipient=cur["assignee"], created_by=user["username"])
    store.audit(user["username"], "workflow.status", pid, f"{cur['status']} -> {p.status}")
    return out


class AssignIn(BaseModel):
    assignee: str
    note: str = Field(default="", max_length=500)


@router.post("/case/{pid}/assign")
def assign(pid: str, p: AssignIn, user: dict = Depends(require("workflow:write"))):
    _case(pid)
    target = store.get_user(p.assignee)
    if not target or target["role"] not in CLINICIAN_ROLES:
        raise HTTPException(status_code=422, detail="Assignee must be an existing clinician account.")
    out = store.workflow_set(pid, user["username"], assignee=p.assignee, note=p.note.strip())
    if p.assignee != user["username"]:
        store.notify("assignment", f"Case {pid} assigned to you", p.note.strip(), pid, recipient=p.assignee, created_by=user["username"])
    store.audit(user["username"], "workflow.assign", pid, p.assignee)
    return out
