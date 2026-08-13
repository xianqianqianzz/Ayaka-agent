from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Ayaka AI Platform"
    database_url: str = "postgresql+asyncpg://ayaka:ayaka@localhost:5432/ayaka"
    secret_key: str = "change-me"


settings = Settings()
