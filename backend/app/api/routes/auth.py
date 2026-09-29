from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import CurrentUser, get_current_user, verify_password
from app.db.session import get_db
from app.schemas.auth import LoginInput
from app.schemas.common import ApiResponse

router = APIRouter()


@router.post("/login", response_model=ApiResponse)
def login(payload: LoginInput, db: Session = Depends(get_db)) -> ApiResponse:
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
    if user is None or not verify_password(payload.password, user["password_hash"]):
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
