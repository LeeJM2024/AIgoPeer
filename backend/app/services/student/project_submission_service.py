from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.student_submission import ProjectManifest, ProjectSubmissionCreated

ARCHIVE_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class UploadContext:
    assignment_id: int
    class_id: int
    student_id: int
    claim_id: int
    student_no: str
    student_name: str
    topic_code: str


def get_upload_context(*, db: Session, assignment_id: int, student_id: int) -> UploadContext:
    assignment = db.execute(
        text(
            """
            SELECT assignment_class.class_id
            FROM assignments AS assignment
            JOIN assignment_classes AS assignment_class ON assignment_class.assignment_id = assignment.id
            JOIN enrollments AS enrollment ON enrollment.class_id = assignment_class.class_id
            WHERE assignment.id = :assignment_id
              AND assignment.type = 'FINAL_PROJECT'
              AND assignment.status IN ('PUBLISHED', 'SUBMITTING')
              AND enrollment.user_id = :student_id
            ORDER BY assignment_class.class_id
            LIMIT 1
            """
        ),
        {"assignment_id": assignment_id, "student_id": student_id},
    ).scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

    claim = db.execute(
        text(
            """
            SELECT topic_claim.id, student.student_no, student.name, topic.code
            FROM topic_claims AS topic_claim
            JOIN users AS student ON student.id = topic_claim.student_id
            JOIN topics AS topic ON topic.id = topic_claim.topic_id
            WHERE topic_claim.assignment_id = :assignment_id
              AND topic_claim.student_id = :student_id
            """
        ),
        {"assignment_id": assignment_id, "student_id": student_id},
    ).mappings().one_or_none()
    if claim is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="TOPIC_CLAIM_REQUIRED")
    return UploadContext(
        assignment_id=assignment_id,
        class_id=int(assignment),
        student_id=student_id,
        claim_id=int(claim["id"]),
        student_no=str(claim["student_no"]),
        student_name=str(claim["name"]),
        topic_code=str(claim["code"]),
    )


def validate_archive_filename(*, file_name: str | None, context: UploadContext) -> str:
    if file_name is None or not re.fullmatch(r"[^_]+_[^_]+_\d{2}\.zip", file_name):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="VALIDATION_ERROR")
    expected_name = f"{context.student_no}_{context.student_name}_{context.topic_code}.zip"
    if file_name != expected_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="VALIDATION_ERROR")
    return file_name


async def store_archive(
    *, upload_file, destination: Path, max_bytes: int
) -> tuple[int, str]:
    """Stream an archive to local development storage while enforcing its size cap."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with destination.open("xb") as stream:
            while chunk := await upload_file.read(ARCHIVE_CHUNK_SIZE):
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="VALIDATION_ERROR",
                    )
                digest.update(chunk)
                stream.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload_file.close()
    return size_bytes, digest.hexdigest()


def new_storage_path(*, storage_root: Path) -> tuple[str, Path]:
    storage_key = f"project-submissions/{secrets.token_urlsafe(24)}.zip"
    return storage_key, storage_root / storage_key


def create_pending_submission(
    *,
    db: Session,
    context: UploadContext,
    manifest: ProjectManifest,
    original_file_name: str,
    storage_key: str,
    size_bytes: int,
    checksum: str,
) -> ProjectSubmissionCreated:
    try:
        version = int(
            db.execute(
                text(
                    """
                    SELECT COALESCE(MAX(version), 0) + 1
                    FROM submissions
                    WHERE assignment_id = :assignment_id AND author_id = :student_id
                    """
                ),
                {"assignment_id": context.assignment_id, "student_id": context.student_id},
            ).scalar_one()
        )
        # A current submission becomes historical before the next version is inserted.
        db.execute(
            text(
                """
                UPDATE submissions
                SET is_current = FALSE, status = 'SUPERSEDED', updated_at = now()
                WHERE assignment_id = :assignment_id
                  AND author_id = :student_id
                  AND is_current = TRUE
                """
            ),
            {"assignment_id": context.assignment_id, "student_id": context.student_id},
        )
        submission_id = db.execute(
            text(
                """
                INSERT INTO submissions(
                  assignment_id, author_id, class_id, status, anonymous_token, submitted_at,
                  topic_claim_id, version, is_current, manifest_json
                ) VALUES (
                  :assignment_id, :student_id, :class_id, 'PENDING', :anonymous_token, now(),
                  :topic_claim_id, :version, TRUE, CAST(:manifest_json AS jsonb)
                )
                RETURNING id
                """
            ),
            {
                "assignment_id": context.assignment_id,
                "student_id": context.student_id,
                "class_id": context.class_id,
                "anonymous_token": secrets.token_urlsafe(12),
                "topic_claim_id": context.claim_id,
                "version": version,
                "manifest_json": json.dumps(manifest.model_dump(mode="json")),
            },
        ).scalar_one()
        db.execute(
            text(
                """
                INSERT INTO submission_files(
                  submission_id, file_kind, storage_key, file_name, size_bytes, checksum
                ) VALUES (
                  :submission_id, 'ZIP', :storage_key, :file_name, :size_bytes, :checksum
                )
                """
            ),
            {
                "submission_id": submission_id,
                "storage_key": storage_key,
                "file_name": original_file_name,
                "size_bytes": size_bytes,
                "checksum": checksum,
            },
        )
        db.execute(
            text("INSERT INTO material_checks(submission_id, status) VALUES (:submission_id, 'PENDING')"),
            {"submission_id": submission_id},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CONFLICT") from exc
    return ProjectSubmissionCreated(
        submission_id=int(submission_id), version=version, material_check_status="PENDING"
    )
