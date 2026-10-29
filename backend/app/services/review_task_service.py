"""Pure planning boundary for the joint cross-class allocator."""

from algorithm.algorithms.allocation import Work, allocate_reviews

from app.schemas.review import InitializeRequest, InitializeResponse, ReviewTaskPlan


def build_task_plan(request: InitializeRequest) -> InitializeResponse:
    plan = allocate_reviews([Work(**w.model_dump()) for w in request.works], request.seed)
    return InitializeResponse(
        assignment_id=request.assignment_id,
        expected_task_count=len(plan.edges),
        seed=plan.seed,
        input_hash=plan.input_hash,
        diagnostics=plan.diagnostics,
        tasks=[
            ReviewTaskPlan(reviewer_id=e.reviewer_id, submission_id=e.submission_id)
            for e in plan.edges
        ],
    )
