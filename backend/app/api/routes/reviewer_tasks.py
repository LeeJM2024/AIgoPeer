"""Anonymous, designated-reviewer endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.reviewer import ReviewSubmissionInput
from app.services.teacher_workflow import lock_assignment

router = APIRouter()

ELIGIBLE = """rt.reviewer_id=:user_id AND s.assignment_id=p.assignment_id
    AND a.type='FINAL_PROJECT' AND a.status IN ('REVIEWER_GRADING','AGGREGATING','TEACHER_GRADING')
    AND p.status='ACTIVE' AND s.class_id=p.target_class_id AND s.author_id <> :user_id
    AND p.target_class_id <> p.reviewer_class_id AND s.is_current AND s.status='VALID'
    AND EXISTS(SELECT 1 FROM material_checks WHERE submission_id=s.id AND status='VALID')
    AND EXISTS(SELECT 1 FROM panel_reviewers WHERE panel_id=p.id AND reviewer_id=:user_id)
    AND EXISTS(SELECT 1 FROM enrollments WHERE user_id=:user_id AND class_id=p.reviewer_class_id)
    AND NOT EXISTS(SELECT 1 FROM enrollments WHERE user_id=:user_id AND class_id=p.target_class_id)"""


def _has_tasks(db, user_id):
    return db.execute(
        text(
            """SELECT EXISTS(SELECT 1 FROM review_tasks rt
      JOIN review_panels p ON p.id=rt.panel_id JOIN submissions s ON s.id=rt.submission_id
      JOIN assignments a ON a.id=s.assignment_id WHERE """
            + ELIGIBLE
            + ")"
        ),
        {"user_id": user_id},
    ).scalar_one()


@router.get("/eligibility", response_model=ApiResponse)
def review_eligibility(
    response: Response,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_student(current_user)
    response.headers["Cache-Control"] = "private, no-store"
    return ApiResponse(data={"has_tasks": _has_tasks(db, current_user.id)})


def _require_student(user: CurrentUser) -> None:
    if user.system_role != "STUDENT":
        raise HTTPException(status_code=403, detail="FORBIDDEN")


def _deadline_passed(deadline: datetime | None) -> bool:
    return deadline is not None and deadline <= datetime.now(UTC)


def _owned_task(db: Session, task_id: int, user_id: int, *, lock: bool = False) -> dict:
    if lock:
        assignment_id = db.execute(
            text("""SELECT s.assignment_id FROM review_tasks rt
            JOIN submissions s ON s.id=rt.submission_id WHERE rt.id=:task AND rt.reviewer_id=:user"""),
            {"task": task_id, "user": user_id},
        ).scalar_one_or_none()
        if assignment_id is None:
            raise HTTPException(403, "FORBIDDEN")
        # Use the same parent-before-child lock order as aggregation and publication.
        lock_assignment(db, assignment_id, editable=False)
    lock_clause = " FOR UPDATE OF rt" if lock else ""
    row = (
        db.execute(
            text(
                f"""SELECT rt.id,rt.reviewer_id,rt.submission_id,rt.status,rt.anonymous_token,
                rt.started_at,rt.submitted_at,a.id AS assignment_id,a.status AS assignment_status,
                a.review_deadline,p.target_class_id,p.reviewer_class_id,
                package.status AS package_status,package.storage_key
            FROM review_tasks rt JOIN review_panels p ON p.id=rt.panel_id
            JOIN submissions s ON s.id=rt.submission_id JOIN assignments a ON a.id=s.assignment_id
            LEFT JOIN review_material_packages package ON package.submission_id=s.id
            WHERE rt.id=:task_id AND {ELIGIBLE}{lock_clause}"""
            ),
            {"task_id": task_id, "user_id": user_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(403, "FORBIDDEN")
    if int(row["reviewer_id"]) != user_id or row["target_class_id"] == row["reviewer_class_id"]:
        raise HTTPException(403, "FORBIDDEN")
    return dict(row)


def _rubric_items(db: Session, assignment_id: int) -> list[dict]:
    return [
        dict(row)
        for row in db.execute(
            text("""SELECT ri.id,ri.name,ri.description,ri.max_score,ri.sort_order
        FROM rubric_items ri JOIN rubrics r ON r.id=ri.rubric_id
        WHERE r.assignment_id=:assignment_id ORDER BY ri.sort_order,ri.id"""),
            {"assignment_id": assignment_id},
        )
        .mappings()
        .all()
    ]


@router.get("/review-tasks/mine", response_model=ApiResponse)
def list_my_review_tasks(
    response: Response,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse:
    _require_student(current_user)
    response.headers["Cache-Control"] = "private, no-store"
    if status_filter not in {None, "PENDING", "IN_PROGRESS", "SUBMITTED"}:
        raise HTTPException(422, "VALIDATION_ERROR")
    if not _has_tasks(db, current_user.id):
        raise HTTPException(403, "FORBIDDEN")
    # The default PENDING view includes started work, preventing it from vanishing on refresh.
    states = ["PENDING", "IN_PROGRESS"] if status_filter in {None, "PENDING"} else [status_filter]
    rows = (
        db.execute(
            text(f"""SELECT rt.id,rt.anonymous_token,rt.status,rt.started_at,rt.submitted_at,
        a.id AS assignment_id,a.title,a.review_deadline,package.status AS package_status
        FROM review_tasks rt JOIN review_panels p ON p.id=rt.panel_id
        JOIN submissions s ON s.id=rt.submission_id JOIN assignments a ON a.id=s.assignment_id
        LEFT JOIN review_material_packages package ON package.submission_id=s.id
        WHERE {ELIGIBLE} AND rt.status=ANY(:states)
        ORDER BY a.review_deadline NULLS LAST,rt.id LIMIT :limit OFFSET :offset"""),
            {
                "user_id": current_user.id,
                "states": states,
                "limit": page_size,
                "offset": (page - 1) * page_size,
            },
        )
        .mappings()
        .all()
    )
    data = []
    for row in rows:
        task = {
            "task_id": row["id"],
            "assignment_id": row["assignment_id"],
            "assignment_title": row["title"],
            "anonymous_token": row["anonymous_token"],
            "status": row["status"],
            "started_at": row["started_at"],
            "submitted_at": row["submitted_at"],
            "review_deadline": row["review_deadline"],
            "rubric_items": _rubric_items(db, int(row["assignment_id"])),
            "materials": [],
        }
        if row["package_status"] == "READY":
            task["materials"] = [
                {
                    "kind": "ANONYMOUS_REVIEW_PACKAGE",
                    "download_url": f"/api/reviewer/review-tasks/{row['id']}/materials/archive",
                }
            ]
        data.append(task)
    return ApiResponse(data=data)


@router.get("/review-tasks/{task_id}/materials/archive")
def download_anonymous_material(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_student(current_user)
    task = _owned_task(db, task_id, current_user.id, lock=True)
    if task["package_status"] != "READY" or not task["storage_key"]:
        raise HTTPException(424, "ANONYMOUS_MATERIAL_NOT_READY")
    if task["status"] not in {"PENDING", "IN_PROGRESS", "SUBMITTED"}:
        raise HTTPException(409, "INVALID_STATE")
    if task["status"] != "SUBMITTED" and _deadline_passed(task["review_deadline"]):
        raise HTTPException(409, "REVIEW_DEADLINE_PASSED")
    root = settings.storage_dir.resolve()
    archive = (root / str(task["storage_key"])).resolve()
    if not archive.is_relative_to(root) or not archive.is_file():
        raise HTTPException(424, "ANONYMOUS_MATERIAL_NOT_READY")
    if task["status"] == "PENDING":
        db.execute(
            text(
                "UPDATE review_tasks SET status='IN_PROGRESS',started_at=clock_timestamp(),updated_at=now() WHERE id=:id"
            ),
            {"id": task_id},
        )
        db.commit()
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=f"anonymous-review-{task['anonymous_token']}.zip",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/review-tasks/{task_id}/reviews", response_model=ApiResponse)
def submit_review(
    task_id: int,
    payload: ReviewSubmissionInput,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse:
    _require_student(current_user)
    task = _owned_task(db, task_id, current_user.id, lock=True)
    if task["status"] == "SUBMITTED":
        raise HTTPException(409, "CONFLICT")
    if task["status"] != "IN_PROGRESS" or task["started_at"] is None:
        raise HTTPException(409, "REVIEW_MATERIAL_MUST_BE_OPENED")
    if task["package_status"] != "READY" or not task["storage_key"]:
        raise HTTPException(424, "ANONYMOUS_MATERIAL_NOT_READY")
    if task["assignment_status"] != "REVIEWER_GRADING" or _deadline_passed(task["review_deadline"]):
        raise HTTPException(409, "REVIEW_DEADLINE_PASSED")
    limits = {
        int(item["id"]): item["max_score"] for item in _rubric_items(db, int(task["assignment_id"]))
    }
    scores = {item.rubric_item_id: item.score for item in payload.rubric_scores}
    if len(scores) != len(payload.rubric_scores) or set(scores) != set(limits):
        raise HTTPException(422, "ALL_RUBRIC_ITEMS_REQUIRED_ONCE")
    if any(score > limits[item_id] for item_id, score in scores.items()):
        raise HTTPException(422, "RUBRIC_SCORE_OUT_OF_RANGE")
    for item_id, score in scores.items():
        db.execute(
            text(
                "INSERT INTO review_scores(review_task_id,rubric_item_id,score) VALUES (:task,:item,:score)"
            ),
            {"task": task_id, "item": item_id, "score": score},
        )
    db.execute(
        text(
            "INSERT INTO review_comments(review_task_id,content,char_count) VALUES (:task,:content,:length)"
        ),
        {"task": task_id, "content": payload.comment, "length": len(payload.comment)},
    )
    db.execute(
        text(
            "UPDATE review_tasks SET status='SUBMITTED',submitted_at=clock_timestamp(),updated_at=now() WHERE id=:id"
        ),
        {"id": task_id},
    )
    db.commit()
    return ApiResponse(data={"task_id": task_id, "status": "SUBMITTED"})
