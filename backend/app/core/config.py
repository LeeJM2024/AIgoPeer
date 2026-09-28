from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AlgoPeer API"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://algopeer:change-me-before-demo@localhost:5432/algopeer"
    jwt_secret: str = "development-only-change-me"
    jwt_algorithm: str = "HS256"


settings = Settings()
