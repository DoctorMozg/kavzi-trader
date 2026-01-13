from kavzi_trader.api.common.models import CandlestickSchema
from kavzi_trader.indicators.base import candles_to_dataframe
from kavzi_trader.indicators.config import IndicatorConfigSchema
from kavzi_trader.indicators.momentum import calculate_macd, calculate_rsi
from kavzi_trader.indicators.schemas import TechnicalIndicatorsSchema
from kavzi_trader.indicators.trend import calculate_ema, calculate_sma
from kavzi_trader.indicators.volatility import calculate_atr, calculate_bollinger_bands
from kavzi_trader.indicators.volume import calculate_volume_analysis


class TechnicalIndicatorCalculator:
    """
    Orchestrates calculation of all technical indicators from candlestick data.

    This class provides a single entry point for computing a complete technical
    analysis snapshot from raw OHLCV data.
    """

    def __init__(self, config: IndicatorConfigSchema | None = None) -> None:
        self.config = config or IndicatorConfigSchema()

    def calculate(
        self,
        candles: list[CandlestickSchema],
    ) -> TechnicalIndicatorsSchema | None:
        """
        Calculate all technical indicators from candlestick data.

        Args:
            candles: List of candlestick data (must be sorted by time, oldest first)

        Returns:
            TechnicalIndicatorsSchema with all calculated indicators,
            or None if no candles provided
        """
        if not candles:
            return None

        ohlcv = candles_to_dataframe(candles)

        if ohlcv.empty:
            return None

        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]
        volume = ohlcv["volume"]

        cfg = self.config

        return TechnicalIndicatorsSchema(
            ema_20=calculate_ema(close, cfg.ema_periods.short),
            ema_50=calculate_ema(close, cfg.ema_periods.medium),
            ema_200=calculate_ema(close, cfg.ema_periods.long),
            sma_20=calculate_sma(close, cfg.ema_periods.short),
            rsi_14=calculate_rsi(close, cfg.rsi_period),
            macd=calculate_macd(
                close,
                cfg.macd_params.fast_period,
                cfg.macd_params.slow_period,
                cfg.macd_params.signal_period,
            ),
            bollinger=calculate_bollinger_bands(
                close,
                cfg.bollinger_params.period,
                cfg.bollinger_params.std_dev,
            ),
            atr_14=calculate_atr(high, low, close, cfg.atr_period),
            volume=calculate_volume_analysis(close, volume, cfg.volume_period),
            timestamp=candles[-1].close_time,
        )
