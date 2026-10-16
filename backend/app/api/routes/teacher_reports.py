from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_teacher
from app.db.session import get_db
from app.schemas.common import ApiResponse

router = APIRouter()


@router.get("/assignments/{assignment_id}/statistics", response_model=ApiResponse)
def assignment_statistics(
    assignment_id: int, _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
):
    assignment = (
        db.execute(
            text("SELECT id,title,status FROM assignments WHERE id=:id"), {"id": assignment_id}
        )
        .mappings()
        .one_or_none()
    )
    if assignment is None:
        raise HTTPException(404, "ASSIGNMENT_NOT_FOUND")
    maximum = db.execute(
        text("""
        SELECT COALESCE(sum(ri.max_score),0) FROM rubric_items ri JOIN rubrics r ON r.id=ri.rubric_id
        WHERE r.assignment_id=:id
    """),
        {"id": assignment_id},
    ).scalar_one()
    submissions = (
        db.execute(
            text("""
        SELECT count(*) AS total, count(*) FILTER (WHERE status='VALID') AS valid,
          count(*) FILTER (WHERE status='INVALID' OR status='RETURNED') AS invalid
        FROM submissions WHERE assignment_id=:id
    """),
            {"id": assignment_id},
        )
        .mappings()
        .one()
    )
    reviews = (
        db.execute(
            text("""
        SELECT count(*) AS total, count(*) FILTER (WHERE rt.status='SUBMITTED') AS completed
        FROM review_tasks rt JOIN review_panels p ON p.id=rt.panel_id WHERE p.assignment_id=:id
    """),
            {"id": assignment_id},
        )
        .mappings()
        .one()
    )
    rows = (
        db.execute(
            text("""
        SELECT s.id AS submission_id,u.student_no,u.name,c.name AS class_name,
          f.final_score,t.total_score AS teacher_score,a.total_score AS aggregate_score,
          t.version AS teacher_grade_version,f.teacher_weight,f.designated_review_weight,f.published_at,
          f.final_grade_source,fr.final_score AS final_review_score,fr.reason AS final_review_reason,
          fr.locked_at AS final_review_locked_at
        FROM final_grades f JOIN submissions s ON s.id=f.submission_id JOIN users u ON u.id=s.author_id
        JOIN classes c ON c.id=s.class_id JOIN teacher_grades t ON t.id=f.teacher_grade_id
        LEFT JOIN designated_review_aggregates a ON a.id=f.aggregate_id
        LEFT JOIN teacher_final_reviews fr ON fr.id=f.teacher_final_review_id
        WHERE s.assignment_id=:id ORDER BY c.name,u.student_no,s.id
    """),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    bins = [
        {"label": label, "count": 0}
        for label in ["低于60%", "60%–69%", "70%–79%", "80%–89%", "90%及以上"]
    ]
    passed = 0
    for row in rows:
        ratio = row["final_score"] / maximum if maximum else Decimal(0)
        index = (
            0
            if ratio < Decimal(".6")
            else 1
            if ratio < Decimal(".7")
            else 2
            if ratio < Decimal(".8")
            else 3
            if ratio < Decimal(".9")
            else 4
        )
        bins[index]["count"] += 1
        passed += ratio >= Decimal(".6")
    return ApiResponse(
        data={
            "assignment": dict(assignment),
            "maximum_score": maximum,
            "submissions": dict(submissions),
            "reviews": dict(reviews),
            "published_count": len(rows),
            "pass_rate": round(passed / len(rows), 4) if rows else None,
            "average": round(sum(row["final_score"] for row in rows) / len(rows), 2)
            if rows
            else None,
            "distribution": bins,
            "grades": [dict(row) for row in rows],
        }
    )
