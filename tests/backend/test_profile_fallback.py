"""Regression cases for profile eligibility and small-panel consensus policy."""

import pytest
from app.schemas.review import AggregateRequest, ReviewerObservation, ScoreItem

from algorithm.algorithms.aggregation import aggregate_panel_scores


def panel_observations(works=1, scores=(85,), reviewers=range(1, 6)):
    return [
        ReviewerObservation(
            reviewer_id=reviewer,
            submission_id=submission,
            task_id=submission * 10 + reviewer,
            duration_seconds=300,
            comment_length=60,
            rubric_scores=[
                ScoreItem(rubric_item_id=item, score=score, max_score=100)
                for item, score in enumerate(scores, 1)
            ],
        )
        for submission in range(1, works + 1)
        for reviewer in reviewers
    ]


def aggregate(observations, **parameters):
    return aggregate_panel_scores(
        AggregateRequest(
            assignment_id=1,
            panel_id=1,
            observations=observations,
            parameters=parameters,
        )
    )


def assert_prior(profile):
    assert profile.learned is False
    assert profile.bias == 0
    assert profile.sigma == 0.12
    assert profile.anomaly_prior == pytest.approx(1 / 21, abs=1e-8)


@pytest.mark.parametrize("works,rubrics", [(1, 1), (1, 3), (2, 3)])
def test_small_panel_counts_works_not_rubric_rows(works, rubrics):
    result = aggregate(panel_observations(works, (85,) * rubrics))
    assert result.fallback_reason == "PANEL_TOO_SMALL"
    for profile in result.reviewer_profiles:
        assert_prior(profile)
    for item in result.results:
        assert item.total_score == 85 * rubrics
        assert item.rubric_scores == item.median_scores


@pytest.mark.parametrize("works", [1, 2])
def test_complete_consensus_uses_median_without_wide_interval_high(works):
    # Items may differ from one another: only agreement across reviewers matters.
    result = aggregate(panel_observations(works, (85, 70, 60)))
    assert result.fallback_reason == "PANEL_TOO_SMALL"
    for item in result.results:
        assert item.total_score == 215
        assert item.risk_level == "LOW"
        assert item.confidence_intervals[1] == (74.72, 95.28)
        assert item.confidence[1] == 0
    for finding in result.anomalies:
        assert "WIDE_CREDIBLE_INTERVAL" not in finding.evidence["rules_triggered"]
        assert finding.evidence["uncertainty_evidence"]["wide_interval_exempt"] is True
        assert finding.evidence["uncertainty_evidence"]["posterior_available"] is False


def test_successful_model_learns_eligible_profiles():
    result = aggregate(panel_observations(3))
    assert result.fallback_reason is None
    assert all(profile.learned for profile in result.reviewer_profiles)
    assert all(profile.sigma != 0.12 for profile in result.reviewer_profiles)
    assert all(item.risk_level == "LOW" for item in result.results)


def test_ineligible_reviewer_keeps_prior_during_em_and_centering():
    observations = panel_observations(3, (75, 65, 55))
    observations = [
        o for o in observations if o.reviewer_id != 5 or o.submission_id == 1
    ]
    next(o for o in observations if o.reviewer_id == 5).rubric_scores[0].score = 80
    result = aggregate(observations)
    assert result.fallback_reason is None
    profiles = {profile.reviewer_id: profile for profile in result.reviewer_profiles}
    assert_prior(profiles[5])
    assert all(profiles[r].learned for r in range(1, 5))
    assert sum(profile.bias for profile in profiles.values()) == pytest.approx(
        0, abs=1e-7
    )


def test_failed_model_discards_iteration_profiles_and_does_not_get_exemption():
    result = aggregate(panel_observations(3), max_iterations=1)
    assert result.fallback_reason == "MODEL_NOT_CONVERGED"
    for profile in result.reviewer_profiles:
        assert_prior(profile)
    for item in result.results:
        assert item.total_score == 85
        assert item.risk_level == "HIGH"
        assert item.confidence_intervals[1] == (74.72, 95.28)
    for finding in result.anomalies:
        assert "WIDE_CREDIBLE_INTERVAL" in finding.evidence["rules_triggered"]
        assert (
            finding.evidence["rubric_evidence"][0]["posterior_anomaly_probability"] == 0
        )


