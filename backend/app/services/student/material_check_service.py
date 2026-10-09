from __future__ import annotations

import io
import json
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas.student_submission import ProjectManifest
from app.services.student.review_anonymization_service import (
    AnonymizationError,
    build_anonymous_review_archive,
)

MAX_ARCHIVE_ENTRIES = 1000
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".py",
    ".rs",
    ".ts",
}


@dataclass(frozen=True)
class ArchiveInspectionError(Exception):
    code: str
    message: str


def _normalise_zip_name(name: str) -> str:
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or ".." in path.parts:
        raise ArchiveInspectionError("UNSAFE_ARCHIVE_PATH", "archive contains an unsafe path")
    return path.as_posix()


def _inspect_archive(*, archive_path: Path, manifest: ProjectManifest) -> tuple[list[str], list[str], dict[str, Any]]:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise ArchiveInspectionError("TOO_MANY_ARCHIVE_ENTRIES", "archive has too many entries")

            files: dict[str, zipfile.ZipInfo] = {}
            total_uncompressed = 0
            for info in infos:
                name = _normalise_zip_name(info.filename)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ArchiveInspectionError("SYMLINK_ARCHIVE_ENTRY", "archive contains a symbolic link")
                if info.is_dir():
                    continue
                if name in files:
                    raise ArchiveInspectionError("DUPLICATE_ARCHIVE_PATH", "archive contains duplicate paths")
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise ArchiveInspectionError("ARCHIVE_TOO_LARGE", "archive expands beyond the allowed size")
                if info.file_size and (
                    not info.compress_size or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
                ):
                    raise ArchiveInspectionError("SUSPICIOUS_COMPRESSION_RATIO", "archive compression ratio is too high")
                files[name] = info
    except zipfile.BadZipFile as exc:
        raise ArchiveInspectionError("INVALID_ZIP", "archive is not a valid ZIP file") from exc

    missing_items: list[str] = []
    warnings: list[str] = ["VIDEO_DURATION_UNCHECKED"]
    if manifest.ppt_path not in files:
        missing_items.append("PPT")
    if manifest.video_path not in files:
        missing_items.append("VIDEO")
    if manifest.readme_path not in files:
        missing_items.append("README")
    if any(path not in files or PurePosixPath(path).suffix.lower() not in SOURCE_EXTENSIONS for path in manifest.source_paths):
        missing_items.append("CODE")
    if any(
        test.input_path not in files or test.expected_path not in files for test in manifest.tests
    ):
        missing_items.append("TESTS")
    if any(example.path not in files for example in manifest.examples if example.path is not None):
        missing_items.append("EXAMPLES")

    # Read only the declared PPT entry; no archive member is extracted to disk.
    ppt_slide_count: int | None = None
    if manifest.ppt_path in files:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                ppt_bytes = archive.read(manifest.ppt_path)
            with zipfile.ZipFile(io.BytesIO(ppt_bytes)) as presentation:
                ppt_slide_count = sum(
                    1
                    for name in presentation.namelist()
                    if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                )
            if not 8 <= ppt_slide_count <= 12:
                warnings.append("PPT_PAGE_COUNT_RECOMMENDED_8_TO_12")
            if any(
                example.location == "PPT" and max(example.pages) > ppt_slide_count
                for example in manifest.examples
            ):
                missing_items.append("EXAMPLES")
        except (KeyError, zipfile.BadZipFile):
            missing_items.append("PPT")

    details = {
        "archive_entry_count": len(files),
        "uncompressed_bytes": total_uncompressed,
        "declared_example_count": sum(example.declared_count for example in manifest.examples),
        "declared_test_count": len(manifest.tests),
        "ppt_slide_count": ppt_slide_count,
        "video_duration": "UNVERIFIED",
    }
    return sorted(set(missing_items)), warnings, details


def _record_result(
    *,
    db: Session,
    submission_id: int,
    status_value: str,
    missing_items: list[str],
    warnings: list[str],
    details: dict[str, Any],
) -> None:
    db.execute(
        text(
            """
            UPDATE material_checks
            SET status = :status, missing_items = CAST(:missing_items AS jsonb),
                warnings = CAST(:warnings AS jsonb), details_json = CAST(:details AS jsonb),
                checked_at = now()
            WHERE submission_id = :submission_id
            """
        ),
        {
            "submission_id": submission_id,
            "status": status_value,
            "missing_items": json.dumps(missing_items),
            "warnings": json.dumps(warnings),
            "details": json.dumps(details),
        },
    )
    db.execute(
        text("UPDATE submissions SET status = CASE WHEN is_current THEN :status ELSE 'SUPERSEDED' END, updated_at = now() WHERE id = :submission_id"),
        {"submission_id": submission_id, "status": status_value},
    )
    db.commit()


