"""GENOMIND-INDIA API.

Run:
    .venv/bin/uvicorn backend.app.main:app --reload --port 8000
Docs: http://localhost:8000/docs

Bootstrapping: on first start the app creates dev users when the users table is empty
(admin / admin-password-change-me, clinician / changeme, asha1 / changeme) — change
them immediately in any real deployment.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app import store
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
    reproductive,
    triage,
)
from backend.app.security import hash_password
from backend.app.services import registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("genomind.api")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_bootstrap()
    logger.info("GENOMIND-INDIA API ready: %s graph nodes", registry.status()["graph_nodes"])
    yield


app = FastAPI(
    title="GENOMIND-INDIA API",
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "AI platform for rare genetic disease diagnosis, pharmacogenomics and reproductive "
        "risk, built for Indian populations. Prototype: outputs are decision support only and "
        "require clinician confirmation."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, clinical.router, diagnosis.router, pharmacogenomics.router,
          reproductive.router, triage.router, dashboard.router, learning.router,
          federated.router, emr.router):
    app.include_router(r)


def ensure_bootstrap() -> None:
    """Create the default admin when the user table is empty.

    Called at import time *and* from the startup hook: `TestClient(app)` without a context
    manager does not fire startup events, and an API with no users is unusable.
    """
    if not store.list_users():
        store.create_user("admin", "admin", hash_password("admin-password-change-me"),
                          "Bootstrap Administrator")
        store.create_user("clinician", "doctor", hash_password("changeme"), "Demo Clinician")
        store.create_user("asha1", "asha", hash_password("changeme"), "Demo ASHA Worker")
        logger.warning("Created default dev users (admin / clinician / asha1) — change passwords in any real deployment.")


# Bootstrap at import time as well: `TestClient(app)` without a context manager does not
# run the lifespan handler, and an API with no users is unusable.
ensure_bootstrap()


@app.get("/health", response_model=HealthOut)
def health():
    status = registry.status()
    return HealthOut(status="ok", graph_nodes=status["graph_nodes"], graph_edges=status["graph_edges"],
                     modules=status["modules"])


@app.get("/api/v1/platform/status")
def platform_status():
    """Which modules are running on trained checkpoints vs deterministic fallbacks."""
    return registry.status()
