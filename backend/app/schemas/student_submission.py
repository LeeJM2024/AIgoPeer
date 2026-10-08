from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def validate_archive_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise ValueError("archive paths must be non-empty relative POSIX paths")
    return value


class TopicClaimRequest(BaseModel):
    topic_id: int = Field(gt=0)


class TopicSummary(BaseModel):
    id: int
    code: str
    chapter: str
    name: str
    description: str


class TopicClaimResponse(BaseModel):
    id: int
    assignment_id: int
    topic: TopicSummary


class ExampleReference(BaseModel):
    location: Literal["PPT", "FILE"]
    pages: list[int] = Field(default_factory=list)
    path: str | None = None
    count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_location_details(self) -> ExampleReference:
        if self.location == "PPT":
            if not self.pages or any(page < 1 for page in self.pages):
                raise ValueError("PPT examples require one or more positive page numbers")
            if self.path is not None or self.count is not None:
                raise ValueError("PPT examples use pages and do not accept path or count")
        elif self.path is None or self.count is None:
            raise ValueError("FILE examples require path and count")
        return self

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        return validate_archive_path(value) if value is not None else None

    @property
    def declared_count(self) -> int:
        return len(self.pages) if self.location == "PPT" else self.count or 0


class TestReference(BaseModel):
    input_path: str
    expected_path: str

    _validate_input_path = field_validator("input_path")(validate_archive_path)
    _validate_expected_path = field_validator("expected_path")(validate_archive_path)


class ProjectManifest(BaseModel):
    ppt_path: str
    video_path: str
    examples: list[ExampleReference] = Field(min_length=1)
    source_paths: list[str] = Field(min_length=1)
    tests: list[TestReference] = Field(min_length=3)
    readme_path: str

    _validate_ppt_path = field_validator("ppt_path")(validate_archive_path)
    _validate_video_path = field_validator("video_path")(validate_archive_path)
    _validate_readme_path = field_validator("readme_path")(validate_archive_path)

    @field_validator("source_paths")
    @classmethod
    def validate_source_paths(cls, values: list[str]) -> list[str]:
        return [validate_archive_path(value) for value in values]

    @model_validator(mode="after")
    def validate_required_extensions_and_examples(self) -> ProjectManifest:
        if not self.ppt_path.lower().endswith(".pptx"):
            raise ValueError("ppt_path must point to a .pptx file")
        if not self.video_path.lower().endswith(".mp4"):
            raise ValueError("video_path must point to an .mp4 file")
        if sum(example.declared_count for example in self.examples) < 3:
            raise ValueError("at least three examples must be declared")
        if PurePosixPath(self.readme_path).name.lower() not in {"readme", "readme.md", "readme.txt"}:
            raise ValueError("readme_path must point to a README file")
        return self


class ProjectSubmissionCreated(BaseModel):
    submission_id: int
    version: int
    material_check_status: Literal["PENDING"]


class MaterialCheckResult(BaseModel):
    status: Literal["PENDING", "VALID", "INVALID", "RETURNED"]
    missing_items: list[str]
    warnings: list[str]
    details: dict[str, Any]
    checked_at: datetime | None = None
