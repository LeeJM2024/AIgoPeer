"""Read models used by the student workspace.

This module intentionally returns only the authenticated student's own submission
summary. It never joins review, grade, aggregation, or author-identity data.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.student import StudentAssignmentSummary, StudentSubmissionSummary


def list_visible_assignments(*, db: Session, student_id: int) -> list[StudentAssignmentSummary]:
    """List non-draft assignments in the student's enrolled classes.

The lateral subqueries select only this student's current submission.  They never
join review, grade, aggregation, or another student's data.
    """
    result = db.execute(
        text(
            """
            SELECT
                a.id,
                a.title,
                a.type,
                a.status,
                a.submit_deadline,
                a.review_deadline,
                COALESCE(latest_project.id, latest_code.id) AS submission_id,
                COALESCE(latest_project.status, latest_code.status) AS submission_status,
                material_checks.status AS material_check_status
            FROM assignments AS a
            LEFT JOIN LATERAL (
                SELECT submission.id, submission.status
                FROM submissions AS submission
                WHERE submission.assignment_id = a.id
                  AND submission.author_id = :student_id
                  AND a.type = 'FINAL_PROJECT'
                  AND submission.is_current = TRUE
                ORDER BY submission.submitted_at DESC NULLS LAST, submission.id DESC
                LIMIT 1
            ) AS latest_project ON TRUE
            LEFT JOIN LATERAL (
                SELECT code_submission.id, code_submission.status
                FROM code_submissions AS code_submission
                WHERE code_submission.assignment_id = a.id
                  AND code_submission.author_id = :student_id
                  AND a.type = 'PROGRAMMING'
                  AND code_submission.is_current = TRUE
                ORDER BY code_submission.queued_at DESC, code_submission.id DESC
                LIMIT 1
            ) AS latest_code ON TRUE
            LEFT JOIN material_checks ON material_checks.submission_id = latest_project.id
            WHERE a.status <> 'DRAFT'
              AND EXISTS (
                  SELECT 1
                  FROM assignment_classes AS assignment_class
                  JOIN enrollments AS enrollment ON enrollment.class_id = assignment_class.class_id
                  WHERE assignment_class.assignment_id = a.id
                    AND enrollment.user_id = :student_id
              )
            ORDER BY
                CASE
                    WHEN a.submit_deadline IS NULL OR a.submit_deadline >= NOW() THEN 0
                    ELSE 1
                END,
                CASE
                    WHEN a.submit_deadline IS NULL OR a.submit_deadline >= NOW() THEN a.submit_deadline
                END ASC NULLS LAST,
                CASE
                    WHEN a.submit_deadline < NOW() THEN a.submit_deadline
                END DESC NULLS LAST,
                a.id DESC
            """
        ),
        {"student_id": student_id},
    )

    assignments: list[StudentAssignmentSummary] = []
    for row in result.mappings().all():
        submission = None
        if row["submission_id"] is not None:
            submission = StudentSubmissionSummary(
                id=int(row["submission_id"]),
                status=str(row["submission_status"]),
                material_check_status=(
                    str(row["material_check_status"])
                    if row["material_check_status"] is not None
                    else None
                ),
            )
        assignments.append(
            StudentAssignmentSummary(
                id=int(row["id"]),
                title=str(row["title"]),
                type=str(row["type"]),
                status=str(row["status"]),
                submit_deadline=row["submit_deadline"],
                review_deadline=row["review_deadline"],
                submission=submission,
            )
        )
    return assignments
