from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ReviewScoreInput(BaseModel):
    rubric_item_id: int = Field(gt=0)
    score: Decimal = Field(ge=0, max_digits=7, decimal_places=2)


class ReviewSubmissionInput(BaseModel):
    rubric_scores: list[ReviewScoreInput] = Field(min_length=1)
    comment: str = Field(min_length=1, max_length=10000)
    # Retained for the published API contract.  The server records its own
    # started_at when the reviewer first retrieves the anonymous package.
    started_at: datetime

    @field_validator("comment")
    @classmethod
    def comment_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("comment must not be blank")
        return value.strip()
