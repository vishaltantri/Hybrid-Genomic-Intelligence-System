"""Authentication + RBAC for GENOMIND-INDIA.

Roles match the five user types in the project brief: doctor, patient, asha, admin, researcher.
Password hashing uses bcrypt directly (no passlib indirection); tokens are HS256 JWTs.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from backend.app import store
from ml_services.config import ACCESS_TOKEN_MINUTES, JWT_ALGORITHM, JWT_SECRET, ROLES

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

ROLE_PERMISSIONS: Dict[str, List[str]] = {
    # doctor reads the KG (disease detail, stats) to explain diagnoses at the point of care
    "doctor": ["clinical:read", "clinical:write", "diagnosis:run", "xai:read", "pgx:read",
               "reproductive:read", "reproductive:counsel", "feedback:write",
               "kg:read", "dashboard:read", "variants:read", "variants:write",
               "assistant:chat", "twin:read", "twin:write", "pedigree:read", "pedigree:write", "evidence:read", "evidence:write",
               "referral:read", "referral:handoff", "workflow:read", "workflow:write", "search:read", "triage:read", "triage:write", "analytics:read"],
    "patient": ["clinical:read:own", "diagnosis:read:own", "reproductive:read:own",
                "pgx:read:own", "assistant:chat", "search:read"],
    "asha": ["triage:write", "triage:read", "clinical:write:limited", "sync:write", "referral:write", "referral:read", "workflow:read", "search:read"],
    "admin": ["*"],
    "researcher": ["dashboard:read", "federated:read", "kg:read", "kg:propose",
                   "variants:read", "variants:write", "assistant:chat", "evidence:read", "search:read", "analytics:read"],
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, role: str, extra: Optional[dict] = None) -> str:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; expected one of {ROLES}")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub", "role"]})
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc


async def current_user(token: Optional[str] = Depends(oauth2_scheme)) -> dict:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    payload = decode_token(token)
    # The database is authoritative: a deleted account or a changed role takes effect on the next request.
    record = store.get_user(str(payload["sub"]))
    if not record or record["role"] not in ROLES:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="account no longer exists")
    return {"username": record["username"], "role": record["role"], "claims": payload}


def require(permission: str):
    """Dependency factory: require a permission for the route."""

    async def _checker(user: dict = Depends(current_user)) -> dict:
        perms = ROLE_PERMISSIONS.get(user["role"], [])
        if "*" in perms or permission in perms:
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"role {user['role']!r} lacks permission {permission!r}")

    return _checker
