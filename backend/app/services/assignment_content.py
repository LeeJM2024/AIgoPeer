"""Teacher-owned statements and knowledge-point tags, frozen on publication."""

from fastapi import HTTPException
from sqlalchemy import text

SUBJECTIVE_TYPES = {"ALGORITHM_ANALYSIS", "PROOF", "OPEN_ENDED"}


def save_assignment_content(db, assignment_id, statement, topic_ids):
    existing = set(
        db.execute(text("SELECT id FROM topics WHERE id=ANY(:ids)"), {"ids": topic_ids}).scalars()
    )
    if existing != set(topic_ids):
        raise HTTPException(422, "TOPIC_NOT_FOUND")
    db.execute(
        text("UPDATE assignments SET statement=:s WHERE id=:id"),
        {"s": statement, "id": assignment_id},
    )
    db.execute(text("DELETE FROM assignment_topics WHERE assignment_id=:id"), {"id": assignment_id})
    for topic_id in topic_ids:
        db.execute(
            text("INSERT INTO assignment_topics VALUES (:a,:t)"),
            {"a": assignment_id, "t": topic_id},
        )


def assignment_topics(db, assignment_id):
    return [
        dict(row)
        for row in db.execute(
            text("""
        SELECT t.id,t.code,t.name,t.chapter FROM topics t
        JOIN assignment_topics x ON x.topic_id=t.id WHERE x.assignment_id=:id ORDER BY t.code
    """),
            {"id": assignment_id},
        ).mappings()
    ]
