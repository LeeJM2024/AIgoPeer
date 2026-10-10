"""Create a fail-closed, reviewer-safe derivative of a project archive."""

from __future__ import annotations

import io
import secrets
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from app.core.config import settings

TEXT_EXTENSIONS = {".c", ".cc", ".cpp", ".cxx", ".cs", ".go", ".h", ".hpp", ".java", ".js", ".py", ".rs", ".ts", ".md", ".txt", ".in", ".out", ".json", ".csv"}
OFFICE_EXTENSIONS = {".pptx", ".docx", ".xlsx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}


@dataclass(frozen=True)
class AnonymizationError(Exception):
    code: str


def _contains_identity(data: bytes, markers: list[str]) -> bool:
    text = data.decode("utf-8", errors="ignore").casefold()
    return any(marker and marker.casefold() in text for marker in markers)


def _safe_office_bytes(data: bytes, markers: list[str]) -> bytes:
    try:
        output = io.BytesIO()
        with ZipFile(io.BytesIO(data)) as source, ZipFile(output, "w", ZIP_DEFLATED) as target:
            for info in source.infolist():
                name = PurePosixPath(info.filename).as_posix()
                if name.startswith("docProps/"):
                    continue
                contents = source.read(info)
                if name.endswith((".xml", ".rels")) and _contains_identity(contents, markers):
                    raise AnonymizationError("IDENTITY_MARKER_DETECTED")
                target.writestr(name, contents)
        return output.getvalue()
    except BadZipFile as exc:
        raise AnonymizationError("UNSAFE_OFFICE_DOCUMENT") from exc


def _safe_image_bytes(data: bytes) -> bytes:
    try:
        from PIL import Image

        source = Image.open(io.BytesIO(data))
        output = io.BytesIO()
        image = source.convert("RGBA") if source.mode not in {"RGB", "RGBA"} else source
        image.save(output, format="PNG")
        return output.getvalue()
    except Exception as exc:  # Pillow rejects malformed or unsupported image data.
        raise AnonymizationError("UNSAFE_IMAGE_METADATA") from exc


def _safe_video_file(source: Path, destination: Path) -> None:
    try:
        subprocess.run(
            [settings.ffmpeg_bin, "-y", "-v", "error", "-i", str(source), "-map", "0", "-map_metadata", "-1", "-c", "copy", str(destination)],
            check=True,
            capture_output=True,
            timeout=settings.anonymization_command_timeout_seconds,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise AnonymizationError("ANONYMIZATION_VIDEO_TOOL_FAILED") from exc


def build_anonymous_review_archive(
    *, source_archive: Path, author_name: str, student_no: str, allowed_paths: set[str]
) -> str:
    """Return a storage-relative key for a freshly built, metadata-free archive.

    File names are intentionally replaced rather than copied.  Opaque formats
    are rejected; a review task may only expose material that this service has
    explicitly processed.
    """
    markers = [author_name.strip(), student_no.strip()]
    root = settings.storage_dir.resolve()
    package_dir = root / "review-materials"
    package_dir.mkdir(parents=True, exist_ok=True)
    destination = package_dir / f"{secrets.token_urlsafe(24)}.zip"
    try:
        with tempfile.TemporaryDirectory(prefix="algopeer-anon-") as temporary:
            work = Path(temporary)
            with ZipFile(source_archive) as source, ZipFile(destination, "x", ZIP_DEFLATED) as target:
                file_index = 0
                for info in source.infolist():
                    if info.is_dir():
                        continue
                    path = PurePosixPath(info.filename)
                    # Never pass through undeclared files: an archive can contain
                    # private drafts or identity-bearing side files that are not
                    # part of the assessed work.
                    if path.as_posix() not in allowed_paths:
                        continue
                    suffix = path.suffix.lower()
                    if suffix not in TEXT_EXTENSIONS | OFFICE_EXTENSIONS | IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                        raise AnonymizationError("UNSUPPORTED_REVIEW_MATERIAL_FORMAT")
                    file_index += 1
                    extension = ".png" if suffix in IMAGE_EXTENSIONS else suffix
                    safe_name = f"materials/{file_index:03d}{extension}"
                    if suffix in VIDEO_EXTENSIONS:
                        input_path = work / f"source-{file_index}{suffix}"
                        output_path = work / f"review-{file_index}.mp4"
                        with source.open(info) as input_stream, input_path.open("wb") as output_stream:
                            shutil.copyfileobj(input_stream, output_stream, 1024 * 1024)
                        _safe_video_file(input_path, output_path)
                        target.write(output_path, safe_name)
                        continue
                    contents = source.read(info)
                    if suffix in TEXT_EXTENSIONS:
                        if _contains_identity(contents, markers):
                            raise AnonymizationError("IDENTITY_MARKER_DETECTED")
                    elif suffix in OFFICE_EXTENSIONS:
                        contents = _safe_office_bytes(contents, markers)
                    elif suffix in IMAGE_EXTENSIONS:
                        contents = _safe_image_bytes(contents)
                    target.writestr(safe_name, contents)
        return destination.relative_to(root).as_posix()
    except (BadZipFile, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise AnonymizationError("ANONYMIZATION_FAILED") from exc
    except Exception:
        destination.unlink(missing_ok=True)
        raise
