"""Allocate newly submitted works while preserving every existing review task."""

import hashlib
import json
import os
import random
from collections import Counter, defaultdict
from dataclasses import asdict
from time import perf_counter

from .allocation import (
    REQUIRED_REVIEWS,
    Allocation,
    AllocationError,
    Edge,
    Work,
    graph_metrics,
    validate_allocation,
)

INCREMENTAL_VERSION = "1.1.0"


def allocate_additional_reviews(
    works: list[Work], seed: int, fixed: list[Edge], history=None, time_limit=20
) -> Allocation:
    """MILP: minimize cumulative squared loads, then repeats, then seeded ties.

    Existing works are fully allocated and frozen. Only edges to new works are
    variables. Marginal load slots encode the convex load objective exactly.
    """
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_matrix

    started = perf_counter()
    works, fixed = sorted(works), sorted(fixed)
    history = history or {}
    by_id = {w.submission_id: w for w in works}
    people = {w.author_id: w.class_id for w in works}
    counts = Counter(edge.submission_id for edge in fixed)
    if any(
        sid not in by_id or count != REQUIRED_REVIEWS for sid, count in counts.items()
    ):
        raise AllocationError("INVALID_EXISTING_ALLOCATION")
    if (
        len(people) != len(works)
        or len(by_id) != len(works)
        or len(set(people.values())) != 2
    ):
        raise AllocationError("TWO_VALID_CLASSES_REQUIRED")
    fresh = [w for w in works if w.submission_id not in counts]
    base = Counter(e.reviewer_id for e in fixed)
    existing_pairs = {(e.reviewer_id, by_id[e.submission_id].author_id) for e in fixed}
    candidates = [
        (u, w)
        for u, cls in sorted(people.items())
        for w in fresh
        if cls != w.class_id and (w.author_id, u) not in existing_pairs
    ]
    by_work, by_user, by_pair = defaultdict(list), defaultdict(list), defaultdict(list)
    rng = random.Random(seed)
    objective = []
    for index, (user, work) in enumerate(candidates):
        by_work[work.submission_id].append(index)
        by_user[user].append(index)
        by_pair[tuple(sorted((user, work.author_id)))].append(index)
        objective.append(
            max(0, history.get((user, work.author_id), 0))
            + rng.random() / (len(candidates) + 1)
        )
    if any(len(by_work[w.submission_id]) < REQUIRED_REVIEWS for w in fresh):
        raise AllocationError("ALLOCATION_INFEASIBLE")
    rows, cols, vals, lower, upper = [], [], [], [], []

    def constraint(indices, lo, hi, coefficients=None):
        row = len(lower)
        for index, coefficient in zip(indices, coefficients or [1] * len(indices)):
            rows.append(row)
            cols.append(index)
            vals.append(coefficient)
        lower.append(lo)
        upper.append(hi)

    for work in fresh:
        constraint(by_work[work.submission_id], REQUIRED_REVIEWS, REQUIRED_REVIEWS)
    for indices in by_pair.values():
        constraint(indices, 0, 1)
    fairness_scale = 1 + REQUIRED_REVIEWS * len(fresh) * (
        1 + max([0, *history.values()])
    )
    for user, indices in by_user.items():
        slots = []
        for offset in range(len(indices)):
            slots.append(len(objective))
            objective.append(fairness_scale * (2 * (base[user] + offset) + 1))
        constraint(indices + slots, 0, 0, [1] * len(indices) + [-1] * len(slots))
    if not fresh:
        combined = fixed
    else:
        matrix = coo_matrix(
            (vals, (rows, cols)), shape=(len(lower), len(objective))
        ).tocsc()
        result = milp(
            np.array(objective),
            integrality=np.ones(len(objective)),
            bounds=Bounds(0, 1),
            constraints=LinearConstraint(matrix, lower, upper),
            options={
                "time_limit": time_limit,
                "mip_rel_gap": 0,
                **({"threads": 1} if os.name == "nt" else {}),
            },
        )
        if result.status != 0:
            raise AllocationError(
                "ALLOCATION_INFEASIBLE"
                if result.status == 2
                else "ALLOCATION_SOLVER_LIMIT",
                {"solver_status": int(result.status)},
            )
        combined = sorted(
            fixed
            + [
                Edge(u, w.submission_id)
                for (u, w), value in zip(candidates, result.x[: len(candidates)])
                if value > 0.5
            ]
        )
    # The initial floor/ceil quota cannot be imposed retroactively on frozen tasks.
    # Incremental fairness is optimized over cumulative loads under those fixed edges.
    quotas = {
        cls: (0, sum(w.class_id != cls for w in works)) for cls in set(people.values())
    }
    validate_allocation(combined, works, quotas)
    snapshot = {
        "works": [asdict(w) for w in works],
        "fixed": [asdict(e) for e in fixed],
        "seed": seed,
        "history": sorted((u, v, cost) for (u, v), cost in history.items()),
    }
    loads = dict(Counter(e.reviewer_id for e in combined))
    return Allocation(
        combined,
        seed,
        hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest(),
        loads,
        quotas,
        {
            "mode": "incremental",
            "fixed_task_count": len(fixed),
            "new_task_count": len(combined) - len(fixed),
            "fairness_objective": "minimum cumulative squared load with fixed tasks",
            "graph_after": graph_metrics(combined, works),
            "elapsed_seconds": round(perf_counter() - started, 6),
        },
    )
