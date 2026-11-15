from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class SignalBracketSchema(BaseModel):
    """Stop and target in ATRs plus a time limit, for labelling sampled bars."""

    sl_atr: Annotated[float, Field(gt=0)]
    tp_atr: Annotated[float, Field(gt=0)]
    horizon_bars: Annotated[int, Field(ge=1)]

    model_config = ConfigDict(frozen=True)

    @classmethod
    def parse(cls, text: str) -> SignalBracketSchema:
        """Parse ``SL:TP:BARS``, e.g. ``1.5:3:96``."""
        parts = text.split(":")
        if len(parts) != 3:  # noqa: PLR2004 - the three bracket fields
            msg = f"bracket must be SL:TP:BARS, got {text!r}"
            raise ValueError(msg)
        return cls.model_validate(
            {"sl_atr": parts[0], "tp_atr": parts[1], "horizon_bars": parts[2]}
        )

    @property
    def label(self) -> str:
        return f"{self.sl_atr:g}/{self.tp_atr:g} ATR, {self.horizon_bars} bars"
