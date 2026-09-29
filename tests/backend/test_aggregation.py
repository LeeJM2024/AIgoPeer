import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))
sys.path.insert(0, str(root))

from app.schemas.review import AggregateRequest, ReviewerObservation, ScoreItem

from algorithm.algorithms.aggregation import aggregate_panel_scores


def test_aggregation_is_panel_local_and_returns_explainable_result() -> None:
    request = AggregateRequest(
        assignment_id=1,
        panel_id=10,
        observations=[
            ReviewerObservation(reviewer_id=1, submission_id=99, rubric_scores=[ScoreItem(rubric_item_id=1, score=18, max_score=20)], duration_seconds=500, comment_length=30),
            ReviewerObservation(reviewer_id=2, submission_id=99, rubric_scores=[ScoreItem(rubric_item_id=1, score=16, max_score=20)], duration_seconds=600, comment_length=40),
        ],
    )
    result = aggregate_panel_scores(request)

    assert result.panel_id == 10
    assert result.algorithm_name == "panel_local_bias_calibrated_mean"
    assert len(result.results) == 1
    assert set(result.results[0].reviewer_bias) == {1, 2}
