from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    POSTGRES_DSN: str
    REDIS_URL: str
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    JWT_TTL_MIN: int = 60
    GCP_PROJECT: str
    VERTEX_LOCATION: str = "asia-south1"
    GEMINI_MODEL: str = "gemini-1.5-flash"
    INGEST_STREAM: str = "stream:ingest"
    DIRECTIVE_CHANNEL: str = "channel:directives"
    ALERT_CHANNEL: str = "channel:alerts"
    RATE_LIMIT_PER_MIN: int = 600
    GEMINI_API_KEY: str


settings = Settings()  # raises ValidationError on missing required vars — fail fast
