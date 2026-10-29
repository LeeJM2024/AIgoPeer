import re
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VideoAiSettingsInput(BaseModel):
    provider: Literal["qwen", "gemini"]
    base_url: str = Field(min_length=1, max_length=1000)
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    api_key: str | None = Field(default=None, max_length=4096)
    enabled: bool = True

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        value = value.strip().rstrip("/")
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or "{" in value
            or "}" in value
        ):
            raise ValueError("请填写完整的 HTTPS Base URL，不含密钥、查询参数或占位符")
        return value

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value):
        if value is None or not value.strip():
            return None
        value = value.strip()
        if re.search(r"[\s\x00-\x1f\x7f]", value):
            raise ValueError("API Key 不能包含空白或控制字符")
        return value


class VideoAnalysisInput(BaseModel):
    force: bool = False


class VideoEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(ge=0, allow_inf_nan=False)
    description: str = Field(min_length=1, max_length=2000)


class VideoAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rubric_item_id: int = Field(gt=0)
    suggested_score: Decimal = Field(ge=0, allow_inf_nan=False, decimal_places=2)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    rationale: str = Field(min_length=1, max_length=6000)
    evidence: list[VideoEvidence] = Field(max_length=20)


class VideoAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=12000)
    assessments: list[VideoAssessment] = Field(min_length=1, max_length=100)
