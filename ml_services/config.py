"""GENOMIND-INDIA shared configuration and path helpers."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
SEEDS_DIR = DATA_DIR / "seeds"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = REPO_ROOT / "models"
REPORTS_DIR = REPO_ROOT / "reports"

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "genomind_dev_password")
GENOMIND_DETERMINISTIC = os.environ.get("GENOMIND_DETERMINISTIC", "1") == "1"

for _d in (SEEDS_DIR, RAW_DIR, PROCESSED_DIR, MODELS_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# 32+ byte default keeps HMAC-SHA256 happy in dev; ALWAYS override in deployments
# (docker-compose and .env.example both set GENOMIND_JWT_SECRET explicitly).
JWT_SECRET = os.environ.get("GENOMIND_JWT_SECRET", "genomind-dev-only-secret-change-me-32b+")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.environ.get("GENOMIND_ACCESS_TOKEN_MINUTES", "120"))

ROLES = ("doctor", "patient", "asha", "admin", "researcher")
