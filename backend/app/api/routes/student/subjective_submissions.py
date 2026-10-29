"""Versioned online answers; submission completes the work without grading."""

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.services.assignment_content import assignment_topics
from app.services.assignment_lifecycle import submission_intake_open

router = APIRouter()


def require_student(user: CurrentUser = Depends(get_current_user)):
    if user.system_role != "STUDENT":
        raise HTTPException(403, "FORBIDDEN")
    return user


class AnswerInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    content: str = Field(min_length=1, max_length=50000)


def _assignment(db, assignment_id, student_id, lock=False):
    row = (
        db.execute(
            text(
                """
        SELECT a.*,ac.class_id,u.name AS author_name,u.student_no
        FROM assignments a JOIN assignment_classes ac ON ac.assignment_id=a.id
        JOIN enrollments e ON e.class_id=ac.class_id
        JOIN users u ON u.id=e.user_id
        WHERE a.id=:a AND e.user_id=:u AND a.status <> 'DRAFT'
          AND a.type IN ('ALGORITHM_ANALYSIS','PROOF','OPEN_ENDED')
        ORDER BY ac.class_id LIMIT 1
    """
                + (" FOR UPDATE OF a" if lock else "")
            ),
            {"a": assignment_id, "u": student_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "NOT_FOUND")
    return row


@router.get("/assignments/{assignment_id}/subjective", response_model=ApiResponse)
def get_subjective(
    assignment_id: int,
    response: Response,
    user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
):
    row = _assignment(db, assignment_id, user.id)
    response.headers["Cache-Control"] = "private, no-store"
    current = (
        db.execute(
            text("""
        SELECT s.id,s.version,s.submitted_at,ans.content FROM submissions s
        JOIN subjective_answers ans ON ans.submission_id=s.id
        WHERE s.assignment_id=:a AND s.author_id=:u AND s.is_current
    """),
            {"a": assignment_id, "u": user.id},
        )
        .mappings()
        .one_or_none()
    )
    return ApiResponse(
        data={
            **{
                key: row[key]
                for key in (
                    "id",
                    "title",
                    "type",
                    "status",
                    "statement",
                    "submit_deadline",
                    "review_deadline",
                )
            },
            "topics": assignment_topics(db, assignment_id),
            "rubric_items": [],
            "current": dict(current) if current else None,
            "can_submit": submission_intake_open(row),
        }
    )


@router.post("/assignments/{assignment_id}/subjective-submissions", response_model=ApiResponse)
def submit_answer(
    assignment_id: int,
    payload: AnswerInput,
    user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
):
    row = _assignment(db, assignment_id, user.id, lock=True)
    if not submission_intake_open(row):
        raise HTTPException(409, "SUBMISSION_CLOSED")
    if row["submit_deadline"] and row["submit_deadline"] <= datetime.now(UTC):
        raise HTTPException(409, "SUBMISSION_DEADLINE_PASSED")
    version = db.execute(
        text("""
        SELECT COALESCE(max(version),0)+1 FROM submissions WHERE assignment_id=:a AND author_id=:u
    """),
        {"a": assignment_id, "u": user.id},
    ).scalar_one()
    db.execute(
        text("""
        UPDATE submissions SET is_current=false,status='SUPERSEDED',updated_at=now()
        WHERE assignment_id=:a AND author_id=:u AND is_current
    """),
        {"a": assignment_id, "u": user.id},
    )
    sid = db.execute(
        text("""
        INSERT INTO submissions(assignment_id,author_id,class_id,status,anonymous_token,
          submitted_at,version,is_current)
        VALUES (:a,:u,:c,'VALID',:token,clock_timestamp(),:v,true) RETURNING id
    """),
        {
            "a": assignment_id,
            "u": user.id,
            "c": row["class_id"],
            "token": secrets.token_urlsafe(24),
            "v": version,
        },
    ).scalar_one()
    db.execute(
        text("INSERT INTO subjective_answers VALUES (:s,:content)"),
        {"s": sid, "content": payload.content},
    )
    db.execute(
        text("""INSERT INTO material_checks(submission_id,status,checked_at)
        VALUES (:s,'VALID',clock_timestamp())"""),
        {"s": sid},
    )
    db.commit()
    return ApiResponse(data={"submission_id": sid, "version": version, "status": "VALID"})


@router.get("/assignments/{assignment_id}/subjective-submissions/mine", response_model=ApiResponse)
def answer_history(
    assignment_id: int,
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
):
    _assignment(db, assignment_id, user.id)
    response.headers["Cache-Control"] = "private, no-store"
    params = {
        "a": assignment_id,
        "u": user.id,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    total = db.execute(
        text("""SELECT count(*) FROM submissions
        WHERE assignment_id=:a AND author_id=:u"""),
        params,
    ).scalar_one()
    rows = db.execute(
        text("""SELECT s.id,s.version,s.is_current,s.submitted_at,ans.content
        FROM submissions s JOIN subjective_answers ans ON ans.submission_id=s.id
        WHERE s.assignment_id=:a AND s.author_id=:u ORDER BY s.version DESC LIMIT :limit OFFSET :offset
    """),
        params,
    ).mappings()
    return ApiResponse(data={"items": [dict(item) for item in rows], "total": total, "page": page})
