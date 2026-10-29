from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import CurrentUser, get_current_user, hash_password, verify_password
from app.db.session import get_db
from app.schemas.auth import LoginInput, RegisterInput
from app.schemas.common import ApiResponse
from app.services.login_throttle import admit_login, admit_registration

router = APIRouter()
_DUMMY_HASH = hash_password("dummy-account-timing-only")


@router.post("/register", response_model=ApiResponse, status_code=201)
def register(
    payload: RegisterInput, request: Request, db: Session = Depends(get_db)
) -> ApiResponse:
    admit_registration(db, payload.student_no, request.client.host if request.client else "unknown")
    user = (
        db.execute(
            text("""INSERT INTO users(student_no, name, password_hash, system_role)
                    VALUES (:student_no, :name, :password_hash, 'STUDENT')
                    ON CONFLICT (student_no) DO NOTHING RETURNING id, name"""),
            {
                "student_no": payload.student_no,
                "name": payload.name,
                "password_hash": hash_password(payload.password),
            },
        )
        .mappings()
        .one_or_none()
    )
    if user is None:
        db.rollback()
        raise HTTPException(409, "ACCOUNT_ALREADY_EXISTS")
    db.commit()
    return ApiResponse(data={"user": {"id": user["id"], "name": user["name"], "role": "STUDENT"}})


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
