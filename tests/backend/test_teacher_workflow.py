import sys
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core.security import hash_password, verify_password
from app.schemas.teacher import (
    AssignmentCreate,
    PanelConfigInput,
    ReviewPanelsInput,
    RubricItemInput,
)
from app.services.teacher_grade_service import calculate_final_score


def test_assignment_requires_two_classes_and_exact_weights() -> None:
    with pytest.raises(ValidationError):
        AssignmentCreate(
            title="期末作业",
            type="FINAL_PROJECT",
            class_ids=[1, 1],
            submit_deadline="2026-12-20T00:00:00+08:00",
            review_deadline="2026-12-21T00:00:00+08:00",
            teacher_weight=Decimal("0.7"),
            designated_review_weight=Decimal("0.4"),
            rubric_items=[RubricItemInput(name="原理", max_score=100, sort_order=1)],
        )


def test_panels_must_be_opposite_directions() -> None:
    with pytest.raises(ValidationError):
        ReviewPanelsInput(
            panels=[
                PanelConfigInput(
                    target_class_id=1, reviewer_class_id=2, reviewer_ids=[1, 2, 3, 4, 5]
                ),
                PanelConfigInput(
                    target_class_id=3,
                    reviewer_class_id=1,
                    reviewer_ids=[6, 7, 8, 9, 10],
                ),
            ]
        )


def test_final_score_uses_published_weights_without_changing_teacher_score() -> None:
    result = calculate_final_score(
        Decimal(88), Decimal(82), Decimal("0.6"), Decimal("0.4")
    )
    assert result == Decimal("85.60")


def test_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("AlgoPeer2026!")
    second = hash_password("AlgoPeer2026!")
    assert first != second
    assert verify_password("AlgoPeer2026!", first)
    assert not verify_password("wrong-password", first)
