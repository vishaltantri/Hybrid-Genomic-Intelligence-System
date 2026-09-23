"""Auth endpoints: register, token, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from backend.app import store
from backend.app.models import TokenResponse, UserCreate, UserOut
from backend.app.security import create_access_token, current_user, hash_password, require, verify_password
from ml_services.config import ACCESS_TOKEN_MINUTES

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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
def login(form: OAuth2PasswordRequestForm = Depends()):
    record = store.get_user(form.username)
    if not record or not verify_password(form.password, record["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    token = create_access_token(form.username, record["role"], {"full_name": record.get("full_name", "")})
    store.audit(form.username, "auth.login", form.username)
    return TokenResponse(access_token=token, role=record["role"], expires_in_minutes=ACCESS_TOKEN_MINUTES)


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
