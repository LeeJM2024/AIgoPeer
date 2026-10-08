from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.programming import CodeSubmissionRequest
from app.services.judge_queue import enqueue_submission
from app.services.student.programming_submission_service import (
    create_code_submission,
    get_code_submission,
    get_programming_problem,
)

router = APIRouter()


def require_student(current_user: CurrentUser) -> CurrentUser:
    if current_user.system_role != "STUDENT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    return current_user


@router.get("/student/assignments/{assignment_id}/programming-problem", response_model=ApiResponse)
def read_programming_problem(
    assignment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse:
    current_user = require_student(current_user)
    problem = get_programming_problem(db=db, assignment_id=assignment_id, student_id=current_user.id)
    return ApiResponse(data=problem.model_dump())


@router.post("/assignments/{assignment_id}/code-submissions", response_model=ApiResponse)
def submit_code(
    assignment_id: int,
    payload: CodeSubmissionRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse:
    current_user = require_student(current_user)
    created = create_code_submission(
        db=db, assignment_id=assignment_id, student_id=current_user.id, payload=payload
    )
    try:
        enqueue_submission(created.submission_id)
    except RedisError as exc:
        db.execute(
            text(
                """
                UPDATE code_submissions
                SET status = 'SYSTEM_ERROR', finished_at = now(), updated_at = now()
                WHERE id = :submission_id AND status = 'QUEUED'
                """
            ),
            {"submission_id": created.submission_id},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="JUDGE_UNAVAILABLE") from exc
    return ApiResponse(data=created.model_dump())


@router.get("/code-submissions/{submission_id}", response_model=ApiResponse)
def read_code_submission(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse:
    current_user = require_student(current_user)
    submission = get_code_submission(db=db, submission_id=submission_id, student_id=current_user.id)
    return ApiResponse(data=submission.model_dump(mode="json"))
