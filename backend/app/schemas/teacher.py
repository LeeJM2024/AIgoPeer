from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator


class TeacherInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, allow_inf_nan=False)


class RubricItemInput(TeacherInput):
    name: str = Field(min_length=1, max_length=100)
    max_score: Decimal = Field(gt=0, le=1000, decimal_places=2)
    sort_order: int = Field(ge=1)
    description: str | None = Field(default=None, max_length=2000)


class AssignmentCreate(TeacherInput):
    title: str = Field(min_length=1, max_length=200)
    type: str = Field(pattern="^(PROGRAMMING|FINAL_PROJECT)$")
    class_ids: list[int] = Field(min_length=2, max_length=2)
    submit_deadline: AwareDatetime
    review_deadline: AwareDatetime
    teacher_weight: Decimal = Field(ge=0, le=1, decimal_places=4)
    designated_review_weight: Decimal = Field(ge=0, le=1, decimal_places=4)
    rubric_items: list[RubricItemInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assignment(self) -> AssignmentCreate:
        if len(set(self.class_ids)) != 2:
            raise ValueError("exactly two distinct classes are required")
        if self.review_deadline <= self.submit_deadline:
            raise ValueError("review_deadline must be after submit_deadline")
        if self.teacher_weight + self.designated_review_weight != Decimal(1):
            raise ValueError("teacher_weight and designated_review_weight must sum to 1")
        orders = [item.sort_order for item in self.rubric_items]
        if sum(item.max_score for item in self.rubric_items) > Decimal("99999.99"):
            raise ValueError("rubric total exceeds supported score range")
        if len(orders) != len(set(orders)):
            raise ValueError("rubric sort_order values must be unique")
        return self


class PanelConfigInput(BaseModel):
    target_class_id: int
    reviewer_class_id: int
    reviewer_ids: list[int] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_panel(self) -> PanelConfigInput:
        if self.target_class_id == self.reviewer_class_id:
            raise ValueError("target and reviewer classes must differ")
        if len(set(self.reviewer_ids)) != 5:
            raise ValueError("a panel requires five distinct reviewers")
        return self


class ReviewPanelsInput(BaseModel):
    panels: list[PanelConfigInput] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_opposite_panels(self) -> ReviewPanelsInput:
        first, second = self.panels
        if (
            first.target_class_id != second.reviewer_class_id
            or first.reviewer_class_id != second.target_class_id
        ):
            raise ValueError("the two panels must be opposite directions between the same classes")
        return self


class RubricScoreInput(TeacherInput):
    rubric_item_id: int
    score: Decimal = Field(ge=0, decimal_places=2)


class TeacherGradeInput(TeacherInput):
    rubric_scores: list[RubricScoreInput] = Field(min_length=1)
    comment: str = Field(default="", max_length=5000)


class TeacherGradeCorrectionInput(TeacherGradeInput):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)


class AnomalyResolutionInput(TeacherInput):
    status: str = Field(pattern="^(CONFIRMED|DISMISSED)$")
    note: str = Field(min_length=2, max_length=2000)


class TeacherFinalReviewInput(TeacherInput):
    final_score: Decimal = Field(ge=0, decimal_places=2)
    reason: str = Field(min_length=3, max_length=2000)


class ClassInput(TeacherInput):
    name: str = Field(min_length=1, max_length=100)
    course_term: str = Field(min_length=1, max_length=64)


class StudentInput(TeacherInput):
    student_no: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=100)
    password: (
        Annotated[str, StringConstraints(strip_whitespace=False, min_length=10, max_length=128)]
        | None
    ) = None


class StudentImportInput(TeacherInput):
    students: list[StudentInput] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_accounts(self):
        if len({s.student_no for s in self.students}) != len(self.students):
            raise ValueError("duplicate student numbers in import")
        return self


class ReviewDeadlineInput(TeacherInput):
    review_deadline: AwareDatetime
    reason: str = Field(min_length=3, max_length=1000)


class DraftAssignmentUpdate(AssignmentCreate):
    expected_updated_at: AwareDatetime
