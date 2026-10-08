"""Shared fixed-window login admission limits, persisted across workers and restarts."""

import hashlib
import hmac

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings


def admit_login(db: Session, account: str, remote_address: str):
    scopes = [("ip", remote_address, 60, 60), ("account", account, 10, 600)]
    for kind, value, limit, seconds in scopes:
        key = hmac.new(
            settings.jwt_secret.encode(), f"{kind}:{value}".encode(), hashlib.sha256
        ).hexdigest()
        attempts = db.execute(
            text("""
            INSERT INTO login_rate_limits(scope_key) VALUES (:key)
            ON CONFLICT (scope_key) DO UPDATE SET
              attempts = CASE WHEN login_rate_limits.window_start <= now() - (:seconds * interval '1 second')
                         THEN 1 ELSE login_rate_limits.attempts + 1 END,
              window_start = CASE WHEN login_rate_limits.window_start <= now() - (:seconds * interval '1 second')
                             THEN now() ELSE login_rate_limits.window_start END
            RETURNING attempts
        """),
            {"key": key, "seconds": seconds},
        ).scalar_one()
        if attempts > limit:
            db.commit()
            raise HTTPException(429, "LOGIN_RATE_LIMITED", headers={"Retry-After": str(seconds)})
    db.execute(text("DELETE FROM login_rate_limits WHERE window_start < now() - interval '1 day'"))
    db.commit()
