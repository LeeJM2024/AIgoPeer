from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewScoreInput(BaseModel):
    rubric_item_id: int = Field(gt=0)
    score: Decimal = Field(ge=0, max_digits=7, decimal_places=2)


class ReviewSubmissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rubric_scores: list[ReviewScoreInput] = Field(min_length=1)
    comment: str = Field(min_length=1, max_length=10000)
    # Retained for the published API contract.  The server records its own
    # started_at when the reviewer first retrieves the anonymous package.
    started_at: datetime | None = None

    @field_validator("comment")
    @classmethod
    def comment_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("comment must not be blank")
        return value.strip()


class ReviewRevisionInput(ReviewSubmissionInput):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_must_be_meaningful(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("revision reason must contain at least three characters")
        return value
