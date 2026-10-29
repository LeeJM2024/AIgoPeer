from fastapi import APIRouter, Depends

from app.api.routes import (
    auth,
    health,
    internal_review,
    reviewer_tasks,
    teacher_assignments,
    teacher_evidence,
    teacher_grades,
    teacher_management,
    teacher_reports,
)
from app.api.routes.student import assignments as student_assignments
from app.api.routes.student import (
    programming_submissions,
    project_submissions,
    subjective_submissions,
    topics,
)
from app.core.security import require_internal_service
from app.services.assignment_lifecycle import enforce_assignment_lifecycle

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
course_router = APIRouter(dependencies=[Depends(enforce_assignment_lifecycle)])
course_router.include_router(reviewer_tasks.router, prefix="/reviewer", tags=["reviewer"])
course_router.include_router(student_assignments.router, prefix="/student", tags=["student"])
course_router.include_router(topics.router, tags=["student"])
course_router.include_router(project_submissions.router, tags=["student"])
course_router.include_router(programming_submissions.router, tags=["student"])
course_router.include_router(subjective_submissions.router, prefix="/student", tags=["student"])
course_router.include_router(
    teacher_assignments.router, prefix="/teacher", tags=["teacher-assignments"]
)
course_router.include_router(teacher_grades.router, prefix="/teacher", tags=["teacher-grades"])
course_router.include_router(teacher_management.router, prefix="/teacher", tags=["teacher-management"])
course_router.include_router(teacher_reports.router, prefix="/teacher", tags=["teacher-reports"])
course_router.include_router(teacher_evidence.router, prefix="/teacher", tags=["teacher-evidence"])
api_router.include_router(course_router)
internal_router = APIRouter(dependencies=[Depends(require_internal_service)])
internal_router.include_router(
    internal_review.router, prefix="/designated-review", tags=["internal-algorithm"]
)
