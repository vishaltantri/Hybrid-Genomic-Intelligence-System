"""GENOMERA API.

Run:
    .venv/bin/uvicorn backend.app.main:app --reload --port 8000
Docs: http://localhost:8000/docs

Bootstrapping: on first start the app creates dev users when the users table is empty
(admin / admin-password-change-me, clinician / changeme, asha1 / changeme) — change
them immediately in any real deployment.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.app import hardening, migrations, observability, store
from backend.app.models import HealthOut
from backend.app.routers import (
    auth,
    clinical,
    dashboard,
    diagnosis,
    emr,
    federated,
    learning,
    pharmacogenomics,
    repro_workspace,
    community,
    workflow,
    search,
    analytics as analytics_router,
    ml_registry as ml_registry_router,
    demo as demo_router,
    quality as quality_router,
    reports,
    reproductive,
    triage,
    variants,
    assistant,
    digital_twin,
    pedigree,
    evidence,
    kg_explorer,
    phenotype,
    diagnosis_intel,
    nlp,
)
from backend.app.security import current_user, hash_password, require
from backend.app.services import registry

observability.configure_logging()
logger = logging.getLogger("genomind.api")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_bootstrap()
    logger.info("GENOMERA API ready: %s graph nodes", registry.status()["graph_nodes"])
    yield


_HIDE_DOCS = hardening.is_production() and os.environ.get("GENOMERA_ENABLE_DOCS") != "1"

app = FastAPI(
    title="GENOMERA API",
    version="0.1.0",
    lifespan=lifespan,
    # Interactive API docs expose the full route and schema inventory: off in production unless explicitly enabled.
    docs_url=None if _HIDE_DOCS else "/docs",
    redoc_url=None if _HIDE_DOCS else "/redoc",
    openapi_url=None if _HIDE_DOCS else "/openapi.json",
    description=(
        "AI platform for rare genetic disease diagnosis, pharmacogenomics and reproductive "
        "risk, built for Indian populations. Prototype: outputs are decision support only and "
        "require clinician confirmation."
    ),
)

for _w in hardening.check_startup():
    logger.warning("SECURITY: %s", _w)

app.add_middleware(
    CORSMiddleware,
    allow_origins=hardening.cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=["X-Total-Count", "X-Request-ID"],
)
app.add_middleware(hardening.SecurityMiddleware)   # wraps CORS: headers and size limit apply to every response
app.add_middleware(observability.RequestObservabilityMiddleware)   # outermost: request id, access log, metrics, safe 500s

for r in (quality_router.router, demo_router.router, analytics_router.router, ml_registry_router.router, search.router,workflow.router, community.router, repro_workspace.router, reports.router, auth.router, clinical.router, diagnosis.router, pharmacogenomics.router,
          reproductive.router, triage.router, dashboard.router, learning.router,
          federated.router, emr.router, variants.router, assistant.router, digital_twin.router, pedigree.router, evidence.router, nlp.router, kg_explorer.router, phenotype.router, diagnosis_intel.router):
    app.include_router(r)


def ensure_bootstrap() -> None:
    """Create the default admin when the user table is empty.

    Called at import time *and* from the startup hook: `TestClient(app)` without a context
    manager does not fire startup events, and an API with no users is unusable.
    """
    if not store.list_users() and hardening.is_production():
        pw = os.environ.get("GENOMERA_BOOTSTRAP_ADMIN_PASSWORD", "")
        if len(pw) >= 12:
            store.create_user("admin", "admin", hash_password(pw), "Administrator")
            logger.warning("Created the first admin from GENOMERA_BOOTSTRAP_ADMIN_PASSWORD.")
        else:
            logger.error("Production start with no users: set GENOMERA_BOOTSTRAP_ADMIN_PASSWORD (12+ chars) to create the first admin.")
        return
    if not store.list_users():
        store.create_user("admin", "admin", hash_password("admin-password-change-me"),
                          "Administrator")
        store.create_user("clinician", "doctor", hash_password("changeme"), "Clinician")
        store.create_user("asha1", "asha", hash_password("changeme"), "ASHA Worker")
        logger.warning("Created default dev users (admin / clinician / asha1) — change passwords in any real deployment.")


# Bootstrap at import time as well: `TestClient(app)` without a context manager does not
# run the lifespan handler, and an API with no users is unusable.
ensure_bootstrap()


@app.get("/health", response_model=HealthOut, tags=["platform"])
def health():
    status = registry.status()
    return HealthOut(status="ok", graph_nodes=status["graph_nodes"], graph_edges=status["graph_edges"],
                     modules=status["modules"])


@app.get("/readiness", tags=["platform"])
def readiness():
    """Ready only when the database answers, migrations are applied and the knowledge graph is loaded (503 otherwise)."""
    ok, body = observability.readiness(registry, store, migrations)
    return JSONResponse(body, status_code=200 if ok else 503)


@app.get("/metrics", tags=["platform"], response_class=PlainTextResponse)
def prometheus_metrics(user: dict = Depends(require("ops:read"))):
    """Prometheus text format. Admin token required; values are measured at runtime, per process."""
    extra = {}
    try:
        with store._connect() as conn:
            t = time.perf_counter()
            conn.execute("SELECT 1").fetchone()
            extra["genomera_database_up"] = 1
            extra["genomera_database_ping_seconds"] = round(time.perf_counter() - t, 6)
    except Exception:  # noqa: BLE001
        extra["genomera_database_up"] = 0
    for k, v in observability.system_resources().items():
        if isinstance(v, (int, float)):
            extra[f"genomera_{k}" if k.startswith("process_") else f"genomera_process_{k}"] = v
    return observability.metrics.prometheus(extra)


@app.get("/api/v1/ops/status", tags=["platform"])
def ops_status(user: dict = Depends(require("ops:read"))):
    """Administrator view of runtime health: request/error counters, resources and security posture."""
    ok, ready = observability.readiness(registry, store, migrations)
    return {"ready": ready, "metrics": observability.metrics.snapshot(), "resources": observability.system_resources(),
            "security": hardening.posture(), "log_format": observability.LOG_FORMAT,
            "limitations": ["Metrics are per process and reset on restart.", "There is no background job system, so no job metrics exist."]}


@app.get("/api/v1/platform/status", tags=["platform"])
def platform_status(user: dict = Depends(current_user)):
    """Which modules are running on trained checkpoints vs deterministic fallbacks. Requires sign-in."""
    return registry.status()