def _record_review_package(
    *, db: Session, submission_id: int, status_value: str, storage_key: str | None = None,
    failure_code: str | None = None, details: dict[str, Any] | None = None,
) -> None:
    db.execute(
        text(
            """INSERT INTO review_material_packages(submission_id,storage_key,status,failure_code,details_json)
               VALUES (:submission_id,:storage_key,:status,:failure_code,CAST(:details AS jsonb))
               ON CONFLICT(submission_id) DO UPDATE SET storage_key=EXCLUDED.storage_key,status=EXCLUDED.status,
                 failure_code=EXCLUDED.failure_code,details_json=EXCLUDED.details_json,updated_at=now()"""
        ),
        {
            "submission_id": submission_id,
            "storage_key": storage_key,
            "status": status_value,
            "failure_code": failure_code,
            "details": json.dumps(details or {}),
        },
    )


def run_material_check(submission_id: int) -> None:
    """Background entry point. Every result, including malformed ZIPs, is persisted."""
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT submission.manifest_json, submission_file.storage_key, user.name AS author_name,
                       user.student_no
                FROM submissions AS submission
                JOIN submission_files AS submission_file ON submission_file.submission_id = submission.id
                JOIN users AS user ON user.id = submission.author_id
                WHERE submission.id = :submission_id AND submission_file.file_kind = 'ZIP'
                """
            ),
            {"submission_id": submission_id},
        ).mappings().one()
        manifest = ProjectManifest.model_validate(row["manifest_json"])
        missing_items, warnings, details = _inspect_archive(
            archive_path=settings.storage_dir / str(row["storage_key"]), manifest=manifest
        )
        if not missing_items:
            try:
                review_key = build_anonymous_review_archive(
                    source_archive=settings.storage_dir / str(row["storage_key"]),
                    author_name=str(row["author_name"]),
                    student_no=str(row["student_no"]),
                    allowed_paths={
                        manifest.ppt_path,
                        manifest.video_path,
                        manifest.readme_path,
                        *manifest.source_paths,
                        *(example.path for example in manifest.examples if example.path),
                        *(test.input_path for test in manifest.tests),
                        *(test.expected_path for test in manifest.tests),
                    },
                )
                _record_review_package(
                    db=db, submission_id=submission_id, status_value="READY", storage_key=review_key
                )
            except AnonymizationError as exc:
                _record_review_package(
                    db=db, submission_id=submission_id, status_value="FAILED", failure_code=exc.code
                )
                _record_result(
                    db=db,
                    submission_id=submission_id,
                    status_value="INVALID",
                    missing_items=["ANONYMIZATION"],
                    warnings=[],
                    details={"error_code": exc.code},
                )
                return
        _record_result(
            db=db,
            submission_id=submission_id,
            status_value="VALID" if not missing_items else "INVALID",
            missing_items=missing_items,
            warnings=warnings,
            details=details,
        )
    except ArchiveInspectionError as exc:
        _record_result(
            db=db,
            submission_id=submission_id,
            status_value="INVALID",
            missing_items=["ARCHIVE"],
            warnings=[],
            details={"error_code": exc.code, "message": exc.message},
        )
    except Exception as exc:  # noqa: BLE001 - background failures must be persisted for the student.
        db.rollback()
        _record_result(
            db=db,
            submission_id=submission_id,
            status_value="INVALID",
            missing_items=["MATERIAL_CHECK_FAILED"],
            warnings=[],
            details={"error_code": "MATERIAL_CHECK_FAILED", "message": str(exc)},
        )
    finally:
        db.close()


def get_material_check(*, db: Session, submission_id: int, current_user_id: int, current_role: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT submission.author_id, material_check.status, material_check.missing_items,
                   material_check.warnings, material_check.details_json, material_check.checked_at
            FROM submissions AS submission
            JOIN material_checks AS material_check ON material_check.submission_id = submission.id
            WHERE submission.id = :submission_id
            """
        ),
        {"submission_id": submission_id},
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")
    if current_role != "TEACHER" and int(row["author_id"]) != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    return {
        "status": row["status"],
        "missing_items": row["missing_items"],
        "warnings": row["warnings"],
        "details": row["details_json"],
        "checked_at": row["checked_at"],
    }
