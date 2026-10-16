from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.services.student.assignment_service import list_visible_assignments

router = APIRouter()


@router.get("/assignments", response_model=ApiResponse)
def list_my_assignments(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse:
    """Return the current student's safe, class-scoped assignment workspace."""
    if current_user.system_role != "STUDENT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    assignments = list_visible_assignments(db=db, student_id=current_user.id)
    return ApiResponse(data=[assignment.model_dump(mode="json") for assignment in assignments])


@router.get("/grades", response_model=ApiResponse)
def read_my_published_grade(
    assignment_id: int = Query(gt=0),
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
) -> ApiResponse:
    """Return the student's own published result without exposing grade inputs.

    Per-rubric component scores, teacher raw scores, peer aggregates, anomalies,
    and reviewer identities intentionally never cross this endpoint.
    """
    if current_user.system_role != "STUDENT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    enrolled = db.execute(
        text("""SELECT EXISTS(SELECT 1 FROM assignment_classes ac JOIN enrollments e ON e.class_id=ac.class_id
             WHERE ac.assignment_id=:assignment_id AND e.user_id=:student_id)"""),
        {"assignment_id": assignment_id, "student_id": current_user.id},
    ).scalar_one()
    if not enrolled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")
    row = db.execute(
        text("""SELECT a.status AS assignment_status,fg.final_score,fg.published_at,tg.feedback
            FROM assignments a JOIN submissions s ON s.assignment_id=a.id
            LEFT JOIN final_grades fg ON fg.submission_id=s.id
            LEFT JOIN LATERAL (SELECT feedback FROM teacher_grades WHERE submission_id=s.id
                               ORDER BY version DESC LIMIT 1) tg ON true
            WHERE a.id=:assignment_id AND s.author_id=:student_id AND s.is_current
            ORDER BY s.id DESC LIMIT 1"""),
        {"assignment_id": assignment_id, "student_id": current_user.id},
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")
    if row["assignment_status"] != "PUBLISHED_RESULT" or row["final_score"] is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    rubric = db.execute(
        text("""SELECT ri.name,ri.description,ri.max_score,ri.sort_order FROM rubric_items ri
            JOIN rubrics r ON r.id=ri.rubric_id WHERE r.assignment_id=:assignment_id
            ORDER BY ri.sort_order,ri.id"""),
        {"assignment_id": assignment_id},
    ).mappings().all()
    comments = db.execute(
        text("""SELECT rc.content FROM review_comments rc JOIN review_tasks rt ON rt.id=rc.review_task_id
            JOIN submissions s ON s.id=rt.submission_id
            WHERE s.assignment_id=:assignment_id AND s.author_id=:student_id AND s.is_current
              AND rt.status='SUBMITTED' ORDER BY rc.id"""),
        {"assignment_id": assignment_id, "student_id": current_user.id},
    ).scalars().all()
    return ApiResponse(data={
        "assignment_id": assignment_id,
        "final_score": row["final_score"],
        "published_at": row["published_at"],
        "rubric_items": [dict(item) for item in rubric],
        "anonymous_comments": list(comments),
        "teacher_feedback": row["feedback"] or "",
    })
