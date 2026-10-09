"""Database adapter for member 3's reproducible, panel-local algorithm."""

from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.review import AggregateRequest, ReviewerObservation, ScoreItem
from app.services.teacher_workflow import lock_assignment


def _canonical_hash(observations: list[ReviewerObservation]) -> str:
    rows = []
    for observation in sorted(
        observations, key=lambda x: (x.submission_id, x.reviewer_id, x.task_id or 0)
    ):
        for score in sorted(observation.rubric_scores, key=lambda x: x.rubric_item_id):
            rows.append(
                {
                    "submission_id": observation.submission_id,
                    "reviewer_id": observation.reviewer_id,
                    "task_id": observation.task_id,
                    "rubric_item_id": score.rubric_item_id,
                    "score": score.score,
                    "max_score": score.max_score,
                    "duration_seconds": observation.duration_seconds,
                    "comment_length": observation.comment_length,
                }
            )
    return hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _create_run(
    db: Session, assignment_id: int, panel_id: int, input_hash: str, status: str
) -> int:
    return db.execute(
        text("""INSERT INTO algorithm_runs(assignment_id,panel_id,algorithm_name,version,
        parameters_json,input_hash,status,finished_at) VALUES (:assignment,:panel,'panel_bayesian_robust','1.0.0',
        CAST(:parameters AS jsonb),:hash,CAST(:status AS text),CASE WHEN CAST(:status AS text)='RUNNING' THEN NULL ELSE now() END) RETURNING id"""),
        {
            "assignment": assignment_id,
            "panel": panel_id,
            "parameters": json.dumps(
                {
                    "inference": "MAP-EM",
                    "random_seed": 20261003,
                    "max_iterations": 100,
                    "convergence_tolerance": 0.000001,
                }
            ),
            "hash": input_hash,
            "status": status,
        },
    ).scalar_one()


