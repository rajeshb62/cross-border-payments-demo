from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://payments:payments@localhost:5432/cross_border_payments"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"

    # Wise API (INR→USD FX leg)
    WISE_API_KEY: str = "stub-key"
    WISE_API_URL: str = "https://api.transferwise.com"

    # Airwallex (LOCAL rail USD delivery, replaces SWIFT)
    AIRWALLEX_CLIENT_ID: str = "stub-client-id"
    AIRWALLEX_API_KEY: str = "stub-airwallex-key"
    AIRWALLEX_WEBHOOK_SECRET: str = "stub-webhook-secret"

    # FX
    RATE_LOCK_TTL_SECONDS: int = 90
    STUB_FX_RATE: float = 83.5  # INR per 1 USD

    # Compliance
    MAX_LRS_LIMIT_USD: float = 250_000.0
    TCS_THRESHOLD_INR: float = 700_000.0

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-this-in-production"
    LOG_LEVEL: str = "INFO"


settings = Settings()
