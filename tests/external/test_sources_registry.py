from kavzi_trader.external.config import ExternalSourcesConfigSchema
from kavzi_trader.external.sources import build_enabled_sources
from kavzi_trader.external.sources.deribit_dvol import DeribitDvolSource
from kavzi_trader.external.sources.fear_greed import FearGreedSource


def test_default_config_builds_all_sources() -> None:
    config = ExternalSourcesConfigSchema()
    sources = build_enabled_sources(config)
    names = [s.name for s in sources]
    assert "deribit_dvol" in names
    assert "fear_greed" in names
    assert names == ["deribit_dvol", "fear_greed"]


def test_all_disabled() -> None:
    config = ExternalSourcesConfigSchema.model_validate(
        {
            "deribit_dvol": {"enabled": False},
            "fear_greed": {"enabled": False},
        },
    )
    sources = build_enabled_sources(config)
    assert len(sources) == 0


def test_source_types() -> None:
    config = ExternalSourcesConfigSchema()
    sources = build_enabled_sources(config)
    assert any(isinstance(s, DeribitDvolSource) for s in sources)
    assert any(isinstance(s, FearGreedSource) for s in sources)
