import pytest

from kavzi_trader.news.coin_tagger import CoinTagger


@pytest.mark.parametrize(
    ("title", "coins"),
    [
        ("Bitcoin tops $90K as ETH lags", ("BTC", "ETH")),
        ("Solana and Cardano ETFs filed", ("SOL", "ADA")),
        ("Ripple wins appeal; XRP jumps", ("XRP",)),
        ("Chainlink oracles come to Avalanche", ("LINK", "AVAX")),
        ("BNB Chain upgrade goes live", ("BNB",)),
    ],
)
def test_tags_names_and_tickers(title: str, coins: tuple[str, ...]) -> None:
    assert CoinTagger().tag([title]) == coins


def test_lowercase_ticker_words_are_not_coins() -> None:
    title = "Exchange will link accounts, sol traders and ada users say"

    assert CoinTagger().tag([title]) == ()


def test_categories_count_as_text() -> None:
    assert CoinTagger().tag(["Weekly wrap", "Ethereum"]) == ("ETH",)
