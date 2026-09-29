"""Student-facing programming problem queries and submission creation.

Hidden test data is deliberately selected only by the judge worker.  No student
route in this module reads or serializes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.programming import (
    CodeSubmissionCreated,
    CodeSubmissionRequest,
    CodeSubmissionResult,
    ProgrammingProblemView,
    PublicSample,
)


@dataclass(frozen=True)
class QueuedCodeSubmission:
    submission_id: int


def _student_programming_assignment(*, db: Session, assignment_id: int, student_id: int):
    return db.execute(
        text(
            """
            SELECT a.id, a.title, a.status, a.submit_deadline, assignment_class.class_id,
                   problem.statement, problem.input_description, problem.output_description,
                   problem.time_limit_ms, problem.memory_limit_mb
            FROM assignments AS a
            JOIN assignment_classes AS assignment_class ON assignment_class.assignment_id = a.id
            JOIN enrollments AS enrollment ON enrollment.class_id = assignment_class.class_id
            JOIN programming_problems AS problem ON problem.assignment_id = a.id
            WHERE a.id = :assignment_id
              AND a.type = 'PROGRAMMING'
              AND a.status <> 'DRAFT'
              AND enrollment.user_id = :student_id
            ORDER BY assignment_class.class_id
            LIMIT 1
            """
        ),
        {"assignment_id": assignment_id, "student_id": student_id},
    ).mappings().one_or_none()


def get_programming_problem(
    *, db: Session, assignment_id: int, student_id: int
) -> ProgrammingProblemView:
    assignment = _student_programming_assignment(
        db=db, assignment_id=assignment_id, student_id=student_id
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")
    samples = db.execute(
        text(
            """
            SELECT input_data, expected_output
            FROM programming_test_cases
            WHERE problem_assignment_id = :assignment_id AND is_public = TRUE
            ORDER BY sort_order
            """
        ),
        {"assignment_id": assignment_id},
    ).mappings().all()
    return ProgrammingProblemView(
        assignment_id=assignment_id,
        title=str(assignment["title"]),
        statement=str(assignment["statement"]),
        input_description=str(assignment["input_description"]),
        output_description=str(assignment["output_description"]),
        time_limit_ms=int(assignment["time_limit_ms"]),
        memory_limit_mb=int(assignment["memory_limit_mb"]),
        samples=[PublicSample.model_validate(sample) for sample in samples],
    )


def create_code_submission(
    *, db: Session, assignment_id: int, student_id: int, payload: CodeSubmissionRequest
) -> CodeSubmissionCreated:
    source_size = len(payload.source_code.encode("utf-8"))
    if source_size > settings.judge_source_limit_bytes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="VALIDATION_ERROR")

    assignment = _student_programming_assignment(
        db=db, assignment_id=assignment_id, student_id=student_id
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")
    if str(assignment["status"]) not in {"PUBLISHED", "SUBMITTING"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_STATE")
    deadline = assignment["submit_deadline"]
    if deadline is not None and deadline <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_STATE")

    try:
        version = int(
            db.execute(
                text(
                    """
                    SELECT COALESCE(MAX(version), 0) + 1
                    FROM code_submissions
                    WHERE assignment_id = :assignment_id AND author_id = :student_id
                    """
                ),
                {"assignment_id": assignment_id, "student_id": student_id},
            ).scalar_one()
        )
        db.execute(
            text(
                """
                UPDATE code_submissions
                SET is_current = FALSE, updated_at = now()
                WHERE assignment_id = :assignment_id AND author_id = :student_id AND is_current = TRUE
                """
            ),
            {"assignment_id": assignment_id, "student_id": student_id},
        )
        submission_id = db.execute(
            text(
                """
                INSERT INTO code_submissions(
                  assignment_id, author_id, class_id, language, source_code, version, status
                ) VALUES (
                  :assignment_id, :student_id, :class_id, :language, :source_code, :version, 'QUEUED'
                ) RETURNING id
                """
            ),
            {
                "assignment_id": assignment_id,
                "student_id": student_id,
                "class_id": int(assignment["class_id"]),
                "language": payload.language,
                "source_code": payload.source_code,
                "version": version,
            },
        ).scalar_one()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CONFLICT") from exc
    return CodeSubmissionCreated(submission_id=int(submission_id), version=version)


def get_code_submission(
    *, db: Session, submission_id: int, student_id: int
) -> CodeSubmissionResult:
    row = db.execute(
        text(
            """
            SELECT id, assignment_id, language, version, status, queued_at AS submitted_at,
                   started_at, finished_at, time_ms, memory_kb, executed_case_count,
                   passed_case_count, compiler_output
            FROM code_submissions
            WHERE id = :submission_id AND author_id = :student_id
            """
        ),
        {"submission_id": submission_id, "student_id": student_id},
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")
    return CodeSubmissionResult.model_validate(row)
