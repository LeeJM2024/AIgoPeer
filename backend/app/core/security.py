from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("password must contain at least 10 characters")
    salt = os.urandom(16)
    result = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(result).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text)
        expected = base64.urlsafe_b64decode(digest_text)
        actual = hashlib.scrypt(
            password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class CurrentUser:
    id: int
    system_role: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="UNAUTHENTICATED")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "role", "exp", "iat"]},
        )
        if payload["role"] not in {"TEACHER", "STUDENT"} or int(payload["sub"]) <= 0:
            raise ValueError("invalid identity")
        return CurrentUser(id=int(payload["sub"]), system_role=str(payload["role"]))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="UNAUTHENTICATED"
        ) from exc


def require_teacher(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.system_role != "TEACHER":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    return user


def require_internal_service(x_internal_token: str | None = Header(default=None)) -> None:
    if not settings.internal_api_token:
        raise HTTPException(503, "INTERNAL_SERVICE_NOT_CONFIGURED")
    if not x_internal_token or not hmac.compare_digest(
        x_internal_token.encode(), settings.internal_api_token.encode()
    ):
        raise HTTPException(403, "FORBIDDEN")
