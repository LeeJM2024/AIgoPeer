"""Validate ZIP metadata before reading an upload or a nested Office ZIP."""

import re
import stat
import unicodedata
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


class UnsafeArchive(ValueError):
    pass


def safe_archive_path(name: str) -> str:
    canonical = unicodedata.normalize("NFKC", name)
    path = PurePosixPath(canonical)
    if (
        not name
        or len(name) > 1000
        or "\\" in canonical
        or ":" in canonical
        or path.is_absolute()
        or ".." in path.parts
        or any(unicodedata.category(char).startswith("C") for char in name)
    ):
        raise UnsafeArchive("UNSAFE_ARCHIVE_PATH")
    return PurePosixPath(name).as_posix()


def inspect_zip(
    archive: ZipFile,
    *,
    total_limit=1024 * 1024 * 1024,
    entry_limit=500 * 1024 * 1024,
    count_limit=1000,
):
    infos = archive.infolist()
    if len(infos) > count_limit:
        raise UnsafeArchive("TOO_MANY_ARCHIVE_ENTRIES")
    total = 0
    seen = set()
    for info in infos:
        if info.orig_filename != info.filename:
            raise UnsafeArchive("UNSAFE_ARCHIVE_PATH")
        name = safe_archive_path(info.filename)
        canonical = unicodedata.normalize("NFKC", name).casefold()
        if canonical in seen:
            raise UnsafeArchive("DUPLICATE_ARCHIVE_PATH")
        seen.add(canonical)
        if stat.S_ISLNK(info.external_attr >> 16):
            raise UnsafeArchive("SYMLINK_ARCHIVE_ENTRY")
        if info.flag_bits & 1 or info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
            raise UnsafeArchive("UNSUPPORTED_ARCHIVE_ENCODING")
        total += info.file_size
        if info.file_size > entry_limit or total > total_limit:
            raise UnsafeArchive("ARCHIVE_TOO_LARGE")
        if info.file_size and info.file_size / max(1, info.compress_size) > 100:
            raise UnsafeArchive("SUSPICIOUS_COMPRESSION_RATIO")
    return infos


def inspect_office(archive: ZipFile):
    infos = inspect_zip(
        archive, total_limit=128 * 1024 * 1024, entry_limit=32 * 1024 * 1024, count_limit=2000
    )
    for info in infos:
        name = info.filename.casefold()
        if "vbaproject" in name or "/activex/" in name or "/embeddings/" in name:
            raise UnsafeArchive("ACTIVE_OFFICE_CONTENT")
        if name.endswith((".xml", ".rels")):
            content = archive.read(info).lower().replace(b"\x00", b"")
            if any(
                marker in content
                for marker in (b"vbaproject", b"macroenabled", b"oleobject", b"activex")
            ):
                raise UnsafeArchive("ACTIVE_OFFICE_CONTENT")
            if b"<!doctype" in content or b"<!entity" in content:
                raise UnsafeArchive("UNSAFE_OFFICE_XML")
            if name.endswith(".rels") and re.search(
                rb"targetmode\s*=\s*['\"]external['\"]", content
            ):
                raise UnsafeArchive("EXTERNAL_OFFICE_RELATIONSHIP")
    return infos
