from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

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
