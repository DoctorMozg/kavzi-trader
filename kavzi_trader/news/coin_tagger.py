import re
from collections.abc import Iterable

# Names match in any case; tickers only as uppercase words, since "link",
# "sol" and "ada" are ordinary words in lowercase.
COIN_ALIASES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "BTC": (("bitcoin",), ("BTC",)),
    "ETH": (("ethereum", "ether"), ("ETH",)),
    "SOL": (("solana",), ("SOL",)),
    "XRP": (("ripple", "xrp"), ("XRP",)),
    "BNB": (("bnb chain", "binance coin"), ("BNB",)),
    "ADA": (("cardano",), ("ADA",)),
    "LINK": (("chainlink",), ("LINK",)),
    "AVAX": (("avalanche",), ("AVAX",)),
}


class CoinTagger:
    """Tags text with the coins it mentions, by name or ticker."""

    def __init__(
        self,
        aliases: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = COIN_ALIASES,
    ) -> None:
        self._patterns = {
            coin: (
                re.compile(
                    r"\b(?:" + "|".join(map(re.escape, names)) + r")\b", re.IGNORECASE
                ),
                re.compile(r"\b(?:" + "|".join(map(re.escape, tickers)) + r")\b"),
            )
            for coin, (names, tickers) in aliases.items()
        }

    def tag(self, texts: Iterable[str]) -> tuple[str, ...]:
        text = " ".join(texts)
        return tuple(
            coin
            for coin, (by_name, by_ticker) in self._patterns.items()
            if by_name.search(text) or by_ticker.search(text)
        )
