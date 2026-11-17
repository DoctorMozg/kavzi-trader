import pytest

from kavzi_trader.config import AppConfig


@pytest.fixture(scope="session")
def app_config() -> AppConfig:
    return AppConfig.from_env()


@pytest.fixture
def llm_app_config(app_config: AppConfig) -> AppConfig:
    """The shipped config with the LLM pipeline selected instead of trend."""
    strategy = app_config.strategy.model_copy(update={"active": "llm_pipeline"})
    return app_config.model_copy(update={"strategy": strategy})
