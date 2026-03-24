from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://payments:payments@localhost:5432/cross_border_payments"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"

    # FX API
    FRANKFURTER_API_URL: str = "https://api.frankfurter.app"
    FX_CACHE_TTL_SECONDS: int = 60

    # Fee
    PLATFORM_FEE_RATE: float = 0.015  # 1.5%

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"


settings = Settings()
