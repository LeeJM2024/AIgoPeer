"""Authorization rules shared by endpoint modules.

Database queries are intentionally injected later: keeping the policy here avoids
putting anonymity and cross-class logic in Vue components.
"""

from fastapi import HTTPException, status


def require_owned_review_task(*, current_user_id: int, task_reviewer_id: int, task_target_class_id: int, reviewer_class_id: int) -> None:
    if current_user_id != task_reviewer_id or task_target_class_id == reviewer_class_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
