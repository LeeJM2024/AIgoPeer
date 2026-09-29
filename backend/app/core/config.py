from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AlgoPeer API"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://algopeer:change-me-before-demo@localhost:5432/algopeer"
    jwt_secret: str = "development-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    cors_origins: str = "http://localhost:5173"
    ai_video_provider: str = ""
    ai_video_api_key: str = ""
    ai_video_base_url: str = ""
    ai_video_model: str = ""
    ai_video_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
