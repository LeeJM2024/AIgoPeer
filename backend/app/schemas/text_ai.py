from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.video_ai import VideoAiSettingsInput


class TextAiSettingsInput(BaseModel):
    base_url: str = Field(default="https://api.deepseek.com", min_length=1, max_length=1000)
    model: str = Field(
        default="deepseek-flash", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$"
    )
    api_key: str | None = Field(default=None, max_length=4096)
    enabled: bool = True
    student_daily_limit: int = Field(default=30, ge=1, le=200)
    allow_full_solution: bool = False

    _url = field_validator("base_url")(VideoAiSettingsInput.valid_url.__func__)
    _key = field_validator("api_key")(VideoAiSettingsInput.valid_key.__func__)


class AssistantQuestion(BaseModel):
    conversation_id: UUID
    question: str = Field(min_length=1, max_length=3000)
    action: Literal[
        "question",
        "understand",
        "explain",
        "debug",
        "complexity",
        "hint",
        "example",
        "proof",
        "compare",
        "practice",
        "teaching",
    ] = "question"
    source_code: str = Field(default="", max_length=65536)
    selected_code: str = Field(default="", max_length=20000)
    submission_id: int | None = Field(default=None, gt=0)

    @field_validator("question")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("请输入问题")
        return value.strip()
