from fastapi import APIRouter

from app.api.routes import (
    auth,
    health,
    internal_review,
    reviewer_tasks,
    teacher_assignments,
    teacher_grades,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(reviewer_tasks.router, prefix="/reviewer", tags=["reviewer"])
api_router.include_router(teacher_assignments.router, prefix="/teacher", tags=["teacher-assignments"])
api_router.include_router(teacher_grades.router, prefix="/teacher", tags=["teacher-grades"])
internal_router = APIRouter()
internal_router.include_router(internal_review.router, prefix="/designated-review", tags=["internal-algorithm"])