def aggregate_panel_and_persist(db: Session, assignment_id: int, panel_id: int) -> dict:
    """Lock parent assignment, snapshot every submitted task, then persist one run.

    The caller owns commit/rollback.  This lock order intentionally matches
    teacher publication and makes a published assignment immutable to a late
    worker retry.
    """
    assignment = lock_assignment(db, assignment_id)
    if assignment["type"] != "FINAL_PROJECT" or assignment["status"] not in {
        "REVIEWER_GRADING",
        "AGGREGATING",
        "TEACHER_GRADING",
    }:
        raise HTTPException(400, "INVALID_STATE")
    panel = (
        db.execute(
            text("""SELECT id,target_class_id FROM review_panels
        WHERE id=:panel AND assignment_id=:assignment FOR SHARE"""),
            {"panel": panel_id, "assignment": assignment_id},
        )
        .mappings()
        .one_or_none()
    )
    if panel is None:
        raise HTTPException(404, "PANEL_NOT_FOUND")
    valid = list(
        db.execute(
            text("""SELECT s.id FROM submissions s JOIN material_checks mc ON mc.submission_id=s.id
        WHERE s.assignment_id=:assignment AND s.class_id=:class_id AND s.is_current AND s.status='VALID' AND mc.status='VALID' ORDER BY s.id"""),
            {"assignment": assignment_id, "class_id": panel["target_class_id"]},
        ).scalars()
    )
    if not valid:
        return {"status": "NO_VALID_SUBMISSIONS", "panel_id": panel_id}
    counts = (
        db.execute(
            text("""SELECT submission_id,count(*) AS total,count(*) FILTER (WHERE status='SUBMITTED') AS submitted
        FROM review_tasks WHERE panel_id=:panel GROUP BY submission_id"""),
            {"panel": panel_id},
        )
        .mappings()
        .all()
    )
    by_submission = {row["submission_id"]: row for row in counts}
    incomplete = [
        sid
        for sid in valid
        if sid not in by_submission
        or by_submission[sid]["total"] != 5
        or by_submission[sid]["submitted"] != 5
    ]
    if incomplete:
        run_id = _create_run(
            db, assignment_id, panel_id, hashlib.sha256(str(valid).encode()).hexdigest(), "FAILED"
        )
        db.execute(
            text(
                "UPDATE algorithm_runs SET parameters_json=jsonb_set(parameters_json,'{failure_reason}','\"INSUFFICIENT_REVIEWS\"') WHERE id=:id"
            ),
            {"id": run_id},
        )
        return {
            "algorithm_run_id": run_id,
            "status": "INSUFFICIENT_REVIEWS",
            "missing_submission_ids": incomplete,
        }
    rows = (
        db.execute(
            text("""SELECT rt.id task_id,rt.reviewer_id,rt.submission_id,
        GREATEST(0,COALESCE(EXTRACT(EPOCH FROM rt.submitted_at-rt.started_at),0)::int) duration_seconds,
        COALESCE(rc.char_count,0) comment_length,rs.rubric_item_id,rs.score,ri.max_score
        FROM review_tasks rt JOIN review_scores rs ON rs.review_task_id=rt.id JOIN rubric_items ri ON ri.id=rs.rubric_item_id
        LEFT JOIN review_comments rc ON rc.review_task_id=rt.id WHERE rt.panel_id=:panel AND rt.status='SUBMITTED'
        AND rt.submission_id=ANY(:valid)
        ORDER BY rt.submission_id,rt.reviewer_id,rs.rubric_item_id"""),
            {"panel": panel_id, "valid": valid},
        )
        .mappings()
        .all()
    )
    packed = {}
    for row in rows:
        entry = packed.setdefault(
            row["task_id"],
            {
                "reviewer_id": row["reviewer_id"],
                "submission_id": row["submission_id"],
                "task_id": row["task_id"],
                "duration_seconds": row["duration_seconds"],
                "comment_length": row["comment_length"],
                "rubric_scores": [],
            },
        )
        entry["rubric_scores"].append(
            ScoreItem(
                rubric_item_id=row["rubric_item_id"],
                score=float(row["score"]),
                max_score=float(row["max_score"]),
            )
        )
    observations = [ReviewerObservation(**entry) for entry in packed.values()]
    expected_items = db.execute(
        text(
            "SELECT count(*) FROM rubric_items ri JOIN rubrics r ON r.id=ri.rubric_id WHERE r.assignment_id=:id"
        ),
        {"id": assignment_id},
    ).scalar_one()
    if len(observations) != len(valid) * 5 or any(
        len(o.rubric_scores) != expected_items for o in observations
    ):
        run_id = _create_run(db, assignment_id, panel_id, _canonical_hash(observations), "FAILED")
        return {"algorithm_run_id": run_id, "status": "INVALID_REVIEW_SNAPSHOT"}
    from algorithm.algorithms.aggregation import aggregate_panel_scores

    request = AggregateRequest(
        assignment_id=assignment_id, panel_id=panel_id, observations=observations
    )
    input_hash = _canonical_hash(observations)
    existing = db.execute(
        text("""SELECT id FROM algorithm_runs WHERE assignment_id=:assignment AND panel_id=:panel
        AND algorithm_name='panel_bayesian_robust' AND version='1.0.0' AND input_hash=:hash AND status='COMPLETED'
        ORDER BY id DESC LIMIT 1"""),
        {"assignment": assignment_id, "panel": panel_id, "hash": input_hash},
    ).scalar_one_or_none()
    if existing is not None:
        _advance_if_complete(db, assignment_id)
        return {"algorithm_run_id": existing, "status": "COMPLETED", "reused": True}
    if db.execute(
        text("SELECT EXISTS(SELECT 1 FROM teacher_final_reviews WHERE submission_id=ANY(:ids))"),
        {"ids": valid},
    ).scalar_one():
        raise HTTPException(409, "FINAL_REVIEW_PREVENTS_REAGGREGATION")
    run_id = _create_run(db, assignment_id, panel_id, input_hash, "RUNNING")
    savepoint = db.begin_nested()
    try:
        result = aggregate_panel_scores(request)
        for profile in result.reviewer_profiles:
            db.execute(
                text("""INSERT INTO reviewer_profiles(assignment_id,panel_id,reviewer_id,bias_json,reliability,lazy_probability)
                VALUES(:assignment,:panel,:reviewer,CAST(:bias AS jsonb),:reliability,:lazy)
                ON CONFLICT(assignment_id,panel_id,reviewer_id) DO UPDATE SET bias_json=EXCLUDED.bias_json,reliability=EXCLUDED.reliability,lazy_probability=EXCLUDED.lazy_probability"""),
                {
                    "assignment": assignment_id,
                    "panel": panel_id,
                    "reviewer": profile.reviewer_id,
                    "bias": json.dumps({"bias": profile.bias, "sigma": profile.sigma}),
                    "reliability": round(1 / (profile.sigma**2), 5),
                    "lazy": profile.anomaly_prior,
                },
            )
        for item in result.results:
            db.execute(
                text("""INSERT INTO designated_review_aggregates(submission_id,panel_id,algorithm_run_id,total_score,rubric_scores_json,confidence_json)
                VALUES(:submission,:panel,:run,:total,CAST(:scores AS jsonb),CAST(:confidence AS jsonb))"""),
                {
                    "submission": item.submission_id,
                    "panel": panel_id,
                    "run": run_id,
                    "total": item.total_score,
                    "scores": json.dumps(item.rubric_scores),
                    "confidence": json.dumps(
                        {
                            "per_item": item.confidence,
                            "intervals": item.confidence_intervals,
                            "median_scores": item.median_scores,
                            "fallback_reason": item.fallback_reason,
                        }
                    ),
                },
            )
        high = {item.submission_id for item in result.results if item.risk_level == "HIGH"}
        for finding in result.anomalies:
            if finding.risk_level != "LOW":
                db.execute(
                    text("""INSERT INTO anomaly_records(submission_id,review_task_id,algorithm_run_id,risk_level,risk_score,evidence_json)
                VALUES(:submission,:task,:run,:level,:score,CAST(:evidence AS jsonb))"""),
                    {
                        "submission": finding.submission_id,
                        "task": finding.review_task_id,
                        "run": run_id,
                        "level": finding.risk_level,
                        "score": finding.risk_score,
                        "evidence": json.dumps(finding.evidence),
                    },
                )
        if high:
            db.execute(
                text(
                    "UPDATE submissions SET final_review_status='ESCALATED_FOR_TEACHER_FINAL_REVIEW',updated_at=now() WHERE id=ANY(:ids)"
                ),
                {"ids": sorted(high)},
            )
        db.execute(
            text("UPDATE algorithm_runs SET status='COMPLETED',finished_at=now() WHERE id=:id"),
            {"id": run_id},
        )
        _advance_if_complete(db, assignment_id)
        savepoint.commit()
        return {
            "algorithm_run_id": run_id,
            "status": "COMPLETED",
            "results": len(result.results),
            "high_risk_submissions": sorted(high),
        }
    except Exception as exc:  # noqa: BLE001 - record any numerical/persistence failure as a run.
        savepoint.rollback()
        # Do not expose SQL parameters, review content or connection details in errors.
        reason = type(exc).__name__
        db.execute(
            text(
                "UPDATE algorithm_runs SET status='FAILED',finished_at=now(),parameters_json=jsonb_set(parameters_json,'{failure_reason}',to_jsonb(CAST(:reason AS text))) WHERE id=:id"
            ),
            {"id": run_id, "reason": reason},
        )
        return {"algorithm_run_id": run_id, "status": "FAILED", "reason": reason}


def _advance_if_complete(db: Session, assignment_id: int) -> None:
    missing = db.execute(
        text("""SELECT count(*) FROM submissions s
        JOIN material_checks mc ON mc.submission_id=s.id
        WHERE s.assignment_id=:id AND s.is_current AND s.status='VALID' AND mc.status='VALID'
        AND NOT EXISTS (
            SELECT 1 FROM designated_review_aggregates ag
            JOIN algorithm_runs ar ON ar.id=ag.algorithm_run_id
            JOIN review_panels p ON p.id=ag.panel_id
            WHERE ag.submission_id=s.id AND p.assignment_id=s.assignment_id
              AND p.target_class_id=s.class_id AND ar.panel_id=p.id
              AND ar.assignment_id=s.assignment_id AND ar.status='COMPLETED'
              AND ar.algorithm_name='panel_bayesian_robust'
              AND ag.created_at >= (SELECT max(submitted_at) FROM review_tasks WHERE submission_id=s.id)
        )"""),
        {"id": assignment_id},
    ).scalar_one()
    if not missing:
        db.execute(
            text("UPDATE assignments SET status='TEACHER_GRADING',updated_at=now() WHERE id=:id"),
            {"id": assignment_id},
        )
