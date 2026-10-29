"""Database adapter for member 3's reproducible, panel-local algorithm."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from algorithm.algorithms.aggregation import (
    ALGORITHM_NAME,
    ALGORITHM_VERSION,
    DEFAULT_PARAMETERS,
    aggregate_panel_scores,
)
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.review import AggregateRequest, ReviewerObservation, ScoreItem
from app.services.assignment_lifecycle import submission_intake_open
from app.services.relationship_service import apply_relationship_evidence, relationship_history
from app.services.teacher_workflow import lock_assignment


def _run_parameters() -> dict:
    return {
        **DEFAULT_PARAMETERS,
        "inference": "MAP-EM",
        "low_evidence_policy": 2,
        "profile_learning_policy": "distinct_works_and_converged",
        "fallback_interval_policy": "uncalibrated_model_around_median",
        "nonconvergence_policy": "fail_persistence",
        "observation_policy": "sparse_active_five_distinct_per_work",
        "bias_centering": "learned_profiles_per_connected_component",
        "relationship_policy": "signed_residual_v1_window20",
    }


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
        parameters_json,input_hash,status,finished_at) VALUES (:assignment,:panel,:algorithm,:version,
        CAST(:parameters AS jsonb),:hash,CAST(:status AS text),CASE WHEN CAST(:status AS text)='RUNNING' THEN NULL ELSE now() END) RETURNING id"""),
        {
            "assignment": assignment_id,
            "panel": panel_id,
            "algorithm": ALGORITHM_NAME,
            "version": ALGORITHM_VERSION,
            "parameters": json.dumps(_run_parameters()),
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
    if submission_intake_open(assignment):
        raise HTTPException(409, "SUBMISSIONS_STILL_OPEN")
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
            text("""SELECT submission_id,count(DISTINCT reviewer_id) AS total,count(DISTINCT reviewer_id) FILTER (WHERE status='SUBMITTED') AS submitted
        FROM review_tasks WHERE panel_id=:panel AND is_active GROUP BY submission_id"""),
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
        LEFT JOIN review_comments rc ON rc.review_task_id=rt.id WHERE rt.panel_id=:panel AND rt.is_active AND rt.status='SUBMITTED'
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
    expected_items = set(
        db.execute(
            text(
                "SELECT ri.id FROM rubric_items ri JOIN rubrics r ON r.id=ri.rubric_id WHERE r.assignment_id=:id"
            ),
            {"id": assignment_id},
        ).scalars()
    )
    if len(observations) != len(valid) * 5 or any(
        {s.rubric_item_id for s in o.rubric_scores} != expected_items for o in observations
    ):
        run_id = _create_run(db, assignment_id, panel_id, _canonical_hash(observations), "FAILED")
        return {"algorithm_run_id": run_id, "status": "INVALID_REVIEW_SNAPSHOT"}
    request = AggregateRequest(
        assignment_id=assignment_id, panel_id=panel_id, observations=observations
    )
    history = relationship_history(db, assignment_id)
    snapshot = {"scores": _canonical_hash(observations), "history": [asdict(r) for r in history]}
    revisions = db.execute(text("""SELECT rev.review_task_id,max(rev.version) AS version
        FROM review_revisions rev JOIN review_tasks rt ON rt.id=rev.review_task_id
        WHERE rt.panel_id=:panel AND rt.is_active AND rt.status='SUBMITTED' AND rt.submission_id=ANY(:valid)
        GROUP BY rev.review_task_id ORDER BY rev.review_task_id"""),
        {"panel": panel_id, "valid": valid}).mappings().all()
    if revisions:
        # Same-length comment corrections still create a fresh evidence snapshot.
        snapshot["review_revisions"] = [dict(row) for row in revisions]
    input_hash = hashlib.sha256(
        json.dumps(
            snapshot,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    existing = db.execute(
        text("""SELECT id FROM algorithm_runs WHERE assignment_id=:assignment AND panel_id=:panel
        AND algorithm_name=:algorithm AND version=:version AND input_hash=:hash AND status='COMPLETED'
        AND parameters_json-'low_evidence_policy'-'relationship_history_snapshot'=CAST(:parameters AS jsonb)-'low_evidence_policy'
        ORDER BY id DESC LIMIT 1"""),
        {
            "assignment": assignment_id,
            "panel": panel_id,
            "algorithm": ALGORITHM_NAME,
            "version": ALGORITHM_VERSION,
            "hash": input_hash,
            "parameters": json.dumps(_run_parameters()),
        },
    ).scalar_one_or_none()
    if existing is not None:
        # Older adapters discarded LOW evidence. Reproduce it before reusing an unpublished run.
        policy = db.execute(
            text("SELECT parameters_json->>'low_evidence_policy' FROM algorithm_runs WHERE id=:id"),
            {"id": existing},
        ).scalar_one()
        if policy != "2":
            result = aggregate_panel_scores(request)
            for finding in result.anomalies:
                if finding.risk_level == "LOW" and finding.evidence.get("rules_triggered"):
                    db.execute(
                        text("""INSERT INTO anomaly_records(submission_id,review_task_id,algorithm_run_id,risk_level,risk_score,evidence_json)
                      SELECT :submission,:task,:run,'LOW',:score,CAST(:evidence AS jsonb)
                      WHERE NOT EXISTS(SELECT 1 FROM anomaly_records WHERE algorithm_run_id=:run AND review_task_id=:task)"""),
                        {
                            "submission": finding.submission_id,
                            "task": finding.review_task_id,
                            "run": existing,
                            "score": finding.risk_score,
                            "evidence": json.dumps(finding.evidence),
                        },
                    )
            db.execute(
                text(
                    "UPDATE algorithm_runs SET parameters_json=jsonb_set(parameters_json,'{low_evidence_policy}','2') WHERE id=:id"
                ),
                {"id": existing},
            )
        _advance_if_complete(db, assignment_id)
        return {"algorithm_run_id": existing, "status": "COMPLETED", "reused": True}
    if db.execute(
        text("SELECT EXISTS(SELECT 1 FROM teacher_final_reviews WHERE submission_id=ANY(:ids))"),
        {"ids": valid},
    ).scalar_one():
        raise HTTPException(409, "FINAL_REVIEW_PREVENTS_REAGGREGATION")
    run_id = _create_run(db, assignment_id, panel_id, input_hash, "RUNNING")
    db.execute(
        text(
            "UPDATE algorithm_runs SET parameters_json=parameters_json || CAST(:snapshot AS jsonb) WHERE id=:id"
        ),
        {
            "id": run_id,
            "snapshot": json.dumps({"relationship_history_snapshot": [asdict(r) for r in history]}),
        },
    )
    savepoint = db.begin_nested()
    try:
        result = aggregate_panel_scores(request)
        if result.fallback_reason == "MODEL_NOT_CONVERGED":
            raise ValueError("MODEL_NOT_CONVERGED")
        apply_relationship_evidence(db, assignment_id, run_id, result, history)
        uncertainty = {
            finding.submission_id: finding.evidence["uncertainty_evidence"]
            for finding in result.anomalies
        }
        for profile in result.reviewer_profiles:
            db.execute(
                text("""INSERT INTO reviewer_profiles(assignment_id,panel_id,reviewer_id,bias_json,reliability,lazy_probability)
                VALUES(:assignment,:panel,:reviewer,CAST(:bias AS jsonb),:reliability,:lazy)
                ON CONFLICT(assignment_id,panel_id,reviewer_id) DO UPDATE SET bias_json=EXCLUDED.bias_json,reliability=EXCLUDED.reliability,lazy_probability=EXCLUDED.lazy_probability"""),
                {
                    "assignment": assignment_id,
                    "panel": panel_id,
                    "reviewer": profile.reviewer_id,
                    "bias": json.dumps(profile.model_dump(exclude={"reviewer_id"})),
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
                            "uncertainty_evidence": uncertainty[item.submission_id],
                        }
                    ),
                },
            )
        high = {item.submission_id for item in result.results if item.risk_level == "HIGH"}
        for finding in result.anomalies:
            if finding.risk_level != "LOW" or finding.evidence.get("rules_triggered"):
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
        # A new policy result must not retain obsolete open cases from an older
        # result for the identical snapshot. Preserve scores, evidence and runs;
        # archive only superseded OPEN cases, with a system audit trail.
        superseded = list(
            db.execute(
                text("""UPDATE anomaly_records ar SET status='DISMISSED',
              resolution_note=:note,resolved_at=now()
            FROM algorithm_runs old
            WHERE ar.algorithm_run_id=old.id AND old.assignment_id=:assignment
              AND old.panel_id=:panel AND old.algorithm_name=:algorithm
              AND old.input_hash=:hash AND old.status='COMPLETED'
              AND old.id<>:run AND ar.status='OPEN' AND ar.submission_id=ANY(:ids)
            RETURNING ar.id"""),
                {
                    "assignment": assignment_id,
                    "panel": panel_id,
                    "algorithm": ALGORITHM_NAME,
                    "hash": input_hash,
                    "run": run_id,
                    "ids": valid,
                    "note": f"已由算法 {ALGORITHM_VERSION} 运行 {run_id} 对同一评分快照重新检测，旧证据保留。",
                },
            ).scalars()
        )
        if superseded:
            db.execute(
                text("""INSERT INTO audit_logs(action,entity_type,entity_id,before_json,after_json)
                VALUES ('SUPERSEDE_ALGORITHM_FINDINGS','algorithm_run',:run,
                CAST(:before AS jsonb),CAST(:after AS jsonb))"""),
                {
                    "run": run_id,
                    "before": json.dumps({"open_anomaly_ids": superseded}),
                    "after": json.dumps(
                        {"replacement_run_id": run_id, "version": ALGORITHM_VERSION}
                    ),
                },
            )
        # Locked final reviews have already blocked reaggregation above.
        db.execute(
            text("""UPDATE submissions s SET final_review_status=CASE WHEN id=ANY(:high)
              OR EXISTS(SELECT 1 FROM anomaly_records ar WHERE ar.submission_id=s.id
                AND ar.status='OPEN' AND ar.risk_level='HIGH')
              THEN 'ESCALATED_FOR_TEACHER_FINAL_REVIEW' ELSE 'NORMAL' END,updated_at=now()
              WHERE id=ANY(:ids) AND final_review_status<>'FINAL_REVIEW_LOCKED'"""),
            {"ids": valid, "high": sorted(high)},
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
              AND ar.algorithm_name=:algorithm
              AND ag.created_at >= (SELECT max(GREATEST(rt.submitted_at,
                  (SELECT max(rev.created_at) FROM review_revisions rev WHERE rev.review_task_id=rt.id)))
                FROM review_tasks rt WHERE rt.submission_id=s.id AND rt.is_active)
        )"""),
        {"id": assignment_id, "algorithm": ALGORITHM_NAME},
    ).scalar_one()
    if not missing:
        db.execute(
            text("UPDATE assignments SET status='TEACHER_GRADING',updated_at=now() WHERE id=:id"),
            {"id": assignment_id},
        )
