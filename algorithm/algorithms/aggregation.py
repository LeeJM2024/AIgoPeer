"""Deterministic, sparse MAP-EM aggregation within one cross-class direction."""

from __future__ import annotations

from collections import defaultdict
from math import exp, log, pi, sqrt
from statistics import median

from app.schemas.review import (
    AggregateItem,
    AggregateRequest,
    AggregateResponse,
    AnomalyFinding,
    ReviewerProfile,
)

ALGORITHM_NAME = "panel_bayesian_robust"
ALGORITHM_VERSION = "2.1.0"
DEFAULT_PARAMETERS: dict[str, float | int] = {
    "theta_prior_mean": 0.5,
    "theta_prior_std": 0.25,
    "bias_prior_std": 0.15,
    "sigma_min": 0.05,
    "sigma_prior_mean": 0.12,
    "pi_alpha": 1.0,
    "pi_beta": 20.0,
    "max_iterations": 100,
    "convergence_tolerance": 0.000001,
    "random_seed": 20261003,
    "min_completed_works": 3,
    "required_reviewers": 5,
    "small_panel_unanimous_ci_exemption": 1,
    "credible_interval_z": 1.96,
    "wide_interval_threshold": 0.20,
    "prior_only_wide_interval_threshold": 0.25,
    "peer_span_threshold": 0.15,
    "outlier_deviation_threshold": 0.30,
    "posterior_outlier_threshold": 0.95,
    "model_median_conflict_threshold": 0.15,
    "low_entropy_min_items": 3,
    "low_entropy_threshold": 0.20,
    "hard_outlier_weight": 0.45,
    "posterior_weight": 0.35,
    "low_entropy_weight": 0.05,
    "medium_risk_threshold": 50,
}


def _clip(x: float) -> float:
    return min(1.0, max(0.0, x))


def _score(x: float) -> float:
    return round(x + 1e-12, 2)


def _density(x: float, mean: float, sigma: float) -> float:
    sigma = max(sigma, 1e-9)
    z = (x - mean) / sigma
    return exp(-z * z / 2) / (sigma * sqrt(2 * pi))


def _posterior(x: float, mean: float, sigma: float, prior: float) -> float:
    prior = min(1 - 1e-8, max(1e-8, prior))
    normal = (1 - prior) * _density(x, mean, sigma)
    return prior / (prior + normal)


def _entropy(xs: list[float]) -> float:
    bins = min(5, len(xs))
    if bins < 3:
        return 1.0
    counts = [0] * bins
    for x in xs:
        counts[min(bins - 1, int(_clip(x) * bins))] += 1
    return -sum((n / len(xs)) * log(n / len(xs)) for n in counts if n) / log(bins)


def _unanimous_submissions(request: AggregateRequest, required: int) -> set[int]:
    """Require five distinct reviewers, identical complete item sets and raw scores.

    The persistence adapter validates the assignment's full rubric. The pure
    kernel also accepts sparse matrices for analysis, but never grants this
    exemption to inconsistent item sets, duplicate reviewers/items, or mismatched maxima.
    """
    observations_by_submission: dict[int, list] = defaultdict(list)
    for observation in request.observations:
        observations_by_submission[observation.submission_id].append(observation)
    unanimous = set()
    for submission, observations in observations_by_submission.items():
        if (
            len(observations) != required
            or len({o.reviewer_id for o in observations}) != required
        ):
            continue
        signatures = []
        for observation in observations:
            items = observation.rubric_scores
            if len({item.rubric_item_id for item in items}) != len(items):
                break
            signatures.append(
                tuple(
                    sorted(
                        (item.rubric_item_id, item.score, item.max_score)
                        for item in items
                    )
                )
            )
        if len(signatures) == required and len(set(signatures)) == 1:
            unanimous.add(submission)
    return unanimous


