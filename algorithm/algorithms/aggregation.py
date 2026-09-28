from __future__ import annotations

from collections import defaultdict
from statistics import fmean, pstdev

from app.schemas.review import AggregateItem, AggregateRequest, AggregateResponse

ALGORITHM_NAME = "panel_local_bias_calibrated_mean"
ALGORITHM_VERSION = "0.1.0"


def aggregate_panel_scores(request: AggregateRequest) -> AggregateResponse:
    """Panel-local mean aggregation with a transparent reviewer-bias correction.

    A reviewer's bias is their mean normalized score minus the panel-wide mean.
    Scores are corrected by subtracting this bias, then clipped to each rubric's
    valid range. This is an MVP baseline inspired by score calibration literature;
    it is deliberately computed inside one panel and never reads/writes teacher
    grades. A later version may replace it but must retain this input/output shape.
    """
    if not request.observations:
        return AggregateResponse(
            assignment_id=request.assignment_id,
            panel_id=request.panel_id,
            algorithm_name=ALGORITHM_NAME,
            algorithm_version=ALGORITHM_VERSION,
            results=[],
        )

    normalized_by_reviewer: dict[int, list[float]] = defaultdict(list)
    normalized_all: list[float] = []
    for observation in request.observations:
        for item in observation.rubric_scores:
            normalized = item.score / item.max_score
            normalized_by_reviewer[observation.reviewer_id].append(normalized)
            normalized_all.append(normalized)
    global_mean = fmean(normalized_all)
    bias = {reviewer_id: fmean(values) - global_mean for reviewer_id, values in normalized_by_reviewer.items()}

    by_submission: dict[int, list] = defaultdict(list)
    for observation in request.observations:
        by_submission[observation.submission_id].append(observation)

    results: list[AggregateItem] = []
    for submission_id, observations in by_submission.items():
        score_buckets: dict[int, list[float]] = defaultdict(list)
        max_scores: dict[int, float] = {}
        normalized_totals: list[float] = []
        for observation in observations:
            for item in observation.rubric_scores:
                corrected = min(item.max_score, max(0.0, item.score - bias[observation.reviewer_id] * item.max_score))
                score_buckets[item.rubric_item_id].append(corrected)
                max_scores[item.rubric_item_id] = item.max_score
                normalized_totals.append(corrected / item.max_score)
        rubric_scores = {item_id: round(fmean(values), 3) for item_id, values in score_buckets.items()}
        dispersion = pstdev(normalized_totals) if len(normalized_totals) > 1 else 0.0
        confidence = round(max(0.0, 1.0 - dispersion), 3)
        results.append(
            AggregateItem(
                submission_id=submission_id,
                total_score=round(sum(rubric_scores.values()), 3),
                rubric_scores=rubric_scores,
                reviewer_bias={reviewer_id: round(value, 5) for reviewer_id, value in bias.items()},
                confidence=confidence,
            )
        )
    return AggregateResponse(
        assignment_id=request.assignment_id,
        panel_id=request.panel_id,
        algorithm_name=ALGORITHM_NAME,
        algorithm_version=ALGORITHM_VERSION,
        results=results,
    )
