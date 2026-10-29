"""Joint cross-class binary allocation with audited, seeded random tie-breaking."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from time import perf_counter

ALLOCATION_NAME = "cross_class_fair_random"
ALLOCATION_VERSION = "1.0.0"
REQUIRED_REVIEWS = 5


class AllocationError(ValueError):
    def __init__(self, code: str, details: dict | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True, order=True)
class Work:
    submission_id: int
    author_id: int
    class_id: int


@dataclass(frozen=True, order=True)
class Edge:
    reviewer_id: int
    submission_id: int


@dataclass
class Allocation:
    edges: list[Edge]
    seed: int
    input_hash: str
    loads: dict[int, int]
    quotas: dict[int, tuple[int, int]]
    diagnostics: dict = field(default_factory=dict)


def graph_metrics(edges: list[Edge], works: list[Work]) -> dict:
    """Connected components of each direction's reviewer--work bipartite graph."""
    result = {}
    for class_id in sorted({w.class_id for w in works}):
        targets = {w.submission_id for w in works if w.class_id == class_id}
        graph = defaultdict(set)
        for edge in edges:
            if edge.submission_id in targets:
                a, b = ("r", edge.reviewer_id), ("s", edge.submission_id)
                graph[a].add(b)
                graph[b].add(a)
        components = 0
        unseen = set(graph)
        while unseen:
            components += 1
            stack = [unseen.pop()]
            while stack:
                for other in graph[stack.pop()]:
                    if other in unseen:
                        unseen.remove(other)
                        stack.append(other)
        result[str(class_id)] = {"components": components, "nodes": len(graph)}
    return result


def validate_allocation(edges: list[Edge], works: list[Work], quotas: dict) -> None:
    by_id = {w.submission_id: w for w in works}
    people = {w.author_id: w.class_id for w in works}
    if len(set(edges)) != len(edges):
        raise AllocationError("DUPLICATE_ALLOCATION")
    counts, loads = Counter(), Counter()
    pairs = set()
    for edge in edges:
        target = by_id.get(edge.submission_id)
        if target is None or edge.reviewer_id not in people:
            raise AllocationError("INVALID_ALLOCATION_MEMBER")
        if people[edge.reviewer_id] == target.class_id:
            raise AllocationError("CROSS_CLASS_REQUIRED")
        pair = (edge.reviewer_id, target.author_id)
        if pair[::-1] in pairs:
            raise AllocationError("RECIPROCAL_REVIEW_FORBIDDEN")
        pairs.add(pair)
        counts[edge.submission_id] += 1
        loads[edge.reviewer_id] += 1
    if any(counts[w.submission_id] != REQUIRED_REVIEWS for w in works):
        raise AllocationError("FIVE_REVIEWS_REQUIRED")
    if any(not quotas[cls][0] <= loads[user] <= quotas[cls][1] for user, cls in people.items()):
        raise AllocationError("UNBALANCED_ALLOCATION")


