"""Shared transaction boundaries and publication checks for teacher operations."""

import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.assignment_lifecycle import require_available, submission_intake_open


def audit(
    db: Session, actor: int, action: str, entity: str, entity_id: int, before=None, after=None
) -> None:
    db.execute(
        text("""
        INSERT INTO audit_logs(actor_id, action, entity_type, entity_id, before_json, after_json)
        VALUES (:actor, :action, :entity, :id, CAST(:before AS jsonb), CAST(:after AS jsonb))
    """),
        {
            "actor": actor,
            "action": action,
            "entity": entity,
            "id": entity_id,
            "before": json.dumps(before, default=str),
            "after": json.dumps(after, default=str),
        },
    )


def lock_assignment(db: Session, assignment_id: int, editable=True):
    row = (
        db.execute(
            text("SELECT * FROM assignments WHERE id = :id FOR UPDATE"), {"id": assignment_id}
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "ASSIGNMENT_NOT_FOUND")
    require_available(row, writable=True)
    if editable and row["status"] == "PUBLISHED_RESULT":
        raise HTTPException(409, "RESULTS_ALREADY_PUBLISHED")
    return row


def lock_submission(db: Session, submission_id: int):
    assignment_id = db.execute(
        text("SELECT assignment_id FROM submissions WHERE id = :id"), {"id": submission_id}
    ).scalar_one_or_none()
    if assignment_id is None:
        raise HTTPException(404, "SUBMISSION_NOT_FOUND")
    # All grade writes and publication acquire the same parent lock first.
    assignment = lock_assignment(db, assignment_id)
    if assignment["type"] != "FINAL_PROJECT":
        raise HTTPException(400, "REVIEWED_ASSIGNMENT_REQUIRED")
    if assignment["status"] not in {"REVIEWER_GRADING", "AGGREGATING", "TEACHER_GRADING"}:
        raise HTTPException(400, "INVALID_STATE")
    row = (
        db.execute(
            text("""
        SELECT s.*, mc.status AS material_status FROM submissions s
        LEFT JOIN material_checks mc ON mc.submission_id = s.id
        WHERE s.id = :id FOR UPDATE OF s
    """),
            {"id": submission_id},
        )
        .mappings()
        .one()
    )
    if not row["is_current"] or row["status"] != "VALID" or row["material_status"] != "VALID":
        raise HTTPException(422, "SUBMISSION_NOT_VALID")
    return row


def publication_readiness(db: Session, assignment_id: int):
    assignment = (
        db.execute(text("SELECT * FROM assignments WHERE id = :id"), {"id": assignment_id})
        .mappings()
        .one_or_none()
    )
    if assignment is None:
        raise HTTPException(404, "ASSIGNMENT_NOT_FOUND")
    if assignment["type"] != "FINAL_PROJECT":
        raise HTTPException(400, "REVIEWED_ASSIGNMENT_REQUIRED")
    rows = (
        db.execute(
            text("""
        SELECT s.id, u.name AS author_name, u.student_no, mc.status AS material_status,
               tg.id AS teacher_grade_id, tg.total_score AS teacher_score, tg.locked_at,
               ag.id AS aggregate_id, ag.total_score AS aggregate_score,
               ag.created_at AS aggregate_created_at,
               ag.algorithm_name, ag.low_evidence_policy,
               s.final_review_status, fr.id AS final_review_id, fr.final_score AS final_review_score,
               (SELECT count(*) FROM anomaly_records ar
                WHERE ar.submission_id = s.id AND ar.status = 'OPEN') AS open_anomalies,
               (SELECT count(DISTINCT rt.reviewer_id) FROM review_tasks rt WHERE rt.submission_id = s.id AND rt.is_active) AS task_count,
               (SELECT count(*) FROM review_tasks rt
                WHERE rt.submission_id = s.id AND rt.is_active AND rt.status = 'SUBMITTED') AS completed_tasks,
               (SELECT max(GREATEST(rt.submitted_at, (SELECT max(rev.created_at) FROM review_revisions rev
                    WHERE rev.review_task_id=rt.id))) FROM review_tasks rt
                WHERE rt.submission_id = s.id AND rt.is_active) AS last_review_at
        FROM submissions s JOIN users u ON u.id = s.author_id
        LEFT JOIN material_checks mc ON mc.submission_id = s.id
        LEFT JOIN LATERAL (
            SELECT * FROM teacher_grades WHERE submission_id = s.id ORDER BY version DESC LIMIT 1
        ) tg ON true
        LEFT JOIN LATERAL (
            SELECT a.*,run.algorithm_name,run.parameters_json->>'low_evidence_policy' AS low_evidence_policy FROM designated_review_aggregates a
            JOIN review_panels p ON p.id = a.panel_id
            JOIN algorithm_runs run ON run.id = a.algorithm_run_id
            WHERE a.submission_id = s.id AND p.assignment_id = s.assignment_id
              AND p.target_class_id = s.class_id AND run.assignment_id = s.assignment_id
              AND run.panel_id = p.id AND run.status = 'COMPLETED'
            ORDER BY a.created_at DESC, a.id DESC LIMIT 1
        ) ag ON true
        LEFT JOIN teacher_final_reviews fr ON fr.submission_id=s.id
        WHERE s.assignment_id = :id AND s.is_current AND s.status = 'VALID' ORDER BY s.id
    """),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    blockers = []
    if assignment["closed_at"] is not None:
        blockers.append({"code": "ASSIGNMENT_CLOSED"})
    if submission_intake_open(assignment):
        blockers.append({"code": "SUBMISSIONS_STILL_OPEN"})
    if assignment["status"] != "TEACHER_GRADING":
        blockers.append({"code": "INVALID_STATE"})
    weights = (assignment["teacher_weight"], assignment["designated_review_weight"])
    if not all(
        weight.is_finite() and Decimal(0) <= weight <= Decimal(1) for weight in weights
    ) or sum(weights) != Decimal(1):
        blockers.append({"code": "INVALID_GRADING_WEIGHTS"})
    if not rows:
        blockers.append({"code": "NO_VALID_SUBMISSIONS"})
    maximum = db.execute(
        text("""
        SELECT COALESCE(sum(ri.max_score), 0) FROM rubric_items ri
        JOIN rubrics r ON r.id = ri.rubric_id WHERE r.assignment_id = :id
    """),
        {"id": assignment_id},
    ).scalar_one()
    all_open = db.execute(
        text("""
        SELECT count(*) FROM anomaly_records ar JOIN submissions s ON s.id = ar.submission_id
        WHERE s.assignment_id = :id AND ar.status = 'OPEN'
    """),
        {"id": assignment_id},
    ).scalar_one()
    if all_open:
        blockers.append({"code": "OPEN_ANOMALIES_REQUIRE_REVIEW", "count": all_open})
    for row in rows:
        reasons = []
        if row["algorithm_name"] == "panel_bayesian_robust" and row["low_evidence_policy"] != "2":
            reasons.append("LOW_EVIDENCE_REFRESH_REQUIRED")
        if row["material_status"] != "VALID":
            reasons.append("MATERIAL_NOT_VALID")
        if row["teacher_grade_id"] is None or row["locked_at"] is None:
            reasons.append("LATEST_GRADE_NOT_LOCKED")
        elif (
            not row["teacher_score"].is_finite()
            or not Decimal(0) <= row["teacher_score"] <= maximum
        ):
            reasons.append("TEACHER_SCORE_OUT_OF_RANGE")
        if row["aggregate_id"] is None:
            reasons.append("AGGREGATE_NOT_READY")
        elif (
            not row["aggregate_score"].is_finite()
            or not Decimal(0) <= row["aggregate_score"] <= maximum
        ):
            reasons.append("AGGREGATE_OUT_OF_RANGE")
        elif row["last_review_at"] and row["last_review_at"] > row["aggregate_created_at"]:
            reasons.append("AGGREGATE_STALE")
        if row["task_count"] != 5 or row["completed_tasks"] != 5:
            reasons.append("REVIEWS_INCOMPLETE")
        if (
            row["final_review_status"] == "ESCALATED_FOR_TEACHER_FINAL_REVIEW"
            or row["final_review_id"] is None
            and row["final_review_status"] == "FINAL_REVIEW_LOCKED"
        ):
            reasons.append("TEACHER_FINAL_REVIEW_REQUIRED")
        for code in reasons:
            blockers.append(
                {
                    "code": code,
                    "submission_id": row["id"],
                    "author_name": row["author_name"],
                    "student_no": row["student_no"],
                }
            )
    return {"ready": not blockers, "submission_count": len(rows), "blockers": blockers}, rows
