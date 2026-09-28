"""Reviewer-facing route placeholders.

Member 2 implements the UI against these response shapes. Repository queries are
added only after the common data model is merged, so author identity cannot leak
through ad-hoc joins in a page component.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import CurrentUser, get_current_user

router = APIRouter()


@router.get("/review-tasks/mine")
def list_my_review_tasks(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    # TODO(member2): query tasks by reviewer_id and serialize the public anonymous view only.
    return {"code": 0, "data": [], "meta": {"reviewer_id": current_user.id}}


@router.post("/review-tasks/{task_id}/reviews", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def submit_review(task_id: int, current_user: CurrentUser = Depends(get_current_user)) -> None:
    del task_id, current_user
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="MEMBER2_ENDPOINT_PENDING")
