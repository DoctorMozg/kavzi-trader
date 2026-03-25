from pydantic import BaseModel, ConfigDict, field_validator


class RedisConfigSchema(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    retry_attempts: int = 3
    retry_backoff_s: float = 0.5

    model_config = ConfigDict(frozen=True)

    @field_validator("port")
    @classmethod
    def _port_range(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            msg = "Redis port must be 1-65535"
            raise ValueError(msg)
        return v

    @field_validator("db")
    @classmethod
    def _db_range(cls, v: int) -> int:
        if not (0 <= v <= 15):
            msg = "Redis db must be 0-15"
            raise ValueError(msg)
        return v
