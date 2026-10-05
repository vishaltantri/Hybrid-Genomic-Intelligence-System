"""Phase 17 security hardening: rate limiting, login throttling, security headers, request-size limits and a
truthful security posture report. Everything here is enforced at runtime; nothing is a placeholder.

Environment:
  GENOMERA_ENV                 development (default) | production. Production refuses a default/short JWT secret and
                               does not seed demo users.
  GENOMERA_CORS_ORIGINS        comma separated allowed origins (default: local Vite/dev origins)
  GENOMERA_MAX_BODY_MB         max request body for non-upload routes (default 2) / upload routes (default 25)
  GENOMERA_BOOTSTRAP_ADMIN_PASSWORD   production only: creates the first admin (min 12 chars)
Limits are in-process (single worker). A multi-worker deployment needs a shared store such as Redis (see PLAN.md).
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, List, Tuple

from fastapi import Depends, HTTPException, Request

from ml_services.config import JWT_SECRET

ENV = os.environ.get("GENOMERA_ENV", "development").lower()
DEFAULT_SECRETS = {"genomind-dev-only-secret-change-me-32b+", "change-me-in-production"}
DEFAULT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]
DEFAULT_PASSWORDS = {"admin": "admin-password-change-me", "clinician": "changeme", "asha1": "changeme"}
MAX_BODY = int(float(os.environ.get("GENOMERA_MAX_BODY_MB", "2")) * 1024 * 1024)
MAX_UPLOAD = 25 * 1024 * 1024
UPLOAD_PATHS = ("/api/v1/variants/upload",)


def is_production() -> bool:
    return os.environ.get("GENOMERA_ENV", "development").lower() == "production"


def cors_origins() -> List[str]:
    raw = os.environ.get("GENOMERA_CORS_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in origins:
        raise RuntimeError("GENOMERA_CORS_ORIGINS must not contain '*' when credentials are allowed")
    return origins or ([] if is_production() else DEFAULT_ORIGINS)


# ------------------------------------------------------------------ rate limiting

class RateLimiter:
    """Sliding-window limiter. `hit` returns the seconds to wait (0 if allowed)."""

    def __init__(self) -> None:
        self._hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, bucket: str, key: str, limit: int, window: float, record: bool = True) -> int:
        now = time.monotonic()
        with self._lock:
            q = self._hits[(bucket, key)]
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return max(1, int(window - (now - q[0])) + 1)
            if record:
                q.append(now)
            return 0

    def record(self, bucket: str, key: str) -> None:
        with self._lock:
            self._hits[(bucket, key)].append(time.monotonic())

    def clear(self, bucket: str, key: str) -> None:
        with self._lock:
            self._hits.pop((bucket, key), None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()

# bucket -> (limit, window seconds). Generous enough for a clinician, tight enough to stop scripted abuse.
LIMITS: Dict[str, Tuple[int, int]] = {
    "ai": (30, 60), "upload": (20, 60), "search": (120, 60), "report": (60, 60), "export": (20, 60),
}


def rate_limit(bucket: str) -> Callable:
    """Dependency factory: per-user sliding-window limit, 429 + Retry-After when exceeded."""
    from backend.app.security import current_user   # local import: security imports nothing from here

    limit, window = LIMITS[bucket]

    async def _dep(user: dict = Depends(current_user)) -> None:
        wait = limiter.check(bucket, user["username"], limit, window)
        if wait:
            raise HTTPException(status_code=429, detail=f"Rate limit exceeded for {bucket}; retry in {wait}s",
                                headers={"Retry-After": str(wait)})
    return _dep


LOGIN_FAILS, LOGIN_WINDOW = 5, 300


def login_gate(request: Request, username: str) -> str:
    """Raise 429 when this (client, username) has too many recent failures. Returns the throttle key."""
    key = f"{request.client.host if request.client else 'unknown'}|{username.lower()[:64]}"
    wait = limiter.check("login", key, LOGIN_FAILS, LOGIN_WINDOW, record=False)
    if wait:
        raise HTTPException(status_code=429, detail="Too many failed sign-in attempts; try again later",
                            headers={"Retry-After": str(wait)})
    return key


# ------------------------------------------------------------------ object-level access

def has_perm(user: dict, perm: str) -> bool:
    from backend.app.security import ROLE_PERMISSIONS
    perms = ROLE_PERMISSIONS.get(user["role"], [])
    return "*" in perms or perm in perms


def analysis_visible(user: dict, analysis: dict) -> bool:
    """A VCF analysis is visible to its uploader, to admins, and (because case access is clinician-wide) to users with
    clinical:read when it is attached to an existing case. Everyone else, including researchers, sees only their own."""
    from backend.app import store
    if user["role"] == "admin" or analysis.get("created_by") == user["username"]:
        return True
    pid = analysis.get("patient_id")
    return bool(pid and has_perm(user, "clinical:read") and store.get_patient(pid))


# ------------------------------------------------------------------ ASGI middleware

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
]
DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityMiddleware:
    """Adds security headers to every response and rejects oversized bodies before they are read."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        headers = dict(scope["headers"])
        try:
            length = int(headers.get(b"content-length", b"0") or 0)
        except ValueError:
            length = -1
        cap = MAX_UPLOAD if path in UPLOAD_PATHS else MAX_BODY
        if length < 0 or length > cap:
            body = b'{"detail":"Request body too large or invalid"}'
            await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"),
                                                                                  (b"content-length", str(len(body)).encode()), *SECURITY_HEADERS]})
            return await send({"type": "http.response.body", "body": body})

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                extra = list(SECURITY_HEADERS)
                if not path.startswith(DOC_PATHS):
                    extra.append((b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"))
                if path.startswith("/api/") and not any(k.lower() == b"cache-control" for k, _ in message["headers"]):
                    extra.append((b"cache-control", b"no-store"))
                message = {**message, "headers": [*message["headers"], *extra]}
            await send(message)

        await self.app(scope, receive, send_wrapped)


# ------------------------------------------------------------------ startup checks and posture

def check_startup() -> List[str]:
    """Return warnings; raise in production on unsafe configuration."""
    warnings: List[str] = []
    weak = JWT_SECRET in DEFAULT_SECRETS or len(JWT_SECRET) < 32
    if weak:
        msg = "GENOMIND_JWT_SECRET is a default or shorter than 32 characters"
        if is_production():
            raise RuntimeError(msg + "; refusing to start with GENOMERA_ENV=production")
        warnings.append(msg)
    cors_origins()   # validates
    return warnings


def posture() -> dict:
    """Real, checkable security facts for administrators. No score; each item states what was checked."""
    from backend.app import store
    from backend.app.security import verify_password
    default_pw_users = []
    for u, pw in DEFAULT_PASSWORDS.items():
        rec = store.get_user(u)
        if rec and verify_password(pw, rec["password_hash"]):
            default_pw_users.append(u)
    return {
        "environment": os.environ.get("GENOMERA_ENV", "development").lower(),
        "jwt_secret_is_default_or_short": JWT_SECRET in DEFAULT_SECRETS or len(JWT_SECRET) < 32,
        "accounts_with_default_password": default_pw_users,
        "cors_origins": cors_origins(),
        "rate_limits": {k: {"limit": v[0], "per_seconds": v[1]} for k, v in LIMITS.items()},
        "login_throttle": {"failures": LOGIN_FAILS, "per_seconds": LOGIN_WINDOW},
        "max_body_bytes": {"default": MAX_BODY, "upload": MAX_UPLOAD},
        "limitations": ["Rate limits and login throttling are per process (in-memory); use a shared store behind multiple workers.",
                        "Tokens are stateless JWTs: they cannot be revoked individually before expiry, but deleted users and role changes take effect immediately.",
                        "Case access is clinician-wide (no care-team model): any user with clinical:read can open any case."],
    }
