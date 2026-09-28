from fastapi import APIRouter

from app.api.routes import health, internal_review, reviewer_tasks
from app.api.routes.student import project_submissions, topics
from app.api.routes.student import assignments as student_assignments

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(reviewer_tasks.router, prefix="/reviewer", tags=["reviewer"])
api_router.include_router(student_assignments.router, prefix="/student", tags=["student"])
api_router.include_router(topics.router, tags=["student"])
api_router.include_router(project_submissions.router, tags=["student"])
internal_router = APIRouter()
internal_router.include_router(internal_review.router, prefix="/designated-review", tags=["internal-algorithm"])