def aggregate_panel_scores(request: AggregateRequest) -> AggregateResponse:
    """Aggregate a panel; sparse pure inputs never authorize formal publication."""
    params = {**DEFAULT_PARAMETERS, **request.parameters}
    # (reviewer, submission, rubric, task, normalized value, max, duration, chars)
    data = [
        (
            o.reviewer_id,
            o.submission_id,
            item.rubric_item_id,
            o.task_id,
            _clip(item.score / item.max_score),
            item.max_score,
            o.duration_seconds,
            o.comment_length,
        )
        for o in request.observations
        for item in o.rubric_scores
    ]
    if not data:
        return AggregateResponse(
            assignment_id=request.assignment_id,
            panel_id=request.panel_id,
            algorithm_name=ALGORITHM_NAME,
            algorithm_version=ALGORITHM_VERSION,
            parameters=params,
            results=[],
            reviewer_profiles=[],
            anomalies=[],
            fallback_reason="NO_OBSERVATIONS",
        )
    by_key: dict[tuple[int, int], list[tuple]] = defaultdict(list)
    by_reviewer: dict[int, list[tuple]] = defaultdict(list)
    by_task: dict[tuple[int, int, int | None], list[tuple]] = defaultdict(list)
    by_submission = defaultdict(dict)
    for row in data:
        by_key[(row[1], row[2])].append(row)
        by_reviewer[row[0]].append(row)
        by_task[(row[0], row[1], row[3])].append(row)
        by_submission[row[1]][row[2]] = by_key[(row[1], row[2])]
    submissions = sorted({row[1] for row in data})
    reviewers = sorted(by_reviewer)
    minimum_works = int(params["min_completed_works"])
    completed_works = {
        r: len({row[1] for row in rows}) for r, rows in by_reviewer.items()
    }
    eligible = {r for r in reviewers if completed_works[r] >= minimum_works}
    # Components are local calibration scopes. Center only learned profiles;
    # prior-only reviewers remain exactly at bias zero throughout inference.
    graph = defaultdict(set)
    for r, s, *_ in data:
        graph[("r", r)].add(("s", s))
        graph[("s", s)].add(("r", r))
    components = []
    component_by_reviewer = {}
    unseen = set(graph)
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        stack, members = [start], set()
        while stack:
            node = stack.pop()
            if node[0] == "r":
                members.add(node[1])
            for neighbor in graph[node]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
        for r in members:
            component_by_reviewer[r] = len(components)
        components.append(members)
    fallback = "PANEL_TOO_SMALL" if len(submissions) < minimum_works else None
    theta = {key: median(row[4] for row in rows) for key, rows in by_key.items()}
    bias = {r: 0.0 for r in reviewers}
    sigma = {r: float(params["sigma_prior_mean"]) for r in reviewers}
    prior = {
        r: float(params["pi_alpha"])
        / (float(params["pi_alpha"]) + float(params["pi_beta"]))
        for r in reviewers
    }
    posterior: dict[tuple, float] = {row: 0.0 for row in data}
    converged = fallback is not None
    precision = 1 / float(params["theta_prior_std"]) ** 2
    bias_precision = 1 / float(params["bias_prior_std"]) ** 2
    sigma_min = float(params["sigma_min"])
    if not fallback:
        for _ in range(int(params["max_iterations"])):
            before = (theta.copy(), bias.copy(), sigma.copy(), prior.copy())
            for row in data:
                posterior[row] = _posterior(
                    row[4],
                    _clip(theta[(row[1], row[2])] + bias[row[0]]),
                    sigma[row[0]],
                    prior[row[0]],
                )
            for key, rows in by_key.items():
                weights = [
                    (1 - posterior[row]) / max(sigma[row[0]] ** 2, sigma_min**2)
                    for row in rows
                ]
                theta[key] = _clip(
                    (
                        precision * float(params["theta_prior_mean"])
                        + sum(
                            w * (row[4] - bias[row[0]]) for row, w in zip(rows, weights)
                        )
                    )
                    / (precision + sum(weights))
                )
            for r, rows in by_reviewer.items():
                if r not in eligible:
                    continue
                weights = [
                    (1 - posterior[row]) / max(sigma[r] ** 2, sigma_min**2)
                    for row in rows
                ]
                bias[r] = sum(
                    w * (row[4] - theta[(row[1], row[2])])
                    for row, w in zip(rows, weights)
                ) / (bias_precision + sum(weights))
            for members in components:
                learned_members = members & eligible
                if learned_members:
                    center = sum(bias[r] for r in learned_members) / len(
                        learned_members
                    )
                    for r in learned_members:
                        bias[r] -= center
            for r, rows in by_reviewer.items():
                if r not in eligible:
                    continue
                normal = [1 - posterior[row] for row in rows]
                sigma[r] = max(
                    sigma_min,
                    sqrt(
                        (
                            2 * float(params["sigma_prior_mean"]) ** 2
                            + sum(
                                w * (row[4] - theta[(row[1], row[2])] - bias[r]) ** 2
                                for row, w in zip(rows, normal)
                            )
                        )
                        / (2 + sum(normal))
                    ),
                )
                prior[r] = min(
                    1 - 1e-6,
                    max(
                        1e-6,
                        (
                            float(params["pi_alpha"])
                            + sum(posterior[row] for row in rows)
                        )
                        / (
                            float(params["pi_alpha"])
                            + float(params["pi_beta"])
                            + len(rows)
                        ),
                    ),
                )
            old = before
            delta = max(
                [abs(theta[k] - old[0][k]) for k in theta]
                + [
                    abs(bias[r] - old[1][r])
                    + abs(sigma[r] - old[2][r])
                    + abs(prior[r] - old[3][r])
                    for r in reviewers
                ]
            )
            if delta < float(params["convergence_tolerance"]):
                converged = True
                break
        if not converged:
            fallback = "MODEL_NOT_CONVERGED"
        else:
            # Report posteriors at the accepted parameters, not the previous E-step.
            posterior = {
                row: _posterior(
                    row[4],
                    _clip(theta[(row[1], row[2])] + bias[row[0]]),
                    sigma[row[0]],
                    prior[row[0]],
                )
                for row in data
            }
    if fallback == "MODEL_NOT_CONVERGED":
        theta = {key: median(row[4] for row in rows) for key, rows in by_key.items()}
        bias = {r: 0.0 for r in reviewers}
        sigma = {r: float(params["sigma_prior_mean"]) for r in reviewers}
        prior = {
            r: float(params["pi_alpha"])
            / (float(params["pi_alpha"]) + float(params["pi_beta"]))
            for r in reviewers
        }
        # Zero is a compatibility placeholder, not a learned normality claim.
        posterior = {row: 0.0 for row in data}

    exempt = (
        _unanimous_submissions(request, int(params["required_reviewers"]))
        if fallback == "PANEL_TOO_SMALL"
        and params["small_panel_unanimous_ci_exemption"]
        else set()
    )
    interval_by_key = {}
    interval_threshold_by_key = {}
    for key, rows in by_key.items():
        weights = sum(
            (1 - posterior[row]) / max(sigma[row[0]] ** 2, sigma_min**2) for row in rows
        )
        radius = float(params["credible_interval_z"]) * sqrt(1 / (precision + weights))
        interval_by_key[key] = (_clip(theta[key] - radius), _clip(theta[key] + radius))
        # Five prior-noise (sigma=.12) reviews imply a ~21% interval even with
        # perfectly ordinary scores. The old 20% cutoff would automatically
        # escalate every work in a direction where reviewers have only two
        # tasks (e.g. 100:40). Keep the actual interval; use a separately audited
        # 25% cutoff only for converged, entirely prior-profile observations.
        prior_only = fallback is None and all(row[0] not in eligible for row in rows)
        interval_threshold_by_key[key] = max(
            float(params["wide_interval_threshold"]),
            float(params["prior_only_wide_interval_threshold"]) if prior_only else 0,
        )

    anomalies: list[AnomalyFinding] = []
    high_submissions: set[int] = set()
    for (_, _, task_id), rows in by_task.items():
        reviewer, submission = rows[0][0], rows[0][1]
        rules: list[str] = []
        evidence = []
        hard = False
        for row in rows:
            peers = [x[4] for x in by_key[(submission, row[2])] if x[0] != reviewer]
            pm = median(peers) if peers else row[4]
            span = max(peers) - min(peers) if len(peers) > 1 else 1
            p = posterior[row]
            hard = hard or (
                len(peers) == int(params["required_reviewers"]) - 1
                and span <= params["peer_span_threshold"]
                and abs(row[4] - pm) >= params["outlier_deviation_threshold"]
            )
            if (
                p >= params["posterior_outlier_threshold"]
                and "POSTERIOR_OUTLIER" not in rules
            ):
                rules.append("POSTERIOR_OUTLIER")
            if (
                abs(
                    theta[(submission, row[2])]
                    - median(x[4] for x in by_key[(submission, row[2])])
                )
                >= params["model_median_conflict_threshold"]
                and "MODEL_MEDIAN_CONFLICT" not in rules
            ):
                rules.append("MODEL_MEDIAN_CONFLICT")
            lo, hi = interval_by_key[(submission, row[2])]
            if (
                submission not in exempt
                and hi - lo >= interval_threshold_by_key[(submission, row[2])]
                and "WIDE_CREDIBLE_INTERVAL" not in rules
            ):
                rules.append("WIDE_CREDIBLE_INTERVAL")
            evidence.append(
                {
                    "rubric_item_id": row[2],
                    "max_score": row[5],
                    "reviewer_score": _score(row[4] * row[5]),
                    "other_four_median": _score(pm * row[5]),
                    "other_four_span": _score(span * row[5]),
                    "normalized_deviation": round(abs(row[4] - pm), 6),
                    "posterior_anomaly_probability": round(p, 6),
                    "bayesian_score": _score(theta[(submission, row[2])] * row[5]),
                    "median_score": _score(
                        median(x[4] for x in by_key[(submission, row[2])]) * row[5]
                    ),
                    "ci_lower": _score(lo * row[5]),
                    "ci_upper": _score(hi * row[5]),
                    "ci_risk_threshold": interval_threshold_by_key[(submission, row[2])],
                }
            )
        if hard:
            rules.insert(0, "FOUR_VS_ONE_OUTLIER")
        entropy = _entropy([x[4] for x in rows])
        low_entropy = (
            len(rows) >= params["low_entropy_min_items"]
            and entropy <= params["low_entropy_threshold"]
        )
        risk = 100 * min(
            1,
            params["hard_outlier_weight"] * hard
            + params["posterior_weight"] * max(posterior[x] for x in rows)
            + params["low_entropy_weight"] * low_entropy,
        )
        level = (
            "HIGH"
            if rules
            else "MEDIUM"
            if risk >= params["medium_risk_threshold"]
            else "LOW"
        )
        if level == "HIGH":
            high_submissions.add(submission)
        # LOW without any triggered signal is a normal observation, not an open case.
        if low_entropy:
            rules.append("LOW_SCORE_DIVERSITY")
        anomalies.append(
            AnomalyFinding(
                review_task_id=task_id,
                submission_id=submission,
                reviewer_id=reviewer,
                risk_level=level,
                risk_score=round(risk, 4),
                evidence={
                    "risk_level": level,
                    "risk_score": round(risk, 4),
                    "rules_triggered": rules,
                    "rubric_evidence": evidence,
                    "behavior_evidence": {
                        "duration_seconds": rows[0][6],
                        "comment_char_count": rows[0][7],
                        "normalized_entropy": round(entropy, 6),
                    },
                    "uncertainty_evidence": {
                        "interval_kind": "uncalibrated_model_around_median"
                        if fallback
                        else "calibrated_model_approximation",
                        "fallback_reason": fallback,
                        "posterior_available": fallback is None,
                        "wide_interval_exempt": submission in exempt,
                    },
                },
            )
        )
    results = []
    for submission in submissions:
        scores = {}
        medians = {}
        confidence = {}
        intervals = {}
        sid = submission
        for item, rows in by_submission[submission].items():
            maximum = rows[0][5]
            value = theta[(sid, item)]
            lo, hi = interval_by_key[(sid, item)]
            scores[item] = _score(value * maximum)
            medians[item] = _score(median(x[4] for x in rows) * maximum)
            intervals[item] = (_score(lo * maximum), _score(hi * maximum))
            confidence[item] = round(
                1 - min(1, (hi - lo) / params["wide_interval_threshold"]), 6
            )
        results.append(
            AggregateItem(
                submission_id=submission,
                total_score=_score(sum(scores.values())),
                rubric_scores=scores,
                median_scores=medians,
                confidence=confidence,
                confidence_intervals=intervals,
                risk_level="HIGH" if submission in high_submissions else "LOW",
                fallback_reason=fallback,
            )
        )
    profiles = [
        ReviewerProfile(
            reviewer_id=r,
            bias=round(bias[r], 8),
            sigma=round(sigma[r], 8),
            anomaly_prior=round(prior[r], 8),
            learned=r in eligible and converged and fallback is None,
            completed_works=completed_works[r],
            observation_count=len(by_reviewer[r]),
            graph_component=component_by_reviewer[r],
        )
        for r in reviewers
    ]
    return AggregateResponse(
        assignment_id=request.assignment_id,
        panel_id=request.panel_id,
        algorithm_name=ALGORITHM_NAME,
        algorithm_version=ALGORITHM_VERSION,
        parameters=params,
        results=results,
        reviewer_profiles=profiles,
        anomalies=anomalies,
        fallback_reason=fallback,
    )
