from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.student_submission import TopicClaimResponse, TopicSummary


def _require_visible_assignment(*, db: Session, assignment_id: int, student_id: int) -> int:
    class_id = db.execute(
        text(
            """
            SELECT assignment_class.class_id
            FROM assignments AS assignment
            JOIN assignment_classes AS assignment_class ON assignment_class.assignment_id = assignment.id
            JOIN enrollments AS enrollment ON enrollment.class_id = assignment_class.class_id
            WHERE assignment.id = :assignment_id
              AND assignment.status <> 'DRAFT'
              AND enrollment.user_id = :student_id
            ORDER BY assignment_class.class_id
            LIMIT 1
            """
        ),
        {"assignment_id": assignment_id, "student_id": student_id},
    ).scalar_one_or_none()
    if class_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")
    return int(class_id)


def _topic_summary(row: dict[str, object]) -> TopicSummary:
    return TopicSummary(
        id=int(row["id"]),
        code=str(row["code"]),
        chapter=str(row["chapter"]),
        name=str(row["name"]),
        description=str(row["description"]),
    )


def list_topics_for_assignment(*, db: Session, assignment_id: int, student_id: int) -> dict[str, object]:
    _require_visible_assignment(db=db, assignment_id=assignment_id, student_id=student_id)
    rows = db.execute(
        text(
            """
            SELECT topic.id, topic.code, topic.chapter, topic.name, topic.description,
                   topic_claim.id AS claim_id
            FROM topics AS topic
            LEFT JOIN topic_claims AS topic_claim
              ON topic_claim.topic_id = topic.id
             AND topic_claim.assignment_id = :assignment_id
             AND topic_claim.student_id = :student_id
            ORDER BY topic.code
            """
        ),
        {"assignment_id": assignment_id, "student_id": student_id},
    ).mappings().all()
    topics = [_topic_summary(row) for row in rows]
    claim = next((row for row in rows if row["claim_id"] is not None), None)
    return {
        "topics": [topic.model_dump() for topic in topics],
        "claim": {
            "id": int(claim["claim_id"]),
            "topic": _topic_summary(claim).model_dump(),
        }
        if claim is not None
        else None,
    }


def claim_topic(
    *, db: Session, assignment_id: int, student_id: int, topic_id: int
) -> TopicClaimResponse:
    _require_visible_assignment(db=db, assignment_id=assignment_id, student_id=student_id)
    topic = db.execute(
        text("SELECT id, code, chapter, name, description FROM topics WHERE id = :topic_id FOR SHARE"),
        {"topic_id": topic_id},
    ).mappings().one_or_none()
    if topic is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="VALIDATION_ERROR")

    existing_claim = db.execute(
        text(
            """
            SELECT id FROM topic_claims
            WHERE assignment_id = :assignment_id AND student_id = :student_id
            """
        ),
        {"assignment_id": assignment_id, "student_id": student_id},
    ).scalar_one_or_none()
    if existing_claim is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CONFLICT")

    try:
        claim_id = db.execute(
            text(
                """
                INSERT INTO topic_claims(assignment_id, student_id, topic_id)
                VALUES (:assignment_id, :student_id, :topic_id)
                RETURNING id
                """
            ),
            {"assignment_id": assignment_id, "student_id": student_id, "topic_id": topic_id},
        ).scalar_one()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CONFLICT") from exc
    return TopicClaimResponse(
        id=int(claim_id), assignment_id=assignment_id, topic=_topic_summary(topic)
    )
