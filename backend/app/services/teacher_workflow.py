"""Shared transaction boundaries and publication checks for teacher operations."""

import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


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
    if row["status"] != "VALID" or row["material_status"] != "VALID":
        raise HTTPException(422, "SUBMISSION_NOT_VALID")
    return row


def validate_saved_panels(db: Session, assignment_id: int):
    from pydantic import ValidationError

    from app.schemas.teacher import ReviewPanelsInput

    class_ids = set(
        db.execute(
            text("""
        SELECT c.id FROM classes c JOIN assignment_classes ac ON ac.class_id = c.id
        WHERE ac.assignment_id = :id ORDER BY c.id FOR SHARE OF c
    """),
            {"id": assignment_id},
        ).scalars()
    )
    panels = (
        db.execute(
            text("""
        SELECT p.*, COALESCE(array_agg(pr.reviewer_id ORDER BY pr.reviewer_id)
            FILTER (WHERE pr.reviewer_id IS NOT NULL), '{}') AS reviewer_ids
        FROM review_panels p LEFT JOIN panel_reviewers pr ON pr.panel_id = p.id
        WHERE p.assignment_id = :id GROUP BY p.id ORDER BY p.id
    """),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    try:
        config = ReviewPanelsInput(panels=[dict(p) for p in panels])
    except ValidationError as exc:
        raise HTTPException(424, "PANEL_NOT_READY") from exc
    if {p.target_class_id for p in config.panels} != class_ids:
        raise HTTPException(424, "PANEL_CLASSES_MUST_MATCH_ASSIGNMENT")
    for panel in config.panels:
        valid = set(
            db.execute(
                text("""
            SELECT e.user_id FROM enrollments e JOIN users u ON u.id = e.user_id
            WHERE e.class_id = :class AND e.user_id = ANY(:ids) AND u.system_role = 'STUDENT'
              AND NOT EXISTS (SELECT 1 FROM enrollments other
                              WHERE other.user_id = e.user_id AND other.class_id = :target)
        """),
                {
                    "class": panel.reviewer_class_id,
                    "target": panel.target_class_id,
                    "ids": panel.reviewer_ids,
                },
            ).scalars()
        )
        if valid != set(panel.reviewer_ids):
            raise HTTPException(424, "REVIEWER_CLASS_CONFLICT")
    return panels


def publication_readiness(db: Session, assignment_id: int):
    assignment = (
        db.execute(text("SELECT * FROM assignments WHERE id = :id"), {"id": assignment_id})
        .mappings()
        .one_or_none()
    )
    if assignment is None:
        raise HTTPException(404, "ASSIGNMENT_NOT_FOUND")
    rows = (
        db.execute(
            text("""
        SELECT s.id, u.name AS author_name, u.student_no, mc.status AS material_status,
               tg.id AS teacher_grade_id, tg.total_score AS teacher_score, tg.locked_at,
               ag.id AS aggregate_id, ag.total_score AS aggregate_score,
               ag.created_at AS aggregate_created_at,
               s.final_review_status, fr.id AS final_review_id, fr.final_score AS final_review_score,
               (SELECT count(*) FROM anomaly_records ar
                WHERE ar.submission_id = s.id AND ar.status = 'OPEN') AS open_anomalies,
               (SELECT count(*) FROM review_tasks rt WHERE rt.submission_id = s.id) AS task_count,
               (SELECT count(*) FROM review_tasks rt
                WHERE rt.submission_id = s.id AND rt.status = 'SUBMITTED') AS completed_tasks,
               (SELECT max(rt.submitted_at) FROM review_tasks rt
                WHERE rt.submission_id = s.id) AS last_review_at
        FROM submissions s JOIN users u ON u.id = s.author_id
        LEFT JOIN material_checks mc ON mc.submission_id = s.id
        LEFT JOIN LATERAL (
            SELECT * FROM teacher_grades WHERE submission_id = s.id ORDER BY version DESC LIMIT 1
        ) tg ON true
        LEFT JOIN LATERAL (
            SELECT a.* FROM designated_review_aggregates a
            JOIN review_panels p ON p.id = a.panel_id
            JOIN algorithm_runs run ON run.id = a.algorithm_run_id
            WHERE a.submission_id = s.id AND p.assignment_id = s.assignment_id
              AND p.target_class_id = s.class_id AND run.assignment_id = s.assignment_id
              AND run.panel_id = p.id AND run.status = 'COMPLETED'
            ORDER BY a.created_at DESC, a.id DESC LIMIT 1
        ) ag ON true
        LEFT JOIN teacher_final_reviews fr ON fr.submission_id=s.id
        WHERE s.assignment_id = :id AND s.status = 'VALID' ORDER BY s.id
    """),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    blockers = []
    if assignment["status"] != "TEACHER_GRADING":
        blockers.append({"code": "INVALID_STATE"})
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
        if row["final_review_status"] == "ESCALATED_FOR_TEACHER_FINAL_REVIEW" or row["final_review_id"] is None and row["final_review_status"] == "FINAL_REVIEW_LOCKED":
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
