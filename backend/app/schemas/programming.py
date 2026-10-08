from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CodeSubmissionRequest(BaseModel):
    language: str = "cpp17"
    source_code: str = Field(min_length=1, max_length=64 * 1024)

    @field_validator("language")
    @classmethod
    def only_cpp17(cls, value: str) -> str:
        if value != "cpp17":
            raise ValueError("only cpp17 is supported")
        return value


class PublicSample(BaseModel):
    input_data: str
    expected_output: str


class ProgrammingProblemView(BaseModel):
    assignment_id: int
    title: str
    statement: str
    input_description: str
    output_description: str
    time_limit_ms: int
    memory_limit_mb: int
    samples: list[PublicSample]


class CodeSubmissionCreated(BaseModel):
    submission_id: int
    version: int
    status: str = "QUEUED"


class CodeSubmissionResult(BaseModel):
    id: int
    assignment_id: int
    language: str
    version: int
    status: str
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    time_ms: int | None = None
    memory_kb: int | None = None
    executed_case_count: int
    passed_case_count: int
    compiler_output: str | None = None
