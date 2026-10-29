"""Stable service boundary for member 3's fixed-panel task initialization."""

from app.schemas.review import InitializeRequest, InitializeResponse, ReviewTaskPlan


def build_task_plan(request: InitializeRequest) -> InitializeResponse:
    """Create the deterministic Cartesian product: every valid work × five reviewers.

    This function has no database side effects so it is easy to unit test. The API
    orchestration layer must persist the returned tasks in one transaction and rely
    on the database unique constraint `(panel_id, submission_id, reviewer_id)`.
    """
    tasks = [
        ReviewTaskPlan(panel_id=request.panel.panel_id, reviewer_id=reviewer_id, submission_id=submission_id)
        for submission_id in request.valid_submission_ids
        for reviewer_id in request.panel.reviewer_ids
    ]
    return InitializeResponse(
        assignment_id=request.assignment_id,
        panel_id=request.panel.panel_id,
        expected_task_count=len(request.valid_submission_ids) * 5,
        tasks=tasks,
    )
