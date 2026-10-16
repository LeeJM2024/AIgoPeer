"""Teacher roster management. Imports are atomic and never reset existing passwords."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, hash_password, require_teacher
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.teacher import ClassInput, StudentImportInput, TopicInput, TopicUpdate
from app.services.teacher_workflow import audit

router = APIRouter()


@router.get("/topics", response_model=ApiResponse)
def teacher_topics(_: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)):
    rows = (
        db.execute(
            text("""SELECT t.*, (SELECT count(*) FROM topic_claims c WHERE c.topic_id=t.id) AS claim_count
        FROM topics t ORDER BY t.code""")
        )
        .mappings()
        .all()
    )
    return ApiResponse(data=[dict(r) for r in rows])


@router.post("/topics", response_model=ApiResponse, status_code=201)
def create_topic(
    payload: TopicInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    topic_id = db.execute(
        text("""INSERT INTO topics(code,chapter,name,description)
        VALUES (:code,:chapter,:name,:description) RETURNING id"""),
        payload.model_dump(),
    ).scalar_one()
    audit(db, teacher.id, "CREATE_TOPIC", "topic", topic_id, after=payload.model_dump())
    db.commit()
    return ApiResponse(data={"topic_id": topic_id})


def _editable_topic(db, topic_id):
    row = (
        db.execute(text("SELECT * FROM topics WHERE id=:id FOR UPDATE"), {"id": topic_id})
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "NOT_FOUND")
    if db.execute(
        text("SELECT EXISTS(SELECT 1 FROM topic_claims WHERE topic_id=:id)"), {"id": topic_id}
    ).scalar_one():
        raise HTTPException(409, "TOPIC_ALREADY_CLAIMED")
    return row


@router.put("/topics/{topic_id}", response_model=ApiResponse)
def update_topic(
    topic_id: int,
    payload: TopicUpdate,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    row = _editable_topic(db, topic_id)
    if row["updated_at"] != payload.expected_updated_at:
        raise HTTPException(409, "DRAFT_VERSION_CONFLICT")
    db.execute(
        text("""UPDATE topics SET code=:code,chapter=:chapter,name=:name,description=:description,
        updated_at=now() WHERE id=:id"""),
        {"id": topic_id, **payload.model_dump(exclude={"expected_updated_at"})},
    )
    audit(
        db,
        teacher.id,
        "UPDATE_TOPIC",
        "topic",
        topic_id,
        before=dict(row),
        after=payload.model_dump(),
    )
    db.commit()
    return ApiResponse(data={"topic_id": topic_id})


@router.delete("/topics/{topic_id}", response_model=ApiResponse)
def delete_topic(
    topic_id: int, teacher: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
):
    row = _editable_topic(db, topic_id)
    db.execute(text("DELETE FROM topics WHERE id=:id"), {"id": topic_id})
    audit(db, teacher.id, "DELETE_TOPIC", "topic", topic_id, before=dict(row))
    db.commit()
    return ApiResponse(data={"deleted": True})


@router.post("/classes", response_model=ApiResponse, status_code=201)
def create_class(
    payload: ClassInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    try:
        class_id = db.execute(
            text("""
            INSERT INTO classes(name, course_term) VALUES (:name, :course_term) RETURNING id
        """),
            payload.model_dump(),
        ).scalar_one()
        audit(db, teacher.id, "CREATE_CLASS", "class", class_id, after=payload.model_dump())
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "CLASS_ALREADY_EXISTS") from exc
    return ApiResponse(data={"class_id": class_id})


@router.put("/classes/{class_id}", response_model=ApiResponse)
def edit_class(
    class_id: int,
    payload: ClassInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    try:
        before = (
            db.execute(text("SELECT * FROM classes WHERE id = :id FOR UPDATE"), {"id": class_id})
            .mappings()
            .one_or_none()
        )
        if before is None:
            raise HTTPException(404, "CLASS_NOT_FOUND")
        db.execute(
            text("""UPDATE classes SET name = :name, course_term = :course_term,
                        updated_at = now() WHERE id = :id"""),
            {"id": class_id, **payload.model_dump()},
        )
        audit(db, teacher.id, "EDIT_CLASS", "class", class_id, dict(before), payload.model_dump())
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "CLASS_ALREADY_EXISTS") from exc
    return ApiResponse(data={"class_id": class_id})


@router.post("/classes/{class_id}/students/import", response_model=ApiResponse)
def import_students(
    class_id: int,
    payload: StudentImportInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    if not db.execute(
        text("SELECT id FROM classes WHERE id = :id FOR UPDATE"), {"id": class_id}
    ).scalar_one_or_none():
        raise HTTPException(404, "CLASS_NOT_FOUND")
    created = enrolled = 0
    try:
        for student in sorted(payload.students, key=lambda item: item.student_no):
            # Serializes simultaneous imports for the same account across different classes.
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:account, 0))"),
                {"account": student.student_no},
            )
            existing = (
                db.execute(
                    text("SELECT id, name, system_role FROM users WHERE student_no = :n"),
                    {"n": student.student_no},
                )
                .mappings()
                .one_or_none()
            )
            if existing:
                if existing["system_role"] != "STUDENT" or existing["name"] != student.name:
                    raise HTTPException(
                        409, {"code": "STUDENT_IDENTITY_CONFLICT", "student_no": student.student_no}
                    )
                user_id = existing["id"]
            else:
                if not student.password:
                    raise HTTPException(
                        422,
                        {"code": "NEW_STUDENT_PASSWORD_REQUIRED", "student_no": student.student_no},
                    )
                user_id = db.execute(
                    text("""
                    INSERT INTO users(student_no, name, password_hash, system_role)
                    VALUES (:number, :name, :hash, 'STUDENT') RETURNING id
                """),
                    {
                        "number": student.student_no,
                        "name": student.name,
                        "hash": hash_password(student.password),
                    },
                ).scalar_one()
                created += 1
            conflict = db.execute(
                text("""
                SELECT EXISTS(SELECT 1 FROM panel_reviewers pr JOIN review_panels p ON p.id=pr.panel_id
                    WHERE pr.reviewer_id=:user AND p.target_class_id=:class)
            """),
                {"user": user_id, "class": class_id},
            ).scalar_one()
            if conflict:
                raise HTTPException(409, "REVIEWER_CLASS_CONFLICT")
            result = db.execute(
                text("""
                INSERT INTO enrollments(user_id, class_id) VALUES (:user, :class)
                ON CONFLICT DO NOTHING RETURNING id
            """),
                {"user": user_id, "class": class_id},
            ).scalar_one_or_none()
            enrolled += result is not None
        audit(
            db,
            teacher.id,
            "IMPORT_STUDENTS",
            "class",
            class_id,
            after={
                "created_accounts": created,
                "new_enrollments": enrolled,
                "requested": len(payload.students),
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "STUDENT_IMPORT_CONFLICT") from exc
    return ApiResponse(
        data={
            "created_accounts": created,
            "new_enrollments": enrolled,
            "unchanged": len(payload.students) - enrolled,
        }
    )


@router.delete("/classes/{class_id}/students/{student_id}", response_model=ApiResponse)
def remove_enrollment(
    class_id: int,
    student_id: int,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    db.execute(text("SELECT id FROM classes WHERE id = :id FOR UPDATE"), {"id": class_id})
    # Membership changes cannot invalidate any saved panel or historical submission.
    in_use = db.execute(
        text("""
        SELECT EXISTS(SELECT 1 FROM panel_reviewers pr JOIN review_panels p ON p.id = pr.panel_id
                      WHERE pr.reviewer_id = :student AND p.reviewer_class_id = :class)
            OR EXISTS(SELECT 1 FROM submissions WHERE author_id = :student AND class_id = :class)
            OR EXISTS(SELECT 1 FROM code_submissions WHERE author_id = :student AND class_id = :class)
    """),
        {"student": student_id, "class": class_id},
    ).scalar_one()
    if in_use:
        raise HTTPException(409, "ENROLLMENT_IN_USE")
    removed = db.execute(
        text("DELETE FROM enrollments WHERE user_id = :u AND class_id = :c RETURNING id"),
        {"u": student_id, "c": class_id},
    ).scalar_one_or_none()
    if removed is None:
        raise HTTPException(404, "ENROLLMENT_NOT_FOUND")
    audit(db, teacher.id, "REMOVE_ENROLLMENT", "class", class_id, after={"student_id": student_id})
    db.commit()
    return ApiResponse(data={"removed": True})
