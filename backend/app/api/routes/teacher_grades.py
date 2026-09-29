from __future__ import annotations

import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_teacher
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.teacher import (
    AnomalyResolutionInput,
    TeacherGradeCorrectionInput,
    TeacherGradeInput,
)
from app.services.teacher_grade_service import calculate_final_score, calculate_teacher_total

router = APIRouter()


def _load_and_validate_scores(
    db: Session, submission_id: int, payload: TeacherGradeInput
) -> tuple[dict, Decimal]:
    submission = (
        db.execute(
            text("""
        SELECT s.id, s.assignment_id FROM submissions s WHERE s.id = :id
    """),
            {"id": submission_id},
        )
        .mappings()
        .one_or_none()
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="SUBMISSION_NOT_FOUND")
    rubric_rows = (
        db.execute(
            text("""
        SELECT ri.id, ri.max_score FROM rubric_items ri JOIN rubrics r ON r.id = ri.rubric_id
        WHERE r.assignment_id = :assignment_id
    """),
            {"assignment_id": submission["assignment_id"]},
        )
        .mappings()
        .all()
    )
    limits = {row["id"]: Decimal(row["max_score"]) for row in rubric_rows}
    submitted = {item.rubric_item_id: item.score for item in payload.rubric_scores}
    if len(submitted) != len(payload.rubric_scores) or set(submitted) != set(limits):
        raise HTTPException(status_code=422, detail="ALL_RUBRIC_ITEMS_REQUIRED_ONCE")
    if any(score > limits[item_id] for item_id, score in submitted.items()):
        raise HTTPException(status_code=422, detail="RUBRIC_SCORE_OUT_OF_RANGE")
    return submission, calculate_teacher_total(list(submitted.values()))


