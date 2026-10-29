from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

SCORE_QUANTUM = Decimal("0.01")


def calculate_teacher_total(scores: list[Decimal]) -> Decimal:
    return sum(scores, start=Decimal(0)).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


def calculate_final_score(
    teacher_score: Decimal,
    aggregate_score: Decimal,
    teacher_weight: Decimal,
    designated_review_weight: Decimal,
) -> Decimal:
    if teacher_weight < 0 or designated_review_weight < 0:
        raise ValueError("grade weights cannot be negative")
    if teacher_weight + designated_review_weight != Decimal(1):
        raise ValueError("grade weights must sum to 1")
    return (teacher_score * teacher_weight + aggregate_score * designated_review_weight).quantize(
        SCORE_QUANTUM, rounding=ROUND_HALF_UP
    )


def grade_score_preview(assignment: Mapping[str, Any], row: Mapping[str, Any]) -> dict:
    """Preview the latest saved grades without writing or publishing a final grade."""

    def result(score, state):
        return {"score_preview": score, "score_preview_state": state}

    if row["final_score"] is not None:
        return result(row["final_score"], "PUBLISHED")
    if row["status"] != "VALID" or row["material_status"] != "VALID":
        return result(None, "MATERIAL_NOT_VALID")
    if row["final_review_status"] == "ESCALATED_FOR_TEACHER_FINAL_REVIEW":
        return result(None, "FINAL_REVIEW_REQUIRED")
    if row["teacher_score"] is None:
        return result(None, "TEACHER_GRADE_REQUIRED")
    if row["task_count"] != 5 or row["completed_tasks"] != 5:
        return result(None, "REVIEWS_INCOMPLETE")
    if row["aggregate_score"] is None or row["aggregate_created_at"] is None:
        return result(None, "AGGREGATE_NOT_READY")
    if row["last_review_at"] and row["last_review_at"] > row["aggregate_created_at"]:
        return result(None, "AGGREGATE_STALE")
    if row["final_review_status"] == "FINAL_REVIEW_LOCKED":
        if row["final_review_score"] is None:
            return result(None, "FINAL_REVIEW_REQUIRED")
        return result(row["final_review_score"], "FINAL_REVIEW_LOCKED")
    score = calculate_final_score(
        row["teacher_score"],
        row["aggregate_score"],
        assignment["teacher_weight"],
        assignment["designated_review_weight"],
    )
    return result(score, "WEIGHTED" if row["locked_at"] else "TEACHER_GRADE_UNLOCKED")
