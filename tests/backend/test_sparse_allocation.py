from collections import Counter

import pytest
from app.schemas.review import AggregateRequest, ReviewerObservation, ScoreItem

from algorithm.algorithms.aggregation import aggregate_panel_scores
from algorithm.algorithms.allocation import (
    AllocationError,
    Work,
    allocate_reviews,
    graph_metrics,
    validate_allocation,
)
from algorithm.algorithms.relationships import (
    RelationshipObservation,
    detect_relationships,
)


def works(left=12, right=10):
    return [Work(i, i, 1 if i <= left else 2) for i in range(1, left + right + 1)]


@pytest.mark.parametrize("sizes", [(10, 10), (12, 10), (20, 8)])
def test_joint_exact_five_balanced_nonreciprocal_reproducible(sizes):
    inputs = works(*sizes)
    plan = allocate_reviews(inputs, 717)
    validate_allocation(plan.edges, inputs, plan.quotas)
    assert len(plan.edges) == 5 * len(inputs)
    assert plan.edges == allocate_reviews(inputs[::-1], 717).edges
    assert plan.input_hash == allocate_reviews(inputs[::-1], 717).input_hash
    assert all(v["components"] == 1 for v in graph_metrics(plan.edges, inputs).values())
    for cls in (1, 2):
        counts = [plan.loads.get(w.author_id, 0) for w in inputs if w.class_id == cls]
        assert max(counts) - min(counts) <= 1


def test_history_priority_and_seed_variation():
    inputs = works(12, 12)
    first = allocate_reviews(inputs, 41)
    second = allocate_reviews(inputs, 42)
    assert first.edges != second.edges
    history = {(e.reviewer_id, e.submission_id): 1 for e in first.edges}
    fresh = allocate_reviews(inputs, 41, history)
    assert fresh.diagnostics["history_cost"] < len(first.edges)
    assert fresh.input_hash != first.input_hash


@pytest.mark.parametrize("sizes", [(5, 5), (9, 10), (4, 100)])
def test_infeasible_class_sizes_are_explicit(sizes):
    with pytest.raises(AllocationError, match="ALLOCATION_INFEASIBLE"):
        allocate_reviews(works(*sizes), 1)


def test_sparse_rotating_reviewers_keep_low_sample_priors():
    observations = [
        ReviewerObservation(
            reviewer_id=(s + j) % 10 + 1,
            submission_id=s + 100,
            task_id=s * 5 + j,
            rubric_scores=[ScoreItem(rubric_item_id=1, score=70 + s, max_score=100)],
            duration_seconds=300,
            comment_length=60,
        )
        for s in range(4)
        for j in range(5)
    ]
    result = aggregate_panel_scores(
        AggregateRequest(assignment_id=1, panel_id=2, observations=observations)
    )
    assert result.fallback_reason is None
    assert len(result.reviewer_profiles) > 5
    counts = Counter(o.reviewer_id for o in observations)
    for profile in result.reviewer_profiles:
        assert profile.completed_works == counts[profile.reviewer_id]
        if profile.completed_works < 3:
            assert not profile.learned
            assert profile.bias == 0 and profile.sigma == 0.12
        else:
            assert profile.learned


def test_disconnected_component_inference_is_independent():
    def inputs(offset, score):
        return [
            ReviewerObservation(
                reviewer_id=r + offset,
                submission_id=s + offset,
                rubric_scores=[
                    ScoreItem(rubric_item_id=1, score=score + r, max_score=100)
                ],
                duration_seconds=300,
                comment_length=60,
            )
            for r in range(1, 6)
            for s in range(1, 4)
        ]

    a, b = inputs(0, 60), inputs(100, 80)
    alone = aggregate_panel_scores(
        AggregateRequest(assignment_id=1, panel_id=2, observations=a)
    )
    combined = aggregate_panel_scores(
        AggregateRequest(assignment_id=1, panel_id=2, observations=[*a, *b])
    )
    assert combined.fallback_reason is None
    assert [x.total_score for x in combined.results[:3]] == [
        x.total_score for x in alone.results
    ]
    assert len({p.graph_component for p in combined.reviewer_profiles}) == 2


