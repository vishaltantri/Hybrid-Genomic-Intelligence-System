"""Auth endpoints: register, token, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from backend.app import store
from backend.app.hardening import limiter, login_gate, posture
from backend.app.models import TokenResponse, UserCreate, UserOut
from backend.app.security import create_access_token, current_user, hash_password, require, verify_password
from ml_services.config import ACCESS_TOKEN_MINUTES

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_DUMMY_HASH = hash_password("not-a-real-password")


@router.get("/security-posture")
def security_posture(user: dict = Depends(require("*"))):
    """Admin only: real configuration facts (default secret/passwords, CORS, limits) and known limitations."""
    return posture()


@router.post("/register", response_model=UserOut)
def register(payload: UserCreate, user: dict = Depends(require("*"))):
    """Create a user. Requires an admin token (bootstrap the first admin with `seed_admin.py`)."""
    if store.get_user(payload.username):
        raise HTTPException(status_code=409, detail="username already exists")
    created = store.create_user(payload.username, payload.role, hash_password(payload.password),
                               payload.full_name)
    store.audit(user["username"], "user.create", payload.username, f"role={payload.role}")
    return created


@router.post("/token", response_model=TokenResponse)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends()):
    key = login_gate(request, form.username)
    record = store.get_user(form.username)
    # Always run one bcrypt comparison so response time does not reveal whether the account exists.
    ok = verify_password(form.password, record["password_hash"] if record else _DUMMY_HASH)
    if not record or not ok:
        limiter.record("login", key)
        store.audit(form.username, "auth.login_failed", "", "")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    limiter.clear("login", key)
    token = create_access_token(record["username"], record["role"], {"full_name": record.get("full_name", "")})
    store.audit(form.username, "auth.login", form.username)
    return TokenResponse(access_token=token, role=record["role"], expires_in_minutes=ACCESS_TOKEN_MINUTES)


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
