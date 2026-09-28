from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class PanelInput(BaseModel):
    panel_id: int
    target_class_id: int
    reviewer_class_id: int
    reviewer_ids: list[int] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_cross_class_panel(self) -> "PanelInput":
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
    def validate_score_range(self) -> "ScoreItem":
        if self.score > self.max_score:
            raise ValueError("score cannot exceed max_score")
        return self


class ReviewerObservation(BaseModel):
    reviewer_id: int
    submission_id: int
    rubric_scores: list[ScoreItem]
    duration_seconds: int = Field(ge=0)
    comment_length: int = Field(ge=0)


class AggregateRequest(BaseModel):
    assignment_id: int
    panel_id: int
    observations: list[ReviewerObservation]


class AggregateItem(BaseModel):
    submission_id: int
    total_score: float
    rubric_scores: dict[int, float]
    reviewer_bias: dict[int, float]
    confidence: float


class AggregateResponse(BaseModel):
    assignment_id: int
    panel_id: int
    algorithm_name: str
    algorithm_version: str
    results: list[AggregateItem]
