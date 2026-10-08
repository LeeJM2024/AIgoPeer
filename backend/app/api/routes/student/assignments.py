from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
