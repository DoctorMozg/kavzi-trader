from pydantic import BaseModel, ConfigDict


class EMAPeriodsSchema(BaseModel):
    short: int = 20
    medium: int = 50
    long: int = 200

    model_config = ConfigDict(frozen=True)


class MACDParamsSchema(BaseModel):
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9

    model_config = ConfigDict(frozen=True)


class BollingerParamsSchema(BaseModel):
    period: int = 20
    std_dev: float = 2.0

    model_config = ConfigDict(frozen=True)


class IndicatorConfigSchema(BaseModel):
    ema_periods: EMAPeriodsSchema = EMAPeriodsSchema()
    rsi_period: int = 14
    macd_params: MACDParamsSchema = MACDParamsSchema()
    bollinger_params: BollingerParamsSchema = BollingerParamsSchema()
    atr_period: int = 14
    volume_period: int = 20

    model_config = ConfigDict(frozen=True)