def test_small_sparse_consensus_uses_each_works_own_five():
    observations = [
        ReviewerObservation(
            reviewer_id=r + 10 * s,
            submission_id=s,
            rubric_scores=[ScoreItem(rubric_item_id=1, score=85, max_score=100)],
            duration_seconds=300,
            comment_length=60,
        )
        for s in range(1, 3)
        for r in range(1, 6)
    ]
    result = aggregate_panel_scores(
        AggregateRequest(assignment_id=1, panel_id=2, observations=observations)
    )
    assert len(result.reviewer_profiles) == 10
    assert all(
        a.evidence["uncertainty_evidence"]["wide_interval_exempt"]
        for a in result.anomalies
    )


def test_relationship_support_counts_assignments_not_rows():
    current = [RelationshipObservation(3, 1, 2, 300, 2.5)]
    history = [RelationshipObservation(1, 1, 2, i, 2.5) for i in range(10)]
    assert not detect_relationships(current, history)
    history.append(RelationshipObservation(2, 1, 2, 20, 2.5))
    found = detect_relationships(current, history)[300]
    assert found["risk_level"] == "HIGH" and found["signed_assignment_count"] == 3
    assert not detect_relationships(
        [RelationshipObservation(3, 1, 2, 300, 0.2)], history
    )


def test_persistent_cross_class_four_person_cycle():
    pairs = [(1, 2), (2, 3), (3, 4), (4, 1)]
    history = [
        RelationshipObservation(a, u, v, 10 * a + j, 2.5)
        for a in (1, 2)
        for j, (u, v) in enumerate(pairs)
    ]
    current = [RelationshipObservation(3, 1, 2, 30, 2.5)]
    finding = detect_relationships(current, history)[30]
    assert "PERSISTENT_POSITIVE_CYCLE" in finding["rules_triggered"]
    assert finding["cycle"] == [1, 2, 3, 4, 1]


def test_two_task_prior_profiles_do_not_mass_escalate_normal_works():
    inputs = works(100, 40)
    plan = allocate_reviews(inputs, 41)
    targets = {w.submission_id for w in inputs if w.class_id == 2}
    observations = [
        ReviewerObservation(
            reviewer_id=e.reviewer_id,
            submission_id=e.submission_id,
            task_id=i,
            rubric_scores=[ScoreItem(rubric_item_id=1, score=80, max_score=100)],
            duration_seconds=300,
            comment_length=60,
        )
        for i, e in enumerate(plan.edges, 1)
        if e.submission_id in targets
    ]
    request = AggregateRequest(assignment_id=1, panel_id=2, observations=observations)
    normal = aggregate_panel_scores(request)
    assert normal.fallback_reason is None
    assert all(
        not p.learned and p.completed_works == 2 for p in normal.reviewer_profiles
    )
    assert all(item.risk_level == "LOW" for item in normal.results)
    assert all(
        "WIDE_CREDIBLE_INTERVAL" not in f.evidence["rules_triggered"]
        for f in normal.anomalies
    )
    assert all(
        f.evidence["rubric_evidence"][0]["ci_risk_threshold"] == 0.25
        for f in normal.anomalies
    )
    # Keep the genuine >20% approximate interval, rather than fabricating a
    # narrower one to pass the risk rule.
    assert all(
        hi - lo > 20
        for item in normal.results
        for lo, hi in item.confidence_intervals.values()
    )
    changed = request.model_copy(deep=True)
    changed.observations[0].rubric_scores[0].score = 10
    abnormal = aggregate_panel_scores(changed)
    finding = next(
        f for f in abnormal.anomalies if f.review_task_id == observations[0].task_id
    )
    assert finding.risk_level == "HIGH"
    assert "FOUR_VS_ONE_OUTLIER" in finding.evidence["rules_triggered"]