@router.get("/assignments/{assignment_id}/grading", response_model=ApiResponse)
def grading_workspace(
    assignment_id: int, _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    assignment = (
        db.execute(
            text(
                "SELECT id, title, status, teacher_weight, designated_review_weight FROM assignments WHERE id = :id"
            ),
            {"id": assignment_id},
        )
        .mappings()
        .one_or_none()
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="ASSIGNMENT_NOT_FOUND")
    rubric = (
        db.execute(
            text("""
        SELECT ri.id, ri.name, ri.max_score, ri.sort_order, ri.description
        FROM rubric_items ri JOIN rubrics r ON r.id = ri.rubric_id
        WHERE r.assignment_id = :id ORDER BY ri.sort_order
    """),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    submissions = (
        db.execute(
            text("""
        SELECT s.id, s.anonymous_token, s.status, s.author_id, u.student_no, u.name AS author_name,
               c.name AS class_name,
               tg.id AS teacher_grade_id, tg.total_score AS teacher_score, tg.version AS teacher_grade_version,
               tg.locked_at, tg.feedback, tg.rubric_scores_json,
               agg.id AS aggregate_id, agg.total_score AS aggregate_score,
               count(DISTINCT ar.id) FILTER (WHERE ar.status = 'OPEN') AS open_anomaly_count,
               fg.final_score, fg.published_at
        FROM submissions s
        JOIN users u ON u.id = s.author_id JOIN classes c ON c.id = s.class_id
        LEFT JOIN LATERAL (
          SELECT * FROM teacher_grades WHERE submission_id = s.id ORDER BY version DESC LIMIT 1
        ) tg ON true
        LEFT JOIN LATERAL (
          SELECT * FROM designated_review_aggregates WHERE submission_id = s.id ORDER BY created_at DESC LIMIT 1
        ) agg ON true
        LEFT JOIN anomaly_records ar ON ar.submission_id = s.id
        LEFT JOIN final_grades fg ON fg.submission_id = s.id
        WHERE s.assignment_id = :id
        GROUP BY s.id, u.student_no, u.name, c.name, tg.id, tg.total_score, tg.version,
                 tg.locked_at, tg.feedback, tg.rubric_scores_json, agg.id, agg.total_score, fg.final_score, fg.published_at
        ORDER BY c.name, u.student_no
    """),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    return ApiResponse(
        data={
            "assignment": dict(assignment),
            "rubric_items": [dict(row) for row in rubric],
            "submissions": [dict(row) for row in submissions],
        }
    )


@router.post(
    "/submissions/{submission_id}/grades",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_teacher_grade(
    submission_id: int,
    payload: TeacherGradeInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ApiResponse:
    _, total = _load_and_validate_scores(db, submission_id, payload)
    exists = db.execute(
        text("SELECT id FROM teacher_grades WHERE submission_id = :id LIMIT 1"),
        {"id": submission_id},
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="GRADE_EXISTS_USE_CORRECTION")
    scores_json = {str(item.rubric_item_id): float(item.score) for item in payload.rubric_scores}
    grade_id = db.execute(
        text("""
        INSERT INTO teacher_grades(submission_id, rubric_scores_json, total_score, version, entered_by, feedback)
        VALUES (:submission_id, CAST(:scores AS jsonb), :total, 1, :entered_by, :feedback) RETURNING id
    """),
        {
            "submission_id": submission_id,
            "scores": json.dumps(scores_json),
            "total": total,
            "entered_by": teacher.id,
            "feedback": payload.comment,
        },
    ).scalar_one()
    db.commit()
    return ApiResponse(
        data={"teacher_grade_id": grade_id, "version": 1, "total_score": total, "locked": False}
    )


@router.post("/grades/{grade_id}/lock", response_model=ApiResponse)
def lock_teacher_grade(
    grade_id: int, teacher: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    grade = (
        db.execute(
            text(
                "SELECT id, submission_id, locked_at FROM teacher_grades WHERE id = :id FOR UPDATE"
            ),
            {"id": grade_id},
        )
        .mappings()
        .one_or_none()
    )
    if grade is None:
        raise HTTPException(status_code=404, detail="GRADE_NOT_FOUND")
    if grade["locked_at"] is not None:
        raise HTTPException(status_code=423, detail="GRADE_LOCKED")
    latest = db.execute(
        text(
            "SELECT id FROM teacher_grades WHERE submission_id = :id ORDER BY version DESC LIMIT 1"
        ),
        {"id": grade["submission_id"]},
    ).scalar_one()
    if latest != grade_id:
        raise HTTPException(status_code=409, detail="ONLY_LATEST_GRADE_CAN_BE_LOCKED")
    db.execute(text("UPDATE teacher_grades SET locked_at = now() WHERE id = :id"), {"id": grade_id})
    db.execute(
        text("""
        INSERT INTO audit_logs(actor_id, action, entity_type, entity_id, after_json)
        VALUES (:actor, 'LOCK_TEACHER_GRADE', 'teacher_grade', :grade_id,
                jsonb_build_object('locked', true))
    """),
        {"actor": teacher.id, "grade_id": grade_id},
    )
    db.commit()
    return ApiResponse(data={"teacher_grade_id": grade_id, "locked": True})


@router.post(
    "/submissions/{submission_id}/grade-corrections",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
)
def correct_teacher_grade(
    submission_id: int,
    payload: TeacherGradeCorrectionInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ApiResponse:
    _, total = _load_and_validate_scores(db, submission_id, payload)
    previous = (
        db.execute(
            text("""
        SELECT id, version, locked_at FROM teacher_grades
        WHERE submission_id = :id ORDER BY version DESC LIMIT 1 FOR UPDATE
    """),
            {"id": submission_id},
        )
        .mappings()
        .one_or_none()
    )
    if previous is None:
        raise HTTPException(status_code=409, detail="CREATE_INITIAL_GRADE_FIRST")
    if previous["locked_at"] is None:
        raise HTTPException(status_code=409, detail="LOCK_CURRENT_GRADE_BEFORE_CORRECTION")
    version = previous["version"] + 1
    scores_json = {str(item.rubric_item_id): float(item.score) for item in payload.rubric_scores}
    grade_id = db.execute(
        text("""
        INSERT INTO teacher_grades(
          submission_id, rubric_scores_json, total_score, version, entered_by, correction_reason, feedback
        ) VALUES (:submission_id, CAST(:scores AS jsonb), :total, :version, :entered_by, :reason, :feedback)
        RETURNING id
    """),
        {
            "submission_id": submission_id,
            "scores": json.dumps(scores_json),
            "total": total,
            "version": version,
            "entered_by": teacher.id,
            "reason": payload.reason,
            "feedback": payload.comment,
        },
    ).scalar_one()
    db.execute(
        text("""
        INSERT INTO audit_logs(actor_id, action, entity_type, entity_id, before_json, after_json)
        VALUES (:actor, 'CREATE_GRADE_CORRECTION', 'teacher_grade', :new_id,
                jsonb_build_object('previous_grade_id', CAST(:old_id AS bigint)),
                jsonb_build_object('reason', CAST(:reason AS text)))
    """),
        {
            "actor": teacher.id,
            "new_id": grade_id,
            "old_id": previous["id"],
            "reason": payload.reason,
        },
    )
    db.commit()
    return ApiResponse(
        data={
            "teacher_grade_id": grade_id,
            "version": version,
            "total_score": total,
            "locked": False,
        }
    )


@router.get("/assignments/{assignment_id}/anomalies", response_model=ApiResponse)
def list_anomalies(
    assignment_id: int, _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    rows = (
        db.execute(
            text("""
        SELECT ar.*, s.anonymous_token, u.name AS author_name, u.student_no
        FROM anomaly_records ar JOIN submissions s ON s.id = ar.submission_id
        JOIN users u ON u.id = s.author_id
        WHERE s.assignment_id = :id ORDER BY ar.status = 'OPEN' DESC, ar.risk_score DESC, ar.created_at DESC
    """),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    return ApiResponse(data=[dict(row) for row in rows])


@router.post("/anomalies/{anomaly_id}/resolve", response_model=ApiResponse)
def resolve_anomaly(
    anomaly_id: int,
    payload: AnomalyResolutionInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ApiResponse:
    updated = db.execute(
        text("""
        UPDATE anomaly_records SET status = :status, resolution_note = :note,
          resolved_by = :teacher_id, resolved_at = now()
        WHERE id = :id AND status = 'OPEN' RETURNING id
    """),
        {
            "status": payload.status,
            "note": payload.note,
            "teacher_id": teacher.id,
            "id": anomaly_id,
        },
    ).scalar_one_or_none()
    if updated is None:
        raise HTTPException(status_code=409, detail="ANOMALY_NOT_OPEN_OR_NOT_FOUND")
    db.commit()
    return ApiResponse(data={"anomaly_id": anomaly_id, "status": payload.status})


@router.post("/assignments/{assignment_id}/publish-results", response_model=ApiResponse)
def publish_results(
    assignment_id: int,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ApiResponse:
    assignment = (
        db.execute(
            text("""
        SELECT id, status, teacher_weight, designated_review_weight FROM assignments
        WHERE id = :id FOR UPDATE
    """),
            {"id": assignment_id},
        )
        .mappings()
        .one_or_none()
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="ASSIGNMENT_NOT_FOUND")
    if assignment["status"] not in {"TEACHER_GRADING", "AGGREGATING"}:
        raise HTTPException(status_code=400, detail="INVALID_STATE")
    open_anomalies = db.execute(
        text("""
        SELECT count(*) FROM anomaly_records ar JOIN submissions s ON s.id = ar.submission_id
        WHERE s.assignment_id = :id AND ar.status = 'OPEN'
    """),
        {"id": assignment_id},
    ).scalar_one()
    if open_anomalies:
        raise HTTPException(status_code=424, detail="OPEN_ANOMALIES_REQUIRE_REVIEW")
    submissions = (
        db.execute(
            text(
                "SELECT id FROM submissions WHERE assignment_id = :id AND status = 'VALID' ORDER BY id"
            ),
            {"id": assignment_id},
        )
        .scalars()
        .all()
    )
    published = 0
    for submission_id in submissions:
        grade = (
            db.execute(
                text("""
            SELECT id, total_score FROM teacher_grades WHERE submission_id = :id AND locked_at IS NOT NULL
            ORDER BY version DESC LIMIT 1
        """),
                {"id": submission_id},
            )
            .mappings()
            .one_or_none()
        )
        aggregate = (
            db.execute(
                text("""
            SELECT id, total_score FROM designated_review_aggregates WHERE submission_id = :id
            ORDER BY created_at DESC LIMIT 1
        """),
                {"id": submission_id},
            )
            .mappings()
            .one_or_none()
        )
        if grade is None or aggregate is None:
            raise HTTPException(
                status_code=424, detail={"code": "GRADE_NOT_READY", "submission_id": submission_id}
            )
        final_score = calculate_final_score(
            Decimal(grade["total_score"]),
            Decimal(aggregate["total_score"]),
            Decimal(assignment["teacher_weight"]),
            Decimal(assignment["designated_review_weight"]),
        )
        db.execute(
            text("""
            INSERT INTO final_grades(submission_id, teacher_grade_id, aggregate_id, final_score, published_by)
            VALUES (:submission_id, :teacher_grade_id, :aggregate_id, :final_score, :published_by)
            ON CONFLICT (submission_id) DO NOTHING
        """),
            {
                "submission_id": submission_id,
                "teacher_grade_id": grade["id"],
                "aggregate_id": aggregate["id"],
                "final_score": final_score,
                "published_by": teacher.id,
            },
        )
        published += 1
    db.execute(
        text(
            "UPDATE assignments SET status = 'PUBLISHED_RESULT', updated_at = now() WHERE id = :id"
        ),
        {"id": assignment_id},
    )
    db.commit()
    return ApiResponse(
        data={
            "assignment_id": assignment_id,
            "status": "PUBLISHED_RESULT",
            "published_count": published,
        }
    )
