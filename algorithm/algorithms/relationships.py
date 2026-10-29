"""Signed, scale-normalized historical reviewer-author evidence.

Only prior assignments enter the history window. Repeated runs of one assignment
are collapsed by the persistence adapter; statistical support counts assignments,
not rubric rows or reaggregation attempts.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import pairwise

RELATIONSHIP_VERSION = "1.0.0"
RESIDUAL_THRESHOLD = 2.0
MIN_REPEATED_ASSIGNMENTS = 3
MIN_CYCLE_ASSIGNMENTS = 2
MAX_CYCLE_LENGTH = 4


@dataclass(frozen=True)
class RelationshipObservation:
    assignment_id: int
    reviewer_id: int
    author_id: int
    task_id: int
    residual: float
    algorithm_run_id: int | None = None


def detect_relationships(current, history):
    """Return task-keyed evidence, with bounded 2--4-person positive cycles."""
    pairs = defaultdict(list)
    for row in [*history, *current]:
        pairs[(row.reviewer_id, row.author_id)].append(row)
    positive = {}
    adjacency = defaultdict(set)
    for pair, rows in pairs.items():
        support = {r.assignment_id for r in rows if r.residual >= RESIDUAL_THRESHOLD}
        if len(support) >= MIN_CYCLE_ASSIGNMENTS:
            positive[pair] = rows
            adjacency[pair[0]].add(pair[1])
    findings = {}
    for row in current:
        if abs(row.residual) < RESIDUAL_THRESHOLD:
            continue
        pair = row.reviewer_id, row.author_id
        samples = pairs[pair]
        signed = [
            r
            for r in samples
            if abs(r.residual) >= RESIDUAL_THRESHOLD and r.residual * row.residual > 0
        ]
        repeated = len({r.assignment_id for r in signed}) >= MIN_REPEATED_ASSIGNMENTS
        # Search only a current edge's return path, bounded in depth; no global
        # enumeration of all simple cycles is needed.
        cycle = None
        if pair in positive and row.residual >= RESIDUAL_THRESHOLD:
            stack = [(row.author_id, [row.reviewer_id, row.author_id])]
            while stack and cycle is None:
                node, path = stack.pop()
                for neighbor in sorted(adjacency[node]):
                    if neighbor == row.reviewer_id:
                        cycle = [*path, neighbor]
                        break
                    if neighbor not in path and len(path) < MAX_CYCLE_LENGTH:
                        stack.append((neighbor, [*path, neighbor]))
        concentrated = (
            len({r.assignment_id for r in samples}) >= 3
            and len({r.assignment_id for r in signed}) >= 2
        )
        rules = []
        if repeated:
            rules.append("REPEATED_SIGNED_RELATIONSHIP")
        if cycle:
            rules.append("PERSISTENT_POSITIVE_CYCLE")
        if concentrated and not repeated:
            rules.append("CONCENTRATED_RELATIONSHIP_RESIDUALS")
        if not rules:
            continue
        related = samples[:]
        if cycle:
            related += [r for a, b in pairwise(cycle) for r in positive[(a, b)]]
        related = sorted(set(related), key=lambda r: (r.assignment_id, r.task_id))
        high = repeated or bool(cycle)
        findings[row.task_id] = {
            "version": RELATIONSHIP_VERSION,
            "rules_triggered": rules,
            "risk_level": "HIGH" if high else "MEDIUM",
            "risk_score": 80 if high else 55,
            "normalized_residual": round(row.residual, 6),
            "normalization": "mean((score/max-bias-theta/max)/max(sigma,0.05))",
            "pair_assignment_count": len({r.assignment_id for r in samples}),
            "signed_assignment_count": len({r.assignment_id for r in signed}),
            "cycle": cycle,
            "threshold": RESIDUAL_THRESHOLD,
            "support": [asdict(r) for r in related],
        }
    return findings
