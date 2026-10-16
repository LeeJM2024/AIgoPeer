import io
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.schemas.student_submission import ProjectManifest
from app.services.student.material_check_service import (
    ArchiveInspectionError,
    _inspect_archive,
    get_material_check,
)
from app.services.student.project_submission_service import (
    UploadContext,
    validate_archive_filename,
)


def build_manifest() -> ProjectManifest:
    return ProjectManifest.model_validate(
        {
            "ppt_path": "slides/lesson.pptx",
            "video_path": "video/lesson.mp4",
            "examples": [{"location": "PPT", "pages": [4, 6, 8]}],
            "source_paths": ["src/main.cpp"],
            "tests": [
                {"input_path": "tests/case1.in", "expected_path": "tests/case1.out"},
                {"input_path": "tests/case2.in", "expected_path": "tests/case2.out"},
                {"input_path": "tests/case3.in", "expected_path": "tests/case3.out"},
            ],
            "readme_path": "README.md",
        }
    )


def build_pptx(slide_count: int = 8) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as presentation:
        for index in range(1, slide_count + 1):
            presentation.writestr(f"ppt/slides/slide{index}.xml", "<slide />")
    return output.getvalue()


def write_valid_archive(path: Path, *, include_video: bool = True) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("slides/lesson.pptx", build_pptx())
        if include_video:
            archive.writestr("video/lesson.mp4", b"placeholder")
        archive.writestr("src/main.cpp", "int main() {}")
        archive.writestr("README.md", "run instructions")
        for index in range(1, 4):
            archive.writestr(f"tests/case{index}.in", "input")
            archive.writestr(f"tests/case{index}.out", "output")


def test_material_check_accepts_complete_archive_and_returns_video_warning(tmp_path: Path) -> None:
    archive_path = tmp_path / "submission.zip"
    write_valid_archive(archive_path)

    missing_items, warnings, details = _inspect_archive(
        archive_path=archive_path, manifest=build_manifest()
    )

    assert missing_items == []
    assert warnings == ["VIDEO_DURATION_UNCHECKED"]
    assert details["ppt_slide_count"] == 8
    assert details["declared_example_count"] == 3
    assert details["declared_test_count"] == 3


def test_material_check_rejects_path_traversal_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.txt", "unsafe")

    with pytest.raises(ArchiveInspectionError, match="unsafe path"):
        _inspect_archive(archive_path=archive_path, manifest=build_manifest())


def test_material_check_marks_missing_video_as_invalid_material(tmp_path: Path) -> None:
    archive_path = tmp_path / "missing-video.zip"
    write_valid_archive(archive_path, include_video=False)

    missing_items, _warnings, _details = _inspect_archive(
        archive_path=archive_path, manifest=build_manifest()
    )

    assert missing_items == ["VIDEO"]


def test_material_check_rejects_example_page_outside_ppt(tmp_path: Path) -> None:
    archive_path = tmp_path / "invalid-example-page.zip"
    write_valid_archive(archive_path)
    manifest_payload = build_manifest().model_dump()
    manifest_payload["examples"] = [{"location": "PPT", "pages": [4, 6, 99]}]
    manifest = ProjectManifest.model_validate(manifest_payload)

    missing_items, _warnings, _details = _inspect_archive(
        archive_path=archive_path, manifest=manifest
    )

    assert missing_items == ["EXAMPLES"]


def test_manifest_requires_three_declared_examples() -> None:
    with pytest.raises(ValueError, match="at least three examples"):
        ProjectManifest.model_validate(
            {
                **build_manifest().model_dump(),
                "examples": [{"location": "PPT", "pages": [4, 6]}],
            }
        )


def test_archive_filename_must_match_current_claim() -> None:
    context = UploadContext(
        assignment_id=1,
        class_id=1,
        student_id=101,
        claim_id=5,
        student_no="D101",
        student_name="学生01",
        topic_code="02",
    )

    assert validate_archive_filename(file_name="D101_学生01_02.zip", context=context) == "D101_学生01_02.zip"
    with pytest.raises(HTTPException) as exc_info:
        validate_archive_filename(file_name="D101_学生01_03.zip", context=context)
    assert exc_info.value.status_code == 422


class MaterialCheckDbResult:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row

    def mappings(self) -> "MaterialCheckDbResult":
        return self

    def one_or_none(self) -> dict[str, object]:
        return self.row


class MaterialCheckDb:
    def __init__(self) -> None:
        self.row = {
            "author_id": 101,
            "status": "VALID",
            "missing_items": [],
            "warnings": ["VIDEO_DURATION_UNCHECKED"],
            "details_json": {"ppt_slide_count": 8},
            "checked_at": None,
        }

    def execute(self, *_args, **_kwargs) -> MaterialCheckDbResult:
        return MaterialCheckDbResult(self.row)


def test_material_check_is_visible_only_to_author_or_teacher() -> None:
    db = MaterialCheckDb()
    with pytest.raises(HTTPException) as exc_info:
        get_material_check(db=db, submission_id=1, current_user_id=102, current_role="STUDENT")
    assert exc_info.value.status_code == 403

    result = get_material_check(db=db, submission_id=1, current_user_id=1, current_role="TEACHER")
    assert result["status"] == "VALID"
