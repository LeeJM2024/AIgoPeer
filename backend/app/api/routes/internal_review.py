from fastapi import APIRouter

from app.schemas.common import ApiResponse
from app.schemas.review import AggregateRequest, InitializeRequest
from app.services.review_task_service import build_task_plan

router = APIRouter()


@router.post("/initialize", response_model=ApiResponse)
def initialize_designated_review_tasks(payload: InitializeRequest) -> ApiResponse:
    """Internal-only endpoint; persistence is added by the repository adapter.

    Reverse-proxy policy must restrict `/internal/*` to backend/worker networks.
    It deliberately produces no author identity or teacher-grade fields.
    """
    return ApiResponse(data=build_task_plan(payload).model_dump())


@router.post("/aggregate", response_model=ApiResponse)
def aggregate_designated_reviews(payload: AggregateRequest) -> ApiResponse:
    from algorithm.algorithms.aggregation import aggregate_panel_scores

    result = aggregate_panel_scores(payload)
    return ApiResponse(data=result.model_dump())
