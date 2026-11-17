from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# A date-only stamp may be in US Eastern time, so the article can appear up to
# ~29h after that UTC midnight; treat it as unseen until then.
DAY_PRECISION_DELAY = timedelta(hours=30)


class NewsItemSchema(BaseModel):
    """One headline, stored as first seen so later edits can't leak hindsight."""

    model_config = ConfigDict(frozen=True)

    url: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    source: str
    published_at: AwareDatetime
    precision: Literal["exact", "day"]
    first_seen_at: AwareDatetime
    coins: tuple[str, ...] = ()

    def available_at(self, lag: timedelta) -> datetime:
        """Earliest time a point-in-time reader may see this item."""
        delay = DAY_PRECISION_DELAY if self.precision == "day" else timedelta(0)
        return self.published_at + delay + lag
