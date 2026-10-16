import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(root / "backend"), str(root)]

from app.schemas.review import AggregateRequest, ReviewerObservation, ScoreItem

from algorithm.algorithms.aggregation import aggregate_panel_scores


def observation(reviewer, submission, first, second, task):
    return ReviewerObservation(reviewer_id=reviewer, submission_id=submission, task_id=task,
        duration_seconds=300, comment_length=60, rubric_scores=[ScoreItem(rubric_item_id=1,score=first,max_score=20),ScoreItem(rubric_item_id=2,score=second,max_score=20)])


def test_bayesian_aggregation_is_panel_local_and_explainable():
    observations = []
    for sid, rows in {99:[(18,17),(19,18),(18,17),(17,18),(18,17)],100:[(16,15),(17,16),(16,15),(15,16),(16,15)],101:[(19,19),(20,19),(19,18),(18,19),(19,19)]}.items():
        observations += [observation(r, sid, *score, sid*10+r) for r, score in enumerate(rows, 1)]
    result = aggregate_panel_scores(AggregateRequest(assignment_id=1,panel_id=10,observations=observations))
    item = next(item for item in result.results if item.submission_id == 99)
    assert result.algorithm_name == "panel_bayesian_robust" and item.risk_level == "LOW"
    assert item.median_scores == {1: 18.0, 2: 17.0} and 34 <= item.total_score <= 37
    assert len(result.reviewer_profiles) == 5


def test_one_extreme_reviewer_creates_high_risk_evidence():
    observations = []
    for sid, rows in {99:[(18,17),(19,18),(18,17),(18,18),(12,10)],100:[(17,16)]*5,101:[(19,18)]*5}.items():
        observations += [observation(r, sid, *score, sid*10+r) for r, score in enumerate(rows, 1)]
    result = aggregate_panel_scores(AggregateRequest(assignment_id=1,panel_id=10,observations=observations))
    anomalous = next(x for x in result.anomalies if x.submission_id == 99 and x.reviewer_id == 5)
    assert anomalous.risk_level == "HIGH"
    assert "FOUR_VS_ONE_OUTLIER" in anomalous.evidence["rules_triggered"]


def test_small_panel_uses_median_fallback():
    result = aggregate_panel_scores(AggregateRequest(assignment_id=1,panel_id=10,observations=[observation(r,99,*score,r) for r,score in enumerate([(18,17),(16,15),(17,16),(18,17),(17,16)],1)]))
    assert result.fallback_reason == "PANEL_TOO_SMALL"
    assert result.results[0].rubric_scores == {1: 17.0, 2: 16.0}
