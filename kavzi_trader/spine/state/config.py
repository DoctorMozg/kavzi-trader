from pydantic import BaseModel, ConfigDict


class RedisConfigSchema(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    retry_attempts: int = 3
    retry_backoff_s: float = 0.5

    model_config = ConfigDict(frozen=True)
