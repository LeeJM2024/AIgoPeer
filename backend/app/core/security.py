from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

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
    session_id: str | None = None


def credential_stamp(password_hash: str) -> str:
    return hmac.new(
        settings.jwt_secret.encode(), password_hash.encode(), hashlib.sha256
    ).hexdigest()


def _guard_request(request: Request, db: Session, user: CurrentUser) -> None:
    """Consume nonces atomically, even when the business transaction rolls back."""
    writing = request.method not in {"GET", "HEAD", "OPTIONS"}
    nonce = request.headers.get("X-Request-Nonce", "")
    if writing:
        timestamp = request.headers.get("X-Request-Timestamp", "")
        if not re.fullmatch(r"[0-9]{10}", timestamp) or not re.fullmatch(r"[a-f0-9]{32}", nonce):
            raise HTTPException(400, "REQUEST_PROOF_REQUIRED")
        age = time.time() - int(timestamp)
        if age > 300 or age < -30:
            raise HTTPException(409, "REQUEST_EXPIRED")
    # Separate connection: never commit or roll back the caller's business writes.
    from app.services.login_throttle import _admit

    with Session(bind=db.get_bind()) as guard:
        scopes = [("api:user", str(user.id), 600, 60)]
        if writing:
            scopes.append(("api:write", str(user.id), 120, 60))
            if re.fullmatch(r"/api/assignments/[0-9]+/project-submissions", request.url.path):
                scopes.append(("api:upload", str(user.id), 10, 600))
            if re.fullmatch(r"/api/assignments/[0-9]+/code-submissions", request.url.path):
                scopes.append(("api:judge", str(user.id), 10, 60))
        _admit(guard, scopes, "API_RATE_LIMITED")
        if writing:
            consumed = guard.execute(
                text("""INSERT INTO request_nonces(session_id,nonce)
                VALUES (:session,:nonce) ON CONFLICT DO NOTHING RETURNING nonce"""),
                {"session": user.session_id, "nonce": nonce},
            ).scalar_one_or_none()
            guard.commit()
            if consumed is None:
                raise HTTPException(409, "REQUEST_REPLAYED")
        if secrets.randbelow(100) == 0:
            guard.execute(text("DELETE FROM request_nonces WHERE expires_at < now()"))
            guard.execute(text("DELETE FROM auth_sessions WHERE expires_at < now()"))
            guard.commit()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="UNAUTHENTICATED")
    if len(credentials.credentials) > 4096:
        raise HTTPException(401, "UNAUTHENTICATED")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="algopeer",
            audience="algopeer-web",
            options={"require": ["sub", "role", "exp", "iat", "jti", "iss", "aud"]},
        )
        if (
            payload["role"] not in {"TEACHER", "STUDENT"}
            or not isinstance(payload["sub"], str)
            or not re.fullmatch(r"[1-9][0-9]{0,18}", payload["sub"])
            or int(payload["sub"]) > 2**63 - 1
            or not isinstance(payload["jti"], str)
            or not re.fullmatch(r"[a-f0-9]{48}", payload["jti"])
        ):
            raise ValueError("invalid identity")
    except (jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="UNAUTHENTICATED"
        ) from exc
    # Authentication must not start the route's business transaction: analytics
    # sets REPEATABLE READ, and uploads rely on their own transaction boundaries.
    with Session(bind=db.get_bind()) as authentication:
        row = (
            authentication.execute(
                text("""SELECT u.system_role,u.password_hash,s.credential_stamp
        FROM auth_sessions s JOIN users u ON u.id=s.user_id
        WHERE s.id=:session AND s.user_id=:user AND s.revoked_at IS NULL AND s.expires_at > now()"""),
                {"session": payload["jti"], "user": int(payload["sub"])},
            )
            .mappings()
            .one_or_none()
        )
    if (
        row is None
        or row["system_role"] != payload["role"]
        or not hmac.compare_digest(row["credential_stamp"], credential_stamp(row["password_hash"]))
    ):
        raise HTTPException(401, "UNAUTHENTICATED")
    user = CurrentUser(int(payload["sub"]), str(row["system_role"]), payload["jti"])
    _guard_request(request, db, user)
    return user


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
