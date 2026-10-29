"""Credentials never leave the backend; encryption key lives in persistent storage."""

import os

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import text

from app.core.config import settings


def cipher():
    directory = settings.storage_dir / ".private"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "video-ai.key"
    try:
        # Atomic creation also handles concurrent first-time saves.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(Fernet.generate_key())
    return Fernet(path.read_bytes())


def read_config(db, teacher_id, *, secret=False):
    row = (
        db.execute(
            text("SELECT * FROM teacher_video_ai_settings WHERE teacher_id=:t"), {"t": teacher_id}
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        return None
    config = dict(row)
    encrypted = config.pop("api_key_encrypted")
    config["configured"] = bool(encrypted)
    if secret:
        try:
            config["api_key"] = cipher().decrypt(encrypted.encode()).decode()
        except (InvalidToken, ValueError, OSError) as exc:
            raise HTTPException(409, "AI_KEY_UNREADABLE") from exc
    return config


def save_config(db, teacher_id, payload):
    key = payload.api_key
    previous = read_config(db, teacher_id, secret=not bool(key))
    if not key:
        if not previous:
            raise HTTPException(422, "AI_KEY_REQUIRED")
        if (previous["provider"], previous["base_url"]) != (payload.provider, payload.base_url):
            raise HTTPException(422, "AI_KEY_REQUIRED_FOR_ENDPOINT")
        key = previous["api_key"]
    encrypted = cipher().encrypt(key.encode()).decode()
    db.execute(
        text("""INSERT INTO teacher_video_ai_settings
      (teacher_id,provider,base_url,model,api_key_encrypted,enabled)
      VALUES (:t,:p,:b,:m,:k,:e) ON CONFLICT(teacher_id) DO UPDATE SET
      provider=:p,base_url=:b,model=:m,api_key_encrypted=:k,enabled=:e,updated_at=clock_timestamp()"""),
        {
            "t": teacher_id,
            "p": payload.provider,
            "b": payload.base_url,
            "m": payload.model,
            "k": encrypted,
            "e": payload.enabled,
        },
    )
    db.commit()
    return read_config(db, teacher_id)