def allocate_reviews(
    works: list[Work],
    seed: int,
    history: dict | None = None,
    *,
    time_limit: float = 20,
    optimize_structure: bool = True,
) -> Allocation:
    """MILP: exact five, floor/ceil loads and joint anti-reciprocity constraints.

    Historical cost has integer priority over the total seeded perturbation.
    Structure repair preserves quotas, reciprocity and historical cost.
    """
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_matrix

    started = perf_counter()
    works = sorted(works)
    history = history or {}
    classes = sorted({w.class_id for w in works})
    if len(classes) != 2 or len({w.author_id for w in works}) != len(works):
        raise AllocationError("TWO_VALID_CLASSES_REQUIRED")
    if len({w.submission_id for w in works}) != len(works):
        raise AllocationError("DUPLICATE_SUBMISSION")
    people = {w.author_id: w.class_id for w in works}
    sizes = Counter(people.values())
    quotas = {}
    for cls in classes:
        other = next(c for c in classes if c != cls)
        total = REQUIRED_REVIEWS * sizes[other]
        quotas[cls] = (total // sizes[cls], math.ceil(total / sizes[cls]))
    if min(sizes.values()) < REQUIRED_REVIEWS or (
        REQUIRED_REVIEWS * len(works) > math.prod(sizes.values())
    ):
        raise AllocationError("ALLOCATION_INFEASIBLE", {"class_sizes": dict(sizes)})
    history_rows = sorted((int(u), int(v), int(cost)) for (u, v), cost in history.items())
    snapshot = {
        "works": [asdict(w) for w in works],
        "seed": seed,
        "history": history_rows,
        "version": ALLOCATION_VERSION,
        "required_reviews": REQUIRED_REVIEWS,
        "structure": optimize_structure,
    }
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    candidates = [
        (user, work)
        for user, cls in sorted(people.items())
        for work in works
        if cls != work.class_id
    ]
    by_work, by_user, by_pair = defaultdict(list), defaultdict(list), defaultdict(list)
    for index, (user, work) in enumerate(candidates):
        by_work[work.submission_id].append(index)
        by_user[user].append(index)
        by_pair[tuple(sorted((user, work.author_id)))].append(index)
    rows, cols, vals, lower, upper = [], [], [], [], []

    def constraint(indices, lo, hi):
        row = len(lower)
        for index in indices:
            rows.append(row)
            cols.append(index)
            vals.append(1.0)
        lower.append(lo)
        upper.append(hi)

    for indices in by_work.values():
        constraint(indices, REQUIRED_REVIEWS, REQUIRED_REVIEWS)
    for user, indices in by_user.items():
        constraint(indices, *quotas[people[user]])
    for indices in by_pair.values():
        constraint(indices, 0, 1)
    matrix = coo_matrix((vals, (rows, cols)), shape=(len(lower), len(candidates))).tocsc()
    rng = random.Random(seed)
    count = len(candidates)
    objective = np.array(
        [
            max(0, history.get((user, work.author_id), 0)) + rng.random() / (count + 1)
            for user, work in candidates
        ]
    )
    solved = milp(
        objective,
        integrality=np.ones(count),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"time_limit": time_limit, "mip_rel_gap": 0, **({"threads": 1} if os.name == "nt" else {})},
    )
    if solved.status != 0:
        code = "ALLOCATION_INFEASIBLE" if solved.status == 2 else "ALLOCATION_SOLVER_LIMIT"
        raise AllocationError(
            code,
            {
                "solver_status": int(solved.status),
                "candidate_count": count,
                "constraint_count": len(lower),
                "elapsed_seconds": round(perf_counter() - started, 6),
                "time_limit_seconds": time_limit,
            },
        )
    edges = sorted(
        Edge(user, work.submission_id)
        for (user, work), value in zip(candidates, solved.x)
        if value > 0.5
    )
    validate_allocation(edges, works, quotas)
    before = graph_metrics(edges, works)
    if optimize_structure:
        edges = _repair_components(edges, works, quotas, history)
    return Allocation(
        edges,
        seed,
        digest,
        dict(Counter(e.reviewer_id for e in edges)),
        quotas,
        {
            "solver": "scipy.optimize.milp/HiGHS",
            "solver_status": 0,
            "candidate_count": count,
            "graph_before": before,
            "graph_after": graph_metrics(edges, works),
            "history_cost": _history_cost(edges, works, history),
            "elapsed_seconds": round(perf_counter() - started, 6),
            "time_limit_seconds": time_limit,
            "constraint_count": len(lower),
        },
    )


def _history_cost(edges, works, history):
    authors = {w.submission_id: w.author_id for w in works}
    return sum(history.get((e.reviewer_id, authors[e.submission_id]), 0) for e in edges)


def _repair_components(edges, works, quotas, history):
    """Bounded two-edge exchanges merge disconnected components without more repeats."""
    best = sum(v["components"] for v in graph_metrics(edges, works).values())
    if best <= 2:
        return edges
    by_id = {w.submission_id: w for w in works}
    cost = _history_cost(edges, works, history)
    attempts = 0
    for _ in range(8):
        improved = False
        for i, a in enumerate(edges):
            for j in range(i + 1, len(edges)):
                b = edges[j]
                if by_id[a.submission_id].class_id != by_id[b.submission_id].class_id:
                    continue
                attempts += 1
                if attempts > 3000:
                    return edges
                swapped = edges[:]
                swapped[i] = Edge(a.reviewer_id, b.submission_id)
                swapped[j] = Edge(b.reviewer_id, a.submission_id)
                if _history_cost(swapped, works, history) > cost:
                    continue
                try:
                    validate_allocation(swapped, works, quotas)
                except AllocationError:
                    continue
                score = sum(v["components"] for v in graph_metrics(swapped, works).values())
                if score < best:
                    edges, best = sorted(swapped), score
                    cost = _history_cost(edges, works, history)
                    improved = True
                    break
            if improved:
                break
        if not improved or best <= 2:
            break
    return edges
