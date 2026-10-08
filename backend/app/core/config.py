from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AlgoPeer API"
    app_env: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api"
    database_url: str = (
        "postgresql+psycopg://algopeer:change-me-before-demo@localhost:5432/algopeer"
    )
    jwt_secret: str = "development-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    internal_api_token: str = ""
    cors_origins: str = "http://localhost:5173"
    ai_video_provider: str = ""
    ai_video_api_key: str = ""
    ai_video_base_url: str = ""
    ai_video_model: str = ""
    ai_video_enabled: bool = False
    storage_dir: Path = Path("storage")
    max_project_archive_bytes: int = 500 * 1024 * 1024
    redis_url: str = "redis://localhost:6379/0"
    judge_queue_name: str = "algopeer:judge:queue"
    judge_worker_concurrency: int = 1
    judge_work_volume: str = "algopeer-judge-work"
    judge_work_dir: Path = Path("/judge-work")
    judge_image: str = "algopeer-judge-cpp:latest"
    judge_source_limit_bytes: int = 64 * 1024
    judge_test_data_limit_bytes: int = 64 * 1024
    judge_time_limit_ms: int = 2000
    judge_total_time_limit_ms: int = 10000
    judge_memory_limit_mb: int = 256
    judge_output_limit_bytes: int = 1024 * 1024
    judge_compiler_output_limit_bytes: int = 4 * 1024

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.app_env == "production":
            unsafe = {"development-only-change-me", "replace-this-with-a-long-random-value"}
            if len(self.jwt_secret) < 32 or self.jwt_secret in unsafe:
                raise ValueError(
                    "production requires an independent JWT_SECRET of at least 32 characters"
                )
            if len(self.internal_api_token) < 32 or self.internal_api_token == self.jwt_secret:
                raise ValueError(
                    "production requires a separate INTERNAL_API_TOKEN of at least 32 characters"
                )
            if "change-me-before-demo" in self.database_url:
                raise ValueError("production cannot use the example database password")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
