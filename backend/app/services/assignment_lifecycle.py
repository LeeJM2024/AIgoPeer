"""Apply closure/deletion consistently to assignment and child-resource routes."""

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db


def submission_intake_open(assignment):
    return (
        assignment["status"] in {"PUBLISHED", "SUBMITTING", "REVIEWER_GRADING"}
        and assignment["closed_at"] is None
        and assignment["deleted_at"] is None
        and assignment["submissions_closed_at"] is None
        and (
            assignment["submit_deadline"] is None
            or assignment["submit_deadline"] > datetime.now(UTC)
        )
    )


def has_assigned_work(db, assignment_id, student_id):
    return db.execute(
        text("""SELECT EXISTS(SELECT 1 FROM review_tasks rt JOIN submissions s ON s.id=rt.submission_id
      WHERE s.assignment_id=:a AND s.author_id=:u AND s.is_current AND rt.is_active)"""),
        {"a": assignment_id, "u": student_id},
    ).scalar_one()


def require_available(assignment, *, writable=False):
    if assignment is None or assignment["deleted_at"] is not None:
        raise HTTPException(404, "ASSIGNMENT_NOT_FOUND")
    if writable and assignment["closed_at"] is not None:
        raise HTTPException(409, "ASSIGNMENT_CLOSED")


def enforce_assignment_lifecycle(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    params = request.path_params
    if "/teacher/" in request.url.path and user.system_role != "TEACHER":
        raise HTTPException(403, "FORBIDDEN")
    aid = params.get("assignment_id")
    if aid is None and request.url.path.endswith("/student/grades"):
        aid = request.query_params.get("assignment_id")
    if aid is None:
        # Names below come only from registered application routes, never from input SQL.
        children = {
            "submission_id": "code_submissions"
            if "/code-submissions/" in request.url.path
            else "submissions",
            "task_id": "review_tasks",
            "grade_id": "teacher_grades",
            "anomaly_id": "anomaly_records",
        }
        for name, table in children.items():
            if name not in params:
                continue
            try:
                child_id = int(params[name])
            except (TypeError, ValueError):
                return
            column = (
                "assignment_id"
                if table in {"submissions", "code_submissions"}
                else "(SELECT assignment_id FROM submissions WHERE id=child.submission_id)"
            )
            aid = db.execute(
                text(f"SELECT {column} FROM {table} child WHERE id=:id"), {"id": child_id}
            ).scalar_one_or_none()
            break
    if aid is None:
        return  # The endpoint retains its own not-found/validation behavior.
    try:
        aid = int(aid)
    except (TypeError, ValueError):
        return
    writing = request.method not in {"GET", "HEAD", "OPTIONS"}
    uploading = request.method == "POST" and request.url.path.endswith("/project-submissions")
    # A slow upload must not hold the whole assignment locked. Intake status and
    # server time are checked again atomically when its submission is inserted.
    lock = " FOR UPDATE" if writing and not uploading else ""
    assignment = (
        db.execute(
            text(f"SELECT id,closed_at,deleted_at FROM assignments WHERE id=:id{lock}"), {"id": aid}
        )
        .mappings()
        .one_or_none()
    )
    # Closing, restoring and deleting remain available to teachers at every stage.
    lifecycle_action = user.system_role == "TEACHER" and (
        request.url.path.endswith(("/close", "/reopen"))
        or request.method == "DELETE"
        and "assignment_id" in params
    )
    require_available(assignment, writable=writing and not lifecycle_action)
    if assignment["closed_at"] is not None and user.system_role != "TEACHER":
        raise HTTPException(409, "ASSIGNMENT_CLOSED")
