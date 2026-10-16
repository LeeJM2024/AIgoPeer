from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.student_submission import TopicClaimRequest
from app.services.student.topic_claim_service import claim_topic, list_topics_for_assignment

router = APIRouter()


def require_student(current_user: CurrentUser) -> CurrentUser:
    if current_user.system_role != "STUDENT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    return current_user


@router.get("/student/assignments/{assignment_id}/topics", response_model=ApiResponse)
def list_assignment_topics(
    assignment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse:
    current_user = require_student(current_user)
    return ApiResponse(
        data=list_topics_for_assignment(
            db=db, assignment_id=assignment_id, student_id=current_user.id
        )
    )


@router.post("/assignments/{assignment_id}/topic-claim", response_model=ApiResponse)
def create_topic_claim(
    assignment_id: int,
    payload: TopicClaimRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse:
    current_user = require_student(current_user)
    claim = claim_topic(
        db=db,
        assignment_id=assignment_id,
        student_id=current_user.id,
        topic_id=payload.topic_id,
    )
    return ApiResponse(data=claim.model_dump())
