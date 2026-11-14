import pytest

from kavzi_trader.config import AppConfig


@pytest.fixture(scope="session")
def app_config() -> AppConfig:
    return AppConfig.from_env()