def test_one_disagreeing_item_prevents_exemption_for_the_whole_work():
    observations = panel_observations(scores=(85, 70))
    observations[-1].rubric_scores[1].score = 69
    result = aggregate(observations)
    assert result.results[0].risk_level == "HIGH"
    assert all(
        "WIDE_CREDIBLE_INTERVAL" in finding.evidence["rules_triggered"]
        for finding in result.anomalies
    )


def test_consensus_exemption_is_per_work_not_per_panel():
    observations = panel_observations(2)
    observations[-1].rubric_scores[0].score = 84
    result = aggregate(observations)
    assert [item.risk_level for item in result.results] == ["LOW", "HIGH"]


@pytest.mark.parametrize(
    "case", ["four_reviews", "duplicate_reviewer", "missing_item", "duplicate_item"]
)
def test_incomplete_or_duplicate_scores_do_not_get_consensus_exemption(case):
    observations = panel_observations(scores=(85, 70))
    if case == "four_reviews":
        observations.pop()
    elif case == "duplicate_reviewer":
        observations[-1].reviewer_id = observations[0].reviewer_id
    elif case == "missing_item":
        observations[-1].rubric_scores.pop()
    else:
        observations[-1].rubric_scores.append(
            observations[-1].rubric_scores[0].model_copy()
        )
    result = aggregate(observations)
    assert result.results[0].risk_level == "HIGH"


def test_equal_normalized_scores_with_different_maxima_do_not_get_exemption():
    observations = panel_observations()
    observations[-1].rubric_scores[0].max_score = 200
    observations[-1].rubric_scores[0].score = 170
    assert aggregate(observations).results[0].risk_level == "HIGH"


def test_four_against_one_extreme_score_remains_high_in_small_panel():
    observations = panel_observations()
    observations[-1].rubric_scores[0].score = 10
    result = aggregate(observations)
    assert result.results[0].total_score == 85
    assert result.results[0].risk_level == "HIGH"
    finding = next(f for f in result.anomalies if f.reviewer_id == 5)
    assert "FOUR_VS_ONE_OUTLIER" in finding.evidence["rules_triggered"]


def test_consensus_keeps_behavior_evidence_and_task_ids_are_optional():
    observations = panel_observations(2)
    for observation in observations:
        observation.task_id = None
        observation.duration_seconds = 30
        observation.comment_length = 5
    result = aggregate(observations)
    assert len(result.anomalies) == 10
    for finding in result.anomalies:
        assert finding.risk_level == "LOW"
        assert finding.risk_score == 0
        assert finding.evidence["rules_triggered"] == []
        assert finding.evidence["behavior_evidence"]["duration_seconds"] == 30
        assert finding.evidence["behavior_evidence"]["comment_char_count"] == 5
    assert all(item.risk_level != "HIGH" for item in result.results)


@pytest.mark.parametrize("duration,chars", [(0, 60), (300, 0), (1, 1)])
@pytest.mark.parametrize("extreme", [False, True])
def test_duration_and_comment_length_do_not_change_risk(duration, chars, extreme):
    observations = panel_observations(3, (85, 65, 45))
    if extreme:
        observations[-1].rubric_scores[0].score = 5
    baseline = aggregate(observations)
    for observation in observations:
        observation.duration_seconds = duration
        observation.comment_length = chars
    # Even legacy caller parameters cannot reactivate the retired signals.
    result = aggregate(observations, short_duration_weight=100, short_comment_weight=100,
                       medium_behavior_signals=1)
    assert result.results == baseline.results
    for actual, expected in zip(result.anomalies, baseline.anomalies, strict=True):
        assert (actual.risk_level, actual.risk_score, actual.evidence["rules_triggered"]) == (
            expected.risk_level, expected.risk_score, expected.evidence["rules_triggered"])


def test_low_score_diversity_remains_without_short_behavior_escalation():
    observations = panel_observations(scores=(85, 85, 85))
    for observation in observations:
        observation.duration_seconds = 1
        observation.comment_length = 1
    result = aggregate(observations)
    assert all(f.risk_level == "LOW" and f.risk_score == 5 for f in result.anomalies)
    assert all(f.evidence["rules_triggered"] == ["LOW_SCORE_DIVERSITY"] for f in result.anomalies)
