from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StudentSubmissionSummary(BaseModel):
    """The current student's latest final-project submission only."""

    id: int
    status: str
    material_check_status: str | None = None


class StudentAssignmentSummary(BaseModel):
    """Safe assignment-list projection for the authenticated student."""

    id: int
    title: str
    type: str
    status: str
    submit_deadline: datetime | None = None
    review_deadline: datetime | None = None
    submission: StudentSubmissionSummary | None = None
