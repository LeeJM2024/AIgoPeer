from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.review import AggregatePanelRequest, AggregateRequest, InitializeRequest
from app.services.designated_review_service import aggregate_panel_and_persist
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


@router.post("/aggregate-panel", response_model=ApiResponse)
def aggregate_and_persist_panel(
    payload: AggregatePanelRequest, db: Session = Depends(get_db)
) -> ApiResponse:
    """Worker endpoint: builds a locked database snapshot and persists one run."""
    result = aggregate_panel_and_persist(db, payload.assignment_id, payload.panel_id)
    db.commit()
    return ApiResponse(data=result)
