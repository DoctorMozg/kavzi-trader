from typing import NotRequired, TypedDict


class DvolPage(TypedDict):
    """The ``result`` of Deribit's get_volatility_index_data."""

    # Rows of [open time ms, open, high, low, close].
    data: list[list[float]]
    # Older end timestamp to request next; null or absent on the last page.
    continuation: NotRequired[int | None]
