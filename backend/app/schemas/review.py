from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class PanelInput(BaseModel):
    panel_id: int
    target_class_id: int
    reviewer_class_id: int
    reviewer_ids: list[int] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_cross_class_panel(self) -> PanelInput:
        if self.target_class_id == self.reviewer_class_id:
            raise ValueError("target_class_id and reviewer_class_id must differ")
        if len(set(self.reviewer_ids)) != 5:
            raise ValueError("a panel requires exactly five distinct reviewers")
        return self


class InitializeRequest(BaseModel):
    assignment_id: int
    panel: PanelInput
    valid_submission_ids: list[int]


class ReviewTaskPlan(BaseModel):
    panel_id: int
    reviewer_id: int
    submission_id: int


class InitializeResponse(BaseModel):
    assignment_id: int
    panel_id: int
    expected_task_count: int
    tasks: list[ReviewTaskPlan]


class ScoreItem(BaseModel):
    rubric_item_id: int
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_score_range(self) -> ScoreItem:
        if self.score > self.max_score:
            raise ValueError("score cannot exceed max_score")
        return self


class ReviewerObservation(BaseModel):
    reviewer_id: int
    submission_id: int
    rubric_scores: list[ScoreItem] = Field(min_length=1)
    duration_seconds: int = Field(ge=0)
    comment_length: int = Field(ge=0)
    task_id: int | None = None


class AggregateRequest(BaseModel):
    assignment_id: int
    panel_id: int
    observations: list[ReviewerObservation]
    parameters: dict[str, float | int] = Field(default_factory=dict)


class AggregatePanelRequest(BaseModel):
    assignment_id: int
    panel_id: int


class ReviewerProfile(BaseModel):
    reviewer_id: int
    bias: float
    sigma: float
    anomaly_prior: float
    learned: bool


class AnomalyFinding(BaseModel):
    review_task_id: int | None
    submission_id: int
    reviewer_id: int
    risk_level: str
    risk_score: float = Field(ge=0, le=100)
    evidence: dict[str, Any]


class AggregateItem(BaseModel):
    submission_id: int
    total_score: float
    rubric_scores: dict[int, float]
    median_scores: dict[int, float] = Field(default_factory=dict)
    confidence: dict[int, float] = Field(default_factory=dict)
    confidence_intervals: dict[int, tuple[float, float]] = Field(default_factory=dict)
    risk_level: str = "LOW"
    fallback_reason: str | None = None


class AggregateResponse(BaseModel):
    assignment_id: int
    panel_id: int
    algorithm_name: str
    algorithm_version: str
    parameters: dict[str, float | int]
    results: list[AggregateItem]
    reviewer_profiles: list[ReviewerProfile]
    anomalies: list[AnomalyFinding]
    fallback_reason: str | None = None
