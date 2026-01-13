from pydantic import BaseModel, ConfigDict


class RedisConfigSchema(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None

    model_config = ConfigDict(frozen=True)
