from pydantic import BaseModel, ConfigDict

from kavzi_trader.domain.algorithm_confluence import DualConfluenceSchema
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.domain.indicator_schemas import TechnicalIndicatorsSchema
from kavzi_trader.order_flow.schemas import OrderFlowSchema


class AnalysisContextSchema(BaseModel):
    """Market inputs shared by the Analyst and Trader dependency builders."""

    indicators: TechnicalIndicatorsSchema
    candles: list[CandlestickSchema]
    order_flow: OrderFlowSchema | None
    confluence: DualConfluenceSchema

    model_config = ConfigDict(frozen=True)
