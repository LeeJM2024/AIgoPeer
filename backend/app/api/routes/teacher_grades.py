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
    TeacherFinalReviewInput,
    TeacherGradeCorrectionInput,
    TeacherGradeInput,
)
from app.services.teacher_grade_service import calculate_final_score, calculate_teacher_total
from app.services.teacher_workflow import (
    audit,
    lock_assignment,
    lock_submission,
    publication_readiness,
)

router = APIRouter()


def _load_and_validate_scores(
    db: Session, submission_id: int, payload: TeacherGradeInput
) -> tuple[dict, Decimal]:
    submission = lock_submission(db, submission_id)
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
    if not limits or len(submitted) != len(payload.rubric_scores) or set(submitted) != set(limits):
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
               c.name AS class_name, mc.status AS material_status, mc.missing_items,
               tg.id AS teacher_grade_id, tg.total_score AS teacher_score, tg.version AS teacher_grade_version,
               tg.locked_at, tg.feedback, tg.rubric_scores_json,
               agg.id AS aggregate_id, agg.total_score AS aggregate_score,
               s.final_review_status, fr.id AS final_review_id, fr.final_score AS final_review_score,
               count(DISTINCT ar.id) FILTER (WHERE ar.status = 'OPEN') AS open_anomaly_count,
               fg.final_score, fg.published_at
        FROM submissions s
        JOIN users u ON u.id = s.author_id JOIN classes c ON c.id = s.class_id
        LEFT JOIN material_checks mc ON mc.submission_id = s.id
        LEFT JOIN LATERAL (
          SELECT * FROM teacher_grades WHERE submission_id = s.id ORDER BY version DESC LIMIT 1
        ) tg ON true
        LEFT JOIN LATERAL (
          SELECT ag.* FROM designated_review_aggregates ag
          JOIN review_panels p ON p.id=ag.panel_id JOIN algorithm_runs run ON run.id=ag.algorithm_run_id
          WHERE ag.submission_id=s.id AND p.assignment_id=s.assignment_id
            AND p.target_class_id=s.class_id AND run.assignment_id=s.assignment_id
            AND run.panel_id=p.id AND run.status='COMPLETED'
          ORDER BY ag.created_at DESC,ag.id DESC LIMIT 1
        ) agg ON true
        LEFT JOIN anomaly_records ar ON ar.submission_id = s.id
        LEFT JOIN teacher_final_reviews fr ON fr.submission_id = s.id
        LEFT JOIN final_grades fg ON fg.submission_id = s.id
        WHERE s.assignment_id = :id AND s.is_current
        GROUP BY s.id, u.student_no, u.name, c.name, mc.status, mc.missing_items, tg.id, tg.total_score, tg.version,
                 tg.locked_at, tg.feedback, tg.rubric_scores_json, agg.id, agg.total_score, s.final_review_status, fr.id, fr.final_score, fg.final_score, fg.published_at
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
    audit(
        db,
        teacher.id,
        "CREATE_TEACHER_GRADE",
        "teacher_grade",
        grade_id,
        after={"submission_id": submission_id, "version": 1},
    )
    db.commit()
    return ApiResponse(
        data={"teacher_grade_id": grade_id, "version": 1, "total_score": total, "locked": False}
    )


