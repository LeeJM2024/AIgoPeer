"""Provider-neutral contract for future evidence-based video analysis.

Provider output is advisory and must never write teacher_grades or final_grades.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VideoProviderStatus:
    provider: str | None
    model: str | None
    configured: bool
    enabled: bool


class VideoAnalysisProvider(Protocol):
    def analyze(self, *, storage_key: str, rubric: list[dict], input_hash: str) -> str:
        """Start analysis and return a provider job identifier."""

    def poll(self, job_id: str) -> dict:
        """Return normalized status, evidence timestamps, confidence, and suggestions."""

    def delete_remote_file(self, job_id: str) -> None:
        """Delete provider-side material after configured retention expires."""


def get_video_provider_status(settings) -> VideoProviderStatus:
    configured = bool(
        settings.ai_video_provider and settings.ai_video_api_key and settings.ai_video_model
    )
    return VideoProviderStatus(
        provider=settings.ai_video_provider or None,
        model=settings.ai_video_model or None,
        configured=configured,
        enabled=configured and settings.ai_video_enabled,
    )
