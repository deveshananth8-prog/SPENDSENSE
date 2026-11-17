from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

GEMINI_MODEL = "gemini-4-hydrogen"


class Settings(BaseSettings):
    app_name: str = "SpendSense"
    secret_key: str = "dev-stage2-change-me-in-production"
    gemini_api_key: str = ""
    gemini_model: str = GEMINI_MODEL
    gemini_timeout_ms: int = 10_000
    gemini_max_retries: int = 1
    ai_max_image_bytes: int = 4 * 1024 * 1024
    database_url: str = "sqlite:///./spendsense.db"
    environment: str = "development"
    upload_dir: str = "uploads/avatars"
    demo_ttl_minutes: int = 120
    session_max_age_seconds: int = 60 * 60 * 24 * 7  # 7 days

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def avatar_upload_path(self) -> Path:
        return Path(self.upload_dir)


settings = Settings()

