"""Run from the repository: python -m algorithm.experiments.sparse_review.

Set PYTHONPATH=backend when the backend package is not installed editable.
Synthetic truth and scenario assumptions are included in the output. This is
an engineering experiment, not a claim of empirical classroom performance.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median, pstdev
from time import perf_counter

from app.schemas.review import AggregateRequest, ReviewerObservation, ScoreItem

from algorithm.algorithms.aggregation import (
    ALGORITHM_VERSION,
    DEFAULT_PARAMETERS,
    aggregate_panel_scores,
)
from algorithm.algorithms.allocation import (
    ALLOCATION_VERSION,
    AllocationError,
    Edge,
    Work,
    allocate_reviews,
    graph_metrics,
)


def make_works(left, right):
    return [Work(i, i, 1 if i <= left else 2) for i in range(1, left + right + 1)]


def baseline(works, seed, kind):
    rng = random.Random(seed)
    edges = []
    for cls in (1, 2):
        people = [w.author_id for w in works if w.class_id != cls]
        targets = [w for w in works if w.class_id == cls]
        rng.shuffle(people)
        rng.shuffle(targets)
        for i, work in enumerate(targets):
            if kind == "fixed_five":
                selected = people[:5]
            elif kind == "random":
                selected = rng.sample(people, 5)
            else:
                selected = [people[(5 * i + j) % len(people)] for j in range(5)]
            edges.extend(Edge(u, work.submission_id) for u in selected)
    return edges


def metrics(edges, works, history):
    authors = {w.submission_id: w.author_id for w in works}
    pairs = {(e.reviewer_id, authors[e.submission_id]) for e in edges}
    loads = Counter(e.reviewer_id for e in edges)
    counts = Counter(e.submission_id for e in edges)
    return {
        "task_count": len(edges),
        "all_exact_five": all(counts[w.submission_id] == 5 for w in works),
        "reciprocal_pairs": sum((v, u) in pairs for u, v in pairs) // 2,
        "load_gap_by_class": {
            str(cls): max(values) - min(values)
            for cls in (1, 2)
            for values in [[loads[w.author_id] for w in works if w.class_id == cls]]
        },
        "repeated_edge_rate": mean((u, v) in history for u, v in pairs),
        "history_cost": sum(history.get(pair, 0) for pair in pairs),
        "graph": graph_metrics(edges, works),
    }


def errors(predicted, truth):
    differences = [predicted[k] - v for k, v in truth.items()]
    return {
        "mae": mean(abs(v) for v in differences),
        "rmse": math.sqrt(mean(v * v for v in differences)),
    }


def simulate_scores(works, edges, seed, mode):
    rng = random.Random(seed + 10000)
    truth = {w.submission_id: rng.uniform(40, 90) for w in works}
    # Each class has centered synthetic reviewer bias, matching the inference
    # identifiability convention; this assumption is not hidden in the results.
    bias = {}
    for cls in (1, 2):
        users = [w.author_id for w in works if w.class_id == cls]
        values = [rng.uniform(-10, 10) for _ in users]
        center = mean(values)
        bias.update({u: v - center for u, v in zip(users, values, strict=True)})
    observations = []
    true_anomalies = set()
    for tid, edge in enumerate(sorted(edges), 1):
        score = truth[edge.submission_id] + bias[edge.reviewer_id] + rng.gauss(0, 3)
        abnormal = mode == "contaminated" and rng.random() < 0.1
        if abnormal:
            score = 5 if truth[edge.submission_id] >= 60 else 98
            true_anomalies.add(tid)
        observations.append(
            ReviewerObservation(
                reviewer_id=edge.reviewer_id,
                submission_id=edge.submission_id,
                task_id=tid,
                rubric_scores=[
                    ScoreItem(
                        rubric_item_id=1,
                        score=round(min(100, max(0, score)), 2),
                        max_score=100,
                    )
                ],
                duration_seconds=20 if abnormal else 300,
                comment_length=10 if abnormal else 60,
            )
        )
    by_work = defaultdict(list)
    for o in observations:
        by_work[o.submission_id].append(o.rubric_scores[0].score)
    predictions = {
        "mean": {s: mean(v) for s, v in by_work.items()},
        "median": {s: median(v) for s, v in by_work.items()},
        "trimmed_mean": {s: mean(sorted(v)[1:-1]) for s, v in by_work.items()},
    }
    bayesian, profiles, intervals, findings, fallbacks = {}, [], {}, [], []
    for cls in (1, 2):
        targets = {w.submission_id for w in works if w.class_id == cls}
        request = AggregateRequest(
            assignment_id=1,
            panel_id=cls,
            observations=[o for o in observations if o.submission_id in targets],
        )
        result = aggregate_panel_scores(request)
        bayesian.update({r.submission_id: r.total_score for r in result.results})
        profiles.extend(result.reviewer_profiles)
        intervals.update(
            {r.submission_id: r.confidence_intervals[1] for r in result.results}
        )
        findings.extend(result.anomalies)
        fallbacks.append(result.fallback_reason)
    predictions["sparse_bayes"] = bayesian
    detected = {f.review_task_id for f in findings if f.risk_level == "HIGH"}
    tp, fp, fn = (
        len(detected & true_anomalies),
        len(detected - true_anomalies),
        len(true_anomalies - detected),
    )
    return {
        "scenario": mode,
        "truth_distribution": "uniform(40,90)",
        "bias_distribution": "class-centered uniform(-10,10)",
        "noise_std": 3,
        "contamination_rate": 0.1 if mode == "contaminated" else 0,
        "errors": {
            name: errors(prediction, truth) for name, prediction in predictions.items()
        },
        "fallback_by_direction": fallbacks,
        "interval_coverage": mean(
            lo <= truth[s] <= hi for s, (lo, hi) in intervals.items()
        ),
        "interval_mean_width": mean(hi - lo for lo, hi in intervals.values()),
        "learned_profiles": sum(p.learned for p in profiles),
        "prior_profiles": sum(not p.learned for p in profiles),
        "bias_mae_learned": mean(
            abs(p.bias * 100 - bias[p.reviewer_id]) for p in profiles if p.learned
        )
        if any(p.learned for p in profiles)
        else None,
        "bias_mae_prior": mean(
            abs(bias[p.reviewer_id]) for p in profiles if not p.learned
        )
        if any(not p.learned for p in profiles)
        else None,
        "detection": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "false_positive_rate": fp / (len(observations) - len(true_anomalies))
            if len(observations) > len(true_anomalies)
            else None,
            "high_task_count": len(detected),
        },
    }


def run(seeds):
    results = []
    initial_round = []
    for left, right in ((10, 10), (100, 40), (120, 40)):
        works = make_works(left, right)
        for seed in seeds:
            started = perf_counter()
            try:
                initial = allocate_reviews(works, seed)
                initial_round.append(
                    {
                        "sizes": [left, right],
                        "seed": seed,
                        "status": "COMPLETED",
                        "diagnostics": initial.diagnostics,
                        "metrics": metrics(initial.edges, works, {}),
                    }
                )
            except AllocationError as exc:
                initial_round.append(
                    {
                        "sizes": [left, right],
                        "seed": seed,
                        "status": "FAILED",
                        "error": exc.code,
                        "diagnostics": exc.details,
                    }
                )
            initial_round[-1]["elapsed_seconds"] = perf_counter() - started
            print(
                f"initial {left}:{right} seed={seed} {initial_round[-1]['status']} {initial_round[-1]['elapsed_seconds']:.2f}s",
                flush=True,
            )
        historical = baseline(works, 20261021, "random")
        history = {(e.reviewer_id, e.submission_id): 20 for e in historical}
        for seed in seeds:
            row = {"sizes": [left, right], "seed": seed, "baselines": {}}
            for kind in ("fixed_five", "random", "balanced"):
                row["baselines"][kind] = metrics(
                    baseline(works, seed, kind), works, history
                )
            started = perf_counter()
            try:
                plan = allocate_reviews(
                    works, seed, history, time_limit=60, optimize_structure=False
                )
                # Reuse the identical solved graph to isolate the structure
                # exchange's effect, rather than run a different random plan.
                from algorithm.algorithms.allocation import _repair_components

                repaired = _repair_components(plan.edges, works, plan.quotas, history)
                row.update(
                    status="COMPLETED",
                    elapsed_seconds=perf_counter() - started,
                    before_structure=metrics(plan.edges, works, history),
                    after_structure=metrics(repaired, works, history),
                    diagnostics=plan.diagnostics,
                    aggregation=[
                        simulate_scores(works, repaired, seed, mode)
                        for mode in ("normal", "contaminated")
                    ],
                )
            except AllocationError as exc:
                row.update(
                    status="FAILED",
                    elapsed_seconds=perf_counter() - started,
                    error=exc.code,
                    diagnostics=exc.details,
                )
            results.append(row)
            print(
                f"{left}:{right} seed={seed} {row['status']} {row['elapsed_seconds']:.2f}s",
                flush=True,
            )
    summary = {}
    for mode in ("normal", "contaminated"):
        values = [
            a
            for r in results
            for a in r.get("aggregation", [])
            if a["scenario"] == mode
        ]
        summary[mode] = (
            {
                method: {
                    "mae_mean": mean(v["errors"][method]["mae"] for v in values),
                    "mae_std": pstdev(v["errors"][method]["mae"] for v in values),
                }
                for method in ("mean", "median", "trimmed_mean", "sparse_bayes")
            }
            if values
            else {}
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "allocation_version": ALLOCATION_VERSION,
        "aggregation_version": ALGORITHM_VERSION,
        "aggregation_parameters": DEFAULT_PARAMETERS,
        "seeds": seeds,
        "initial_round": initial_round,
        "results": results,
        "summary": summary,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=[41, 42, 43])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/experiments/cross-class-sparse.json"),
    )
    args = parser.parse_args()
    output = run(args.seeds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))
