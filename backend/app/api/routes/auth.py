from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    CurrentUser,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.schemas.auth import ChangePasswordInput, LoginInput
from app.schemas.common import ApiResponse
from app.services.login_throttle import admit_login, admit_password_change

router = APIRouter()
_DUMMY_HASH = hash_password("dummy-account-timing-only")


@router.post("/change-password", response_model=ApiResponse)
def change_password(
    payload: ChangePasswordInput,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse:
    admit_password_change(db, str(current_user.id))
    user = (
        db.execute(
            text("SELECT password_hash FROM users WHERE id=:id FOR UPDATE"),
            {"id": current_user.id},
        )
        .mappings()
        .one_or_none()
    )
    if user is None:
        raise HTTPException(401, "UNAUTHENTICATED")
    if not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(400, "CURRENT_PASSWORD_INCORRECT")
    if payload.new_password == payload.current_password:
        raise HTTPException(400, "NEW_PASSWORD_UNCHANGED")
    db.execute(
        text("UPDATE users SET password_hash=:password, updated_at=now() WHERE id=:id"),
        {"password": hash_password(payload.new_password), "id": current_user.id},
    )
    # Record the action without storing passwords or password hashes in the audit trail.
    db.execute(
        text("""INSERT INTO audit_logs(actor_id,action,entity_type,entity_id)
            VALUES (:id,'CHANGE_PASSWORD','user',:id)"""),
        {"id": current_user.id},
    )
    db.commit()
    return ApiResponse(data={"changed": True})


@router.post("/login", response_model=ApiResponse)
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)) -> ApiResponse:
    admit_login(db, payload.account, request.client.host if request.client else "unknown")
    user = (
        db.execute(
            text(
                "SELECT id, student_no, name, password_hash, system_role FROM users WHERE student_no = :account"
            ),
            {"account": payload.account},
        )
        .mappings()
        .one_or_none()
    )
    password_valid = verify_password(
        payload.password, user["password_hash"] if user else _DUMMY_HASH
    )
    if user is None or not password_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_CREDENTIALS")
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user["id"]),
            "role": user["system_role"],
            "name": user["name"],
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return ApiResponse(
        data={
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.jwt_expire_minutes * 60,
            "user": {"id": user["id"], "name": user["name"], "role": user["system_role"]},
        }
    )


@router.get("/me", response_model=ApiResponse)
def me(current_user: CurrentUser = Depends(get_current_user)) -> ApiResponse:
    return ApiResponse(data={"id": current_user.id, "role": current_user.system_role})
