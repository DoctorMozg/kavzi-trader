from unittest.mock import patch

from kavzi_trader.external.config import ExternalSourcesConfigSchema
from kavzi_trader.external.sources import build_enabled_sources
from kavzi_trader.external.sources.cryptopanic import CryptoPanicSource
from kavzi_trader.external.sources.deribit_dvol import DeribitDvolSource
from kavzi_trader.external.sources.fear_greed import FearGreedSource


def test_default_config_builds_deribit_and_fgi() -> None:
    config = ExternalSourcesConfigSchema()
    sources = build_enabled_sources(config)
    names = [s.name for s in sources]
    assert "deribit_dvol" in names
    assert "fear_greed" in names
    assert "cryptopanic" not in names


def test_all_disabled() -> None:
    config = ExternalSourcesConfigSchema.model_validate(
        {
            "deribit_dvol": {"enabled": False},
            "fear_greed": {"enabled": False},
            "cryptopanic": {"enabled": False},
        },
    )
    sources = build_enabled_sources(config)
    assert len(sources) == 0


@patch.dict("os.environ", {"KT_CRYPTOPANIC_API_KEY": "test-key-123"})
def test_cryptopanic_enabled_with_key() -> None:
    config = ExternalSourcesConfigSchema.model_validate(
        {"cryptopanic": {"enabled": True}},
    )
    sources = build_enabled_sources(config)
    names = [s.name for s in sources]
    assert "cryptopanic" in names
    cp = next(s for s in sources if s.name == "cryptopanic")
    assert isinstance(cp, CryptoPanicSource)


@patch.dict("os.environ", {"KT_CRYPTOPANIC_API_KEY": ""})
def test_cryptopanic_enabled_without_key() -> None:
    config = ExternalSourcesConfigSchema.model_validate(
        {"cryptopanic": {"enabled": True}},
    )
    sources = build_enabled_sources(config)
    names = [s.name for s in sources]
    assert "cryptopanic" not in names


def test_source_types() -> None:
    config = ExternalSourcesConfigSchema()
    sources = build_enabled_sources(config)
    assert any(isinstance(s, DeribitDvolSource) for s in sources)
    assert any(isinstance(s, FearGreedSource) for s in sources)
