from pydantic import BaseModel, ConfigDict, field_validator

_REDIS_DB_MAX = 15
_REDIS_PORT_MAX = 65535
_REDIS_PORT_MIN = 1


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
        if not (_REDIS_PORT_MIN <= v <= _REDIS_PORT_MAX):
            msg = "Redis port must be 1-65535"
            raise ValueError(msg)
        return v

    @field_validator("db")
    @classmethod
    def _db_range(cls, v: int) -> int:
        if not (0 <= v <= _REDIS_DB_MAX):
            msg = "Redis db must be 0-15"
            raise ValueError(msg)
        return v
