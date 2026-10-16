import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core.config import settings
from app.services.student.review_anonymization_service import (
    AnonymizationError,
    build_anonymous_review_archive,
)


def test_anonymous_archive_replaces_names_and_excludes_undeclared_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    source = tmp_path / "S001_张三_topic.zip"
    with ZipFile(source, "w") as archive:
        archive.writestr("张三/readme.md", "algorithm notes")
        archive.writestr("private.txt", "this must not be exposed")

    key = build_anonymous_review_archive(
        source_archive=source,
        author_name="张三",
        student_no="S001",
        allowed_paths={"张三/readme.md"},
    )

    with ZipFile(tmp_path / key) as archive:
        assert archive.namelist() == ["materials/001.md"]
        assert archive.read("materials/001.md") == b"algorithm notes"


def test_identity_marker_blocks_anonymous_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    source = tmp_path / "source.zip"
    with ZipFile(source, "w") as archive:
        archive.writestr("README.md", "作者：张三，学号 S001")

    with pytest.raises(AnonymizationError, match="IDENTITY_MARKER_DETECTED"):
        build_anonymous_review_archive(
            source_archive=source,
            author_name="张三",
            student_no="S001",
            allowed_paths={"README.md"},
        )
