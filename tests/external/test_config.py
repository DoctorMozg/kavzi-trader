from kavzi_trader.external.config import (
    CryptoPanicConfigSchema,
    DeribitDvolConfigSchema,
    ExternalSourcesConfigSchema,
    FearGreedConfigSchema,
    SynthesizerConfigSchema,
)


def test_defaults() -> None:
    config = ExternalSourcesConfigSchema()
    assert config.enabled is True
    assert config.run_interval_s == 300
    assert config.deribit_dvol.enabled is True
    assert config.fear_greed.enabled is True
    assert config.cryptopanic.enabled is False
    assert config.synthesizer.enabled is True


def test_deribit_dvol_defaults() -> None:
    config = DeribitDvolConfigSchema()
    assert config.enabled is True


def test_fear_greed_defaults() -> None:
    config = FearGreedConfigSchema()
    assert config.enabled is True


def test_cryptopanic_defaults() -> None:
    config = CryptoPanicConfigSchema()
    assert config.enabled is False
    assert config.max_results == 20
    assert config.max_headlines == 5


def test_synthesizer_defaults() -> None:
    config = SynthesizerConfigSchema()
    assert config.enabled is True
    assert config.model_id == "deepseek/deepseek-chat-v3-0324"
    assert config.temperature == 0.0
    assert config.retries == 1


def test_custom_values() -> None:
    config = ExternalSourcesConfigSchema.model_validate(
        {
            "enabled": False,
            "run_interval_s": 600,
            "cryptopanic": {"enabled": True, "max_results": 10},
            "synthesizer": {"model_id": "custom/model", "retries": 3},
        },
    )
    assert config.enabled is False
    assert config.run_interval_s == 600
    assert config.cryptopanic.enabled is True
    assert config.cryptopanic.max_results == 10
    assert config.synthesizer.model_id == "custom/model"
    assert config.synthesizer.retries == 3


def test_frozen() -> None:
    config = ExternalSourcesConfigSchema()
    try:
        config.enabled = False  # type: ignore[misc]
        msg = "Expected frozen config to raise"
        raise AssertionError(msg)
    except Exception:
        pass
