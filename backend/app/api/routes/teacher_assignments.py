from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import CurrentUser, require_teacher
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.teacher import (
    AssignmentCreate,
    DraftAssignmentUpdate,
    ReviewDeadlineInput,
    ReviewPanelsInput,
)
from app.services.teacher_programming import get_programming_problem, save_programming_problem
from app.services.teacher_workflow import audit, lock_assignment, validate_saved_panels
from app.services.video_ai_provider import get_video_provider_status

router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ASSIGNMENT_NOT_FOUND")


@router.get("/dashboard", response_model=ApiResponse)
def dashboard(
    _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    counts = (
        db.execute(
            text("""
        SELECT
          count(*) FILTER (WHERE status <> 'PUBLISHED_RESULT') AS active_assignments,
          count(*) FILTER (WHERE status = 'TEACHER_GRADING') AS awaiting_grading,
          count(*) FILTER (WHERE status = 'PUBLISHED_RESULT') AS published_assignments
        FROM assignments
    """)
        )
        .mappings()
        .one()
    )
    progress = (
        db.execute(
            text("""
        SELECT
          count(*) AS task_count,
          count(*) FILTER (WHERE status = 'SUBMITTED') AS completed_tasks,
          count(*) FILTER (WHERE status = 'PENDING') AS pending_tasks
        FROM review_tasks
    """)
        )
        .mappings()
        .one()
    )
    anomalies = db.execute(
        text("SELECT count(*) FROM anomaly_records WHERE status = 'OPEN'")
    ).scalar_one()
    return ApiResponse(data={**dict(counts), **dict(progress), "open_anomalies": anomalies})


@router.get("/classes", response_model=ApiResponse)
def list_classes(
    _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    rows = (
        db.execute(
            text("""
        SELECT c.id, c.name, c.course_term,
               count(e.user_id) FILTER (WHERE u.system_role = 'STUDENT') AS student_count
        FROM classes c
        LEFT JOIN enrollments e ON e.class_id = c.id
        LEFT JOIN users u ON u.id = e.user_id
        GROUP BY c.id ORDER BY c.course_term DESC, c.name
    """)
        )
        .mappings()
        .all()
    )
    return ApiResponse(data=[dict(row) for row in rows])


@router.get("/classes/{class_id}/students", response_model=ApiResponse)
def list_class_students(
    class_id: int, _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    rows = (
        db.execute(
            text("""
        SELECT u.id, u.student_no, u.name
        FROM users u JOIN enrollments e ON e.user_id = u.id
        WHERE e.class_id = :class_id AND u.system_role = 'STUDENT'
        ORDER BY u.student_no, u.id
    """),
            {"class_id": class_id},
        )
        .mappings()
        .all()
    )
    return ApiResponse(data=[dict(row) for row in rows])


@router.get("/assignments", response_model=ApiResponse)
def list_assignments(
    _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    rows = (
        db.execute(
            text("""
        SELECT a.id, a.title, a.type, a.status, a.submit_deadline, a.review_deadline,
               a.teacher_weight, a.designated_review_weight,
               CASE WHEN a.type='PROGRAMMING' THEN
                 (SELECT count(*) FROM code_submissions cs WHERE cs.assignment_id=a.id AND cs.is_current)
                 ELSE (SELECT count(*) FROM submissions s WHERE s.assignment_id=a.id AND s.is_current)
               END AS submission_count,
               (SELECT count(*) FROM review_tasks rt JOIN review_panels p ON p.id=rt.panel_id
                 WHERE p.assignment_id=a.id) AS review_task_count
        FROM assignments a
        ORDER BY a.created_at DESC
    """)
        )
        .mappings()
        .all()
    )
    return ApiResponse(data=[dict(row) for row in rows])


@router.post("/assignments", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ApiResponse:
    existing_classes = set(
        db.execute(
            text("SELECT id FROM classes WHERE id = ANY(:ids)"), {"ids": payload.class_ids}
        ).scalars()
    )
    if existing_classes != set(payload.class_ids):
        raise HTTPException(status_code=422, detail="CLASS_NOT_FOUND")
    try:
        assignment_id = db.execute(
            text("""
            INSERT INTO assignments(
              title, type, status, submit_deadline, review_deadline,
              teacher_weight, designated_review_weight, created_by
            ) VALUES (:title, :type, 'DRAFT', :submit_deadline, :review_deadline,
                      :teacher_weight, :review_weight, :created_by)
            RETURNING id
        """),
            {
                "title": payload.title,
                "type": payload.type,
                "submit_deadline": payload.submit_deadline,
                "review_deadline": payload.review_deadline,
                "teacher_weight": payload.teacher_weight,
                "review_weight": payload.designated_review_weight,
                "created_by": teacher.id,
            },
        ).scalar_one()
        for class_id in payload.class_ids:
            db.execute(
                text("INSERT INTO assignment_classes(assignment_id, class_id) VALUES (:a, :c)"),
                {"a": assignment_id, "c": class_id},
            )
        rubric_id = db.execute(
            text("""
            INSERT INTO rubrics(assignment_id, name, total_score)
            VALUES (:assignment_id, '课程评分量表', :total_score) RETURNING id
        """),
            {
                "assignment_id": assignment_id,
                "total_score": sum(item.max_score for item in payload.rubric_items),
            },
        ).scalar_one()
        for item in payload.rubric_items:
            db.execute(
                text("""
                INSERT INTO rubric_items(rubric_id, name, max_score, sort_order, description)
                VALUES (:rubric_id, :name, :max_score, :sort_order, :description)
            """),
                {"rubric_id": rubric_id, **item.model_dump()},
            )
        save_programming_problem(db, assignment_id, payload.programming_problem)
        audit(
            db,
            teacher.id,
            "CREATE_ASSIGNMENT",
            "assignment",
            assignment_id,
            after=payload.model_dump(),
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="ASSIGNMENT_CONFLICT") from exc
    return ApiResponse(data={"assignment_id": assignment_id, "status": "DRAFT"})


@router.get("/assignments/{assignment_id}", response_model=ApiResponse)
def get_assignment(
    assignment_id: int, _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
) -> ApiResponse:
    assignment = (
        db.execute(text("SELECT * FROM assignments WHERE id = :id"), {"id": assignment_id})
        .mappings()
        .one_or_none()
    )
    if assignment is None:
        raise _not_found()
    classes = (
        db.execute(
            text("""
        SELECT c.id, c.name, c.course_term FROM classes c
        JOIN assignment_classes ac ON ac.class_id = c.id WHERE ac.assignment_id = :id ORDER BY c.id
    """),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
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
    panels = (
        db.execute(
            text("""
        SELECT p.id, p.target_class_id, p.reviewer_class_id, p.status,
               COALESCE(array_agg(pr.reviewer_id ORDER BY pr.reviewer_id)
                 FILTER (WHERE pr.reviewer_id IS NOT NULL), '{}') AS reviewer_ids
        FROM review_panels p LEFT JOIN panel_reviewers pr ON pr.panel_id = p.id
        WHERE p.assignment_id = :id GROUP BY p.id ORDER BY p.target_class_id
    """),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    return ApiResponse(
        data={
            **dict(assignment),
            "classes": [dict(row) for row in classes],
            "rubric_items": [dict(row) for row in rubric],
            "panels": [dict(row) for row in panels],
            "programming_problem": get_programming_problem(db, assignment_id),
        }
    )


@router.put("/assignments/{assignment_id}/review-panels", response_model=ApiResponse)
def configure_panels(
    assignment_id: int,
    payload: ReviewPanelsInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ApiResponse:
    assignment = (
        db.execute(
            text("SELECT status,type FROM assignments WHERE id = :id FOR UPDATE"), {"id": assignment_id}
        )
        .mappings()
        .one_or_none()
    )
    if assignment is None:
        raise _not_found()
    if assignment["status"] != "DRAFT":
        raise HTTPException(status_code=400, detail="PANELS_ONLY_EDITABLE_IN_DRAFT")
    if assignment["type"] != "FINAL_PROJECT":
        raise HTTPException(status_code=400, detail="INVALID_STATE")
    class_ids = set(
        db.execute(
            text("SELECT class_id FROM assignment_classes WHERE assignment_id = :id"),
            {"id": assignment_id},
        ).scalars()
    )
    if {payload.panels[0].target_class_id, payload.panels[0].reviewer_class_id} != class_ids:
        raise HTTPException(status_code=422, detail="PANEL_CLASSES_MUST_MATCH_ASSIGNMENT")
    for panel in payload.panels:
        db.execute(
            text("SELECT id FROM classes WHERE id = ANY(:ids) ORDER BY id FOR SHARE"),
            {"ids": sorted(class_ids)},
        ).all()
        enrolled = set(
            db.execute(
                text("""
            SELECT e.user_id FROM enrollments e JOIN users u ON u.id = e.user_id
            WHERE e.class_id = :class_id AND e.user_id = ANY(:reviewer_ids) AND u.system_role = 'STUDENT'
              AND NOT EXISTS (SELECT 1 FROM enrollments other
                              WHERE other.user_id = e.user_id AND other.class_id = :target)
        """),
                {
                    "class_id": panel.reviewer_class_id,
                    "reviewer_ids": panel.reviewer_ids,
                    "target": panel.target_class_id,
                },
            ).scalars()
        )
        if enrolled != set(panel.reviewer_ids):
            raise HTTPException(status_code=422, detail="REVIEWER_NOT_IN_REVIEWER_CLASS")
    db.execute(text("DELETE FROM review_panels WHERE assignment_id = :id"), {"id": assignment_id})
    panel_ids = []
    for panel in payload.panels:
        panel_id = db.execute(
            text("""
            INSERT INTO review_panels(assignment_id, target_class_id, reviewer_class_id, status)
            VALUES (:assignment_id, :target_class_id, :reviewer_class_id, 'DRAFT') RETURNING id
        """),
            {"assignment_id": assignment_id, **panel.model_dump(exclude={"reviewer_ids"})},
        ).scalar_one()
        for reviewer_id in panel.reviewer_ids:
            db.execute(
                text(
                    "INSERT INTO panel_reviewers(panel_id, reviewer_id) VALUES (:panel_id, :reviewer_id)"
                ),
                {"panel_id": panel_id, "reviewer_id": reviewer_id},
            )
        panel_ids.append(panel_id)
    audit(
        db, teacher.id, "CONFIGURE_PANELS", "assignment", assignment_id, after=payload.model_dump()
    )
    db.commit()
    return ApiResponse(data={"panel_ids": panel_ids})


@router.post("/assignments/{assignment_id}/publish", response_model=ApiResponse)
def publish_assignment(
    assignment_id: int,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ApiResponse:
    row = (
        db.execute(
            text("SELECT status, type FROM assignments WHERE id = :id FOR UPDATE"), {"id": assignment_id}
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise _not_found()
    if row["status"] != "DRAFT":
        raise HTTPException(status_code=400, detail="ASSIGNMENT_NOT_DRAFT")
    if row["type"] == "PROGRAMMING":
        from pydantic import ValidationError

        from app.schemas.teacher import ProgrammingProblemInput

        try:
            ProgrammingProblemInput.model_validate(get_programming_problem(db, assignment_id))
        except ValidationError as exc:
            raise HTTPException(424, "PROGRAMMING_PROBLEM_NOT_READY") from exc
        db.execute(text("UPDATE assignments SET status='PUBLISHED',updated_at=now() WHERE id=:id"), {"id": assignment_id})
        audit(db, teacher.id, "PUBLISH_ASSIGNMENT", "assignment", assignment_id)
        db.commit()
        return ApiResponse(data={"assignment_id": assignment_id, "status": "PUBLISHED"})
    validate_saved_panels(db, assignment_id)
    panel_counts = (
        db.execute(
            text("""
        SELECT p.id, count(pr.id) AS reviewer_count FROM review_panels p
        LEFT JOIN panel_reviewers pr ON pr.panel_id = p.id
        WHERE p.assignment_id = :id GROUP BY p.id
    """),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    if len(panel_counts) != 2 or any(row["reviewer_count"] != 5 for row in panel_counts):
        raise HTTPException(status_code=424, detail="PANEL_NOT_READY")
    db.execute(
        text(
            "UPDATE review_panels SET status = 'ACTIVE', updated_at = now() WHERE assignment_id = :id"
        ),
        {"id": assignment_id},
    )
    db.execute(
        text("UPDATE assignments SET status = 'PUBLISHED', updated_at = now() WHERE id = :id"),
        {"id": assignment_id},
    )
    audit(db, teacher.id, "PUBLISH_ASSIGNMENT", "assignment", assignment_id)
    db.commit()
    return ApiResponse(data={"assignment_id": assignment_id, "status": "PUBLISHED"})


@router.post("/assignments/{assignment_id}/initialize-review-tasks", response_model=ApiResponse)
def initialize_review_tasks(
    assignment_id: int,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> ApiResponse:
    assignment = (
        db.execute(
            text("""
        SELECT status, type, submit_deadline FROM assignments WHERE id = :id FOR UPDATE
    """),
            {"id": assignment_id},
        )
        .mappings()
        .one_or_none()
    )
    if assignment is None:
        raise _not_found()
    if assignment["type"] != "FINAL_PROJECT":
        raise HTTPException(400, "FINAL_PROJECT_REQUIRED")
    if assignment["status"] not in {"PUBLISHED", "SUBMITTING", "REVIEWER_INITIALIZING"}:
        raise HTTPException(status_code=400, detail="INVALID_STATE")
    if assignment["submit_deadline"] and assignment["submit_deadline"] > datetime.now(UTC):
        raise HTTPException(status_code=400, detail="SUBMISSION_DEADLINE_NOT_REACHED")
    pending_checks = db.execute(
        text("""
        SELECT count(*) FROM submissions s LEFT JOIN material_checks mc ON mc.submission_id = s.id
        WHERE s.assignment_id = :id AND s.is_current AND s.status <> 'DRAFT'
          AND (mc.status = 'PENDING' OR mc.id IS NULL)
    """),
        {"id": assignment_id},
    ).scalar_one()
    if pending_checks:
        raise HTTPException(status_code=424, detail="MATERIAL_CHECKS_PENDING")
    validate_saved_panels(db, assignment_id)
    panels = (
        db.execute(
            text(
                "SELECT id, target_class_id FROM review_panels WHERE assignment_id = :id AND status = 'ACTIVE' ORDER BY id"
            ),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    if len(panels) != 2:
        raise HTTPException(status_code=424, detail="PANEL_NOT_READY")
    db.execute(
        text(
            "UPDATE assignments SET status = 'REVIEWER_INITIALIZING', updated_at = now() WHERE id = :id"
        ),
        {"id": assignment_id},
    )
    results = []
    for panel in panels:
        reviewers = list(
            db.execute(
                text(
                    "SELECT reviewer_id FROM panel_reviewers WHERE panel_id = :id ORDER BY reviewer_id"
                ),
                {"id": panel["id"]},
            ).scalars()
        )
        submissions = (
            db.execute(
                text("""
            SELECT s.id, s.anonymous_token FROM submissions s
            JOIN material_checks mc ON mc.submission_id = s.id
            WHERE s.assignment_id = :assignment_id AND s.class_id = :class_id
              AND s.is_current AND s.status = 'VALID' AND mc.status = 'VALID' ORDER BY s.id
        """),
                {"assignment_id": assignment_id, "class_id": panel["target_class_id"]},
            )
            .mappings()
            .all()
        )
        input_hash = hashlib.sha256(
            json.dumps(
                {
                    "panel": panel["id"],
                    "reviewers": reviewers,
                    "submissions": [s["id"] for s in submissions],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        run_id = db.execute(
            text("""
            INSERT INTO algorithm_runs(assignment_id, panel_id, algorithm_name, version, parameters_json, input_hash, status, finished_at)
            VALUES (:assignment_id, :panel_id, 'fixed_cross_class_task_initialization', '1.0.0', '{}', :input_hash, 'COMPLETED', now())
            RETURNING id
        """),
            {"assignment_id": assignment_id, "panel_id": panel["id"], "input_hash": input_hash},
        ).scalar_one()
        for submission in submissions:
            for reviewer_id in reviewers:
                db.execute(
                    text("""
                    INSERT INTO review_tasks(panel_id, submission_id, reviewer_id, anonymous_token)
                    VALUES (:panel_id, :submission_id, :reviewer_id, :anonymous_token)
                    ON CONFLICT (panel_id, submission_id, reviewer_id) DO NOTHING
                """),
                    {
                        "panel_id": panel["id"],
                        "submission_id": submission["id"],
                        "reviewer_id": reviewer_id,
                        "anonymous_token": submission["anonymous_token"],
                    },
                )
        results.append(
            {
                "panel_id": panel["id"],
                "algorithm_run_id": run_id,
                "task_count": len(submissions) * 5,
            }
        )
    db.execute(
        text(
            "UPDATE assignments SET status = 'REVIEWER_GRADING', updated_at = now() WHERE id = :id"
        ),
        {"id": assignment_id},
    )
    audit(db, teacher.id, "INITIALIZE_REVIEW_TASKS", "assignment", assignment_id, after=results)
    db.commit()
    return ApiResponse(
        data={"assignment_id": assignment_id, "status": "REVIEWER_GRADING", "panels": results}
    )


@router.get("/ai-video/status", response_model=ApiResponse)
def ai_video_status(_: CurrentUser = Depends(require_teacher)) -> ApiResponse:
    status_value = get_video_provider_status(settings)
    return ApiResponse(data=status_value.__dict__)


@router.put("/assignments/{assignment_id}", response_model=ApiResponse)
def edit_draft(
    assignment_id: int,
    payload: DraftAssignmentUpdate,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    before = lock_assignment(db, assignment_id)
    if before["status"] != "DRAFT":
        raise HTTPException(409, "ASSIGNMENT_NOT_DRAFT")
    if before["updated_at"] != payload.expected_updated_at:
        raise HTTPException(409, "DRAFT_VERSION_CONFLICT")
    if db.execute(
        text("SELECT EXISTS(SELECT 1 FROM submissions WHERE assignment_id = :id) OR EXISTS(SELECT 1 FROM code_submissions WHERE assignment_id = :id)"),
        {"id": assignment_id},
    ).scalar_one():
        raise HTTPException(409, "ASSIGNMENT_HAS_SUBMISSIONS")
    classes = set(
        db.execute(
            text("SELECT id FROM classes WHERE id = ANY(:ids)"), {"ids": payload.class_ids}
        ).scalars()
    )
    if classes != set(payload.class_ids):
        raise HTTPException(422, "CLASS_NOT_FOUND")
    params = payload.model_dump(exclude={"class_ids", "rubric_items", "expected_updated_at", "programming_problem"})
    db.execute(
        text("""
        UPDATE assignments SET title=:title, type=:type, submit_deadline=:submit_deadline,
          review_deadline=:review_deadline, teacher_weight=:teacher_weight,
          designated_review_weight=:designated_review_weight, updated_at=now() WHERE id=:id
    """),
        {"id": assignment_id, **params},
    )
    old_classes = set(
        db.execute(
            text("SELECT class_id FROM assignment_classes WHERE assignment_id=:id"),
            {"id": assignment_id},
        ).scalars()
    )
    if old_classes != classes or before["type"] != payload.type:
        db.execute(text("DELETE FROM review_panels WHERE assignment_id=:id"), {"id": assignment_id})
    if old_classes != classes:
        db.execute(
            text("DELETE FROM assignment_classes WHERE assignment_id=:id"), {"id": assignment_id}
        )
        for class_id in classes:
            db.execute(
                text("INSERT INTO assignment_classes VALUES (:a,:c)"),
                {"a": assignment_id, "c": class_id},
            )
    db.execute(text("DELETE FROM rubrics WHERE assignment_id=:id"), {"id": assignment_id})
    rubric_id = db.execute(
        text("""
        INSERT INTO rubrics(assignment_id,name,total_score) VALUES (:a,'课程评分量表',:total) RETURNING id
    """),
        {"a": assignment_id, "total": sum(r.max_score for r in payload.rubric_items)},
    ).scalar_one()
    for item in payload.rubric_items:
        db.execute(
            text("""
            INSERT INTO rubric_items(rubric_id,name,max_score,sort_order,description)
            VALUES (:rubric_id,:name,:max_score,:sort_order,:description)
        """),
            {"rubric_id": rubric_id, **item.model_dump()},
        )
    save_programming_problem(db, assignment_id, payload.programming_problem)
    audit(
        db,
        teacher.id,
        "EDIT_DRAFT",
        "assignment",
        assignment_id,
        dict(before),
        payload.model_dump(),
    )
    db.commit()
    return ApiResponse(
        data={
            "assignment_id": assignment_id,
            "status": "DRAFT",
            "panels_reset": old_classes != classes or before["type"] != payload.type,
        }
    )


@router.delete("/assignments/{assignment_id}", response_model=ApiResponse)
def delete_draft(
    assignment_id: int,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    before = lock_assignment(db, assignment_id)
    if before["status"] != "DRAFT":
        raise HTTPException(409, "ASSIGNMENT_NOT_DRAFT")
    if db.execute(
        text("""SELECT EXISTS(SELECT 1 FROM submissions WHERE assignment_id=:id)
                         OR EXISTS(SELECT 1 FROM code_submissions WHERE assignment_id=:id)
                         OR EXISTS(SELECT 1 FROM algorithm_runs WHERE assignment_id=:id)"""),
        {"id": assignment_id},
    ).scalar_one():
        raise HTTPException(409, "ASSIGNMENT_HAS_SUBMISSIONS")
    audit(db, teacher.id, "DELETE_DRAFT", "assignment", assignment_id, before=dict(before))
    db.execute(text("DELETE FROM assignments WHERE id=:id"), {"id": assignment_id})
    db.commit()
    return ApiResponse(data={"deleted": True})


@router.put("/assignments/{assignment_id}/review-deadline", response_model=ApiResponse)
def extend_review_deadline(
    assignment_id: int,
    payload: ReviewDeadlineInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = lock_assignment(db, assignment_id)
    if assignment["status"] not in {"PUBLISHED", "SUBMITTING", "REVIEWER_GRADING"}:
        raise HTTPException(400, "INVALID_STATE")
    if payload.review_deadline <= datetime.now(UTC) or (
        assignment["review_deadline"] and payload.review_deadline <= assignment["review_deadline"]
    ):
        raise HTTPException(422, "DEADLINE_MUST_BE_EXTENDED")
    db.execute(
        text("UPDATE assignments SET review_deadline=:deadline, updated_at=now() WHERE id=:id"),
        {"id": assignment_id, "deadline": payload.review_deadline},
    )
    audit(
        db,
        teacher.id,
        "EXTEND_REVIEW_DEADLINE",
        "assignment",
        assignment_id,
        {"review_deadline": assignment["review_deadline"]},
        payload.model_dump(),
    )
    db.commit()
    return ApiResponse(data={"review_deadline": payload.review_deadline})


@router.get("/assignments/{assignment_id}/review-progress", response_model=ApiResponse)
def review_progress(
    assignment_id: int, _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
):
    if (
        db.execute(
            text("SELECT id FROM assignments WHERE id=:id"), {"id": assignment_id}
        ).scalar_one_or_none()
        is None
    ):
        raise _not_found()
    rows = (
        db.execute(
            text("""
        SELECT p.id AS panel_id, c.name AS target_class_name, u.name AS reviewer_name,
               u.student_no, pr.reviewer_id, count(rt.id) AS task_count,
               count(rt.id) FILTER (WHERE rt.status='SUBMITTED') AS completed_count,
               COALESCE(jsonb_agg(jsonb_build_object('task_id',rt.id,'submission_id',rt.submission_id,
                 'anonymous_token',rt.anonymous_token,'status',rt.status))
                 FILTER (WHERE rt.id IS NOT NULL AND rt.status <> 'SUBMITTED'), '[]') AS missing_tasks
        FROM review_panels p JOIN classes c ON c.id=p.target_class_id
        JOIN panel_reviewers pr ON pr.panel_id=p.id JOIN users u ON u.id=pr.reviewer_id
        LEFT JOIN review_tasks rt ON rt.panel_id=p.id AND rt.reviewer_id=pr.reviewer_id
        WHERE p.assignment_id=:id GROUP BY p.id,c.name,u.name,u.student_no,pr.reviewer_id
        ORDER BY p.id,u.student_no
    """),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    return ApiResponse(data=[dict(row) for row in rows])
