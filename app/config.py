from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SpendSense"
    secret_key: str = "dev-stage1-placeholder-secret"
    gemini_api_key: str = ""
    database_url: str = "sqlite:///./spendsense.db"
    environment: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