@router.post("/grades/{grade_id}/lock", response_model=ApiResponse)
def lock_teacher_grade(
    grade_id: int, teacher: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    submission_id = db.execute(
        text("SELECT submission_id FROM teacher_grades WHERE id = :id"), {"id": grade_id}
    ).scalar_one_or_none()
    if submission_id is None:
        raise HTTPException(404, "GRADE_NOT_FOUND")
    lock_submission(db, submission_id)
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
    latest = db.execute(
        text(
            "SELECT id FROM teacher_grades WHERE submission_id = :id ORDER BY version DESC LIMIT 1"
        ),
        {"id": grade["submission_id"]},
    ).scalar_one()
    if latest != grade_id:
        raise HTTPException(status_code=409, detail="ONLY_LATEST_GRADE_CAN_BE_LOCKED")
    if grade["locked_at"] is not None:
        return ApiResponse(data={"teacher_grade_id": grade_id, "locked": True})
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
    if previous["version"] != payload.expected_version:
        raise HTTPException(409, "GRADE_VERSION_CONFLICT")
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
    if not db.execute(
        text("SELECT id FROM assignments WHERE id = :id"), {"id": assignment_id}
    ).scalar_one_or_none():
        raise HTTPException(404, "ASSIGNMENT_NOT_FOUND")
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
    assignment_id = db.execute(
        text("""
        SELECT s.assignment_id FROM anomaly_records ar JOIN submissions s ON s.id = ar.submission_id
        WHERE ar.id = :id
    """),
        {"id": anomaly_id},
    ).scalar_one_or_none()
    if assignment_id is None:
        raise HTTPException(404, "ANOMALY_NOT_FOUND")
    if db.execute(text("SELECT risk_level FROM anomaly_records WHERE id=:id"), {"id": anomaly_id}).scalar_one() == "HIGH":
        raise HTTPException(409, "HIGH_RISK_REQUIRES_FINAL_REVIEW")
    lock_assignment(db, assignment_id)
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
    audit(
        db,
        teacher.id,
        "RESOLVE_ANOMALY",
        "anomaly",
        anomaly_id,
        before={"status": "OPEN"},
        after=payload.model_dump(),
    )
    db.commit()
    return ApiResponse(data={"anomaly_id": anomaly_id, "status": payload.status})


@router.post("/submissions/{submission_id}/final-review", response_model=ApiResponse, status_code=201)
def create_teacher_final_review(
    submission_id: int, payload: TeacherFinalReviewInput,
    teacher: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    submission = lock_submission(db, submission_id)
    assignment = lock_assignment(db, submission["assignment_id"])
    if assignment["status"] != "TEACHER_GRADING":
        raise HTTPException(409, "FINAL_REVIEW_NOT_READY")
    existing = db.execute(text("SELECT * FROM teacher_final_reviews WHERE submission_id=:id"), {"id": submission_id}).mappings().one_or_none()
    if existing:
        if existing["final_score"] == payload.final_score and existing["reason"] == payload.reason and existing["entered_by"] == teacher.id:
            return ApiResponse(data={"teacher_final_review_id": existing["id"], "final_score": existing["final_score"], "locked": True})
        raise HTTPException(409, "FINAL_REVIEW_ALREADY_LOCKED")
    if submission["final_review_status"] != "ESCALATED_FOR_TEACHER_FINAL_REVIEW":
        raise HTTPException(409, "HIGH_RISK_REVIEW_NOT_FOUND")
    maximum = db.execute(text("""SELECT COALESCE(sum(ri.max_score),0) FROM rubric_items ri
        JOIN rubrics r ON r.id=ri.rubric_id WHERE r.assignment_id=:id"""), {"id": submission["assignment_id"]}).scalar_one()
    if payload.final_score > maximum:
        raise HTTPException(422, "FINAL_REVIEW_SCORE_OUT_OF_RANGE")
    run_id = db.execute(text("""SELECT ar.algorithm_run_id FROM anomaly_records ar
        WHERE ar.submission_id=:id AND ar.risk_level='HIGH' ORDER BY ar.created_at DESC LIMIT 1"""), {"id":submission_id}).scalar_one_or_none()
    if run_id is None:
        raise HTTPException(409, "HIGH_RISK_REVIEW_NOT_FOUND")
    review_id = db.execute(text("""INSERT INTO teacher_final_reviews(submission_id,algorithm_run_id,final_score,reason,entered_by)
        VALUES(:submission,:run,:score,:reason,:teacher) RETURNING id"""), {"submission":submission_id,"run":run_id,"score":payload.final_score,"reason":payload.reason,"teacher":teacher.id}).scalar_one()
    db.execute(text("UPDATE submissions SET final_review_status='FINAL_REVIEW_LOCKED',updated_at=now() WHERE id=:id"), {"id":submission_id})
    db.execute(text("""UPDATE anomaly_records SET status='CONFIRMED',resolution_note='已由教师复核最终分处理',resolved_by=:teacher,resolved_at=now()
        WHERE submission_id=:submission AND risk_level='HIGH' AND status='OPEN'"""), {"teacher":teacher.id,"submission":submission_id})
    audit(db, teacher.id, "CREATE_TEACHER_FINAL_REVIEW", "teacher_final_review", review_id, after={"submission_id":submission_id,"final_score":str(payload.final_score),"reason":payload.reason})
    db.commit()
    return ApiResponse(data={"teacher_final_review_id":review_id,"final_score":payload.final_score.quantize(Decimal('0.01')),"locked":True})


@router.get("/assignments/{assignment_id}/publication-readiness", response_model=ApiResponse)
def get_publication_readiness(
    assignment_id: int, _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    readiness, _rows = publication_readiness(db, assignment_id)
    return ApiResponse(data=readiness)


@router.get("/submissions/{submission_id}/grade-history", response_model=ApiResponse)
def grade_history(
    submission_id: int, _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    if (
        db.execute(
            text("SELECT id FROM submissions WHERE id = :id"), {"id": submission_id}
        ).scalar_one_or_none()
        is None
    ):
        raise HTTPException(404, "SUBMISSION_NOT_FOUND")
    rows = (
        db.execute(
            text("""
        SELECT tg.*, u.name AS entered_by_name FROM teacher_grades tg
        JOIN users u ON u.id = tg.entered_by WHERE submission_id = :id ORDER BY version DESC
    """),
            {"id": submission_id},
        )
        .mappings()
        .all()
    )
    return ApiResponse(data=[dict(row) for row in rows])


@router.post("/assignments/{assignment_id}/publish-results", response_model=ApiResponse)
def publish_results(
    assignment_id: int,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ApiResponse:
    assignment = lock_assignment(db, assignment_id, editable=False)
    if assignment["status"] == "PUBLISHED_RESULT":
        count = db.execute(
            text("""
            SELECT count(*) FROM final_grades f JOIN submissions s ON s.id = f.submission_id
            WHERE s.assignment_id = :id
        """),
            {"id": assignment_id},
        ).scalar_one()
        return ApiResponse(
            data={
                "assignment_id": assignment_id,
                "status": "PUBLISHED_RESULT",
                "published_count": count,
            }
        )
    readiness, rows = publication_readiness(db, assignment_id)
    if not readiness["ready"]:
        raise HTTPException(424, {"code": "PUBLICATION_BLOCKED", **readiness})
    for row in rows:
        final_review = row["final_review_status"] == "FINAL_REVIEW_LOCKED"
        final_score = row["final_review_score"] if final_review else calculate_final_score(
            row["teacher_score"], row["aggregate_score"], assignment["teacher_weight"], assignment["designated_review_weight"])
        db.execute(
            text("""
            INSERT INTO final_grades(submission_id, teacher_grade_id, aggregate_id, teacher_final_review_id, final_grade_source,
                                      final_score, published_by, teacher_weight, designated_review_weight)
            VALUES (:submission, :grade, :aggregate, :final_review, :source, :score, :teacher, :tw, :rw)
        """),
            {
                "submission": row["id"],
                "grade": row["teacher_grade_id"],
                "aggregate": row["aggregate_id"],
                "score": final_score,
                "source": "TEACHER_FINAL_REVIEW" if final_review else "NORMAL_BLEND",
                "final_review": row["final_review_id"] if final_review else None,
                "teacher": teacher.id,
                "tw": assignment["teacher_weight"],
                "rw": assignment["designated_review_weight"],
            },
        )
    db.execute(
        text(
            "UPDATE assignments SET status = 'PUBLISHED_RESULT', updated_at = now() WHERE id = :id"
        ),
        {"id": assignment_id},
    )
    audit(
        db,
        teacher.id,
        "PUBLISH_RESULTS",
        "assignment",
        assignment_id,
        after={
            "count": len(rows),
            "teacher_weight": assignment["teacher_weight"],
            "designated_review_weight": assignment["designated_review_weight"],
        },
    )
    db.commit()
    return ApiResponse(
        data={
            "assignment_id": assignment_id,
            "status": "PUBLISHED_RESULT",
            "published_count": len(rows),
        }
    )
