"""Small Redis-backed queue used only for judge submission identifiers."""

from __future__ import annotations

import redis

from app.core.config import settings


def queue_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def enqueue_submission(submission_id: int) -> None:
    queue_client().rpush(settings.judge_queue_name, str(submission_id))
