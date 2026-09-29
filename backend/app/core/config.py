from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AlgoPeer API"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://algopeer:change-me-before-demo@localhost:5432/algopeer"
    jwt_secret: str = "development-only-change-me"
    jwt_algorithm: str = "HS256"
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


settings = Settings()
