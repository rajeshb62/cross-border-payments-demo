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
    FX_RATE_LOCK_TTL_SECONDS: int = 120

    # Fee
    PLATFORM_FEE_RATE: float = 0.015  # 1.5%

    # OPGSP cap (RBI PA-CB limit per transaction)
    OPGSP_CAP_USD: float = 10000.0

    # Webhook security
    WEBHOOK_SECRET: str = "demo-webhook-secret"

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"


settings = Settings()
