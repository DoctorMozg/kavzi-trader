import logging
import os

from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.config import ExternalSourcesConfigSchema
from kavzi_trader.external.sources.cryptopanic import CryptoPanicSource
from kavzi_trader.external.sources.deribit_dvol import DeribitDvolSource
from kavzi_trader.external.sources.fear_greed import FearGreedSource

logger = logging.getLogger(__name__)


def build_enabled_sources(
    config: ExternalSourcesConfigSchema,
) -> list[ExternalSource]:
    """Build list of enabled external data sources from config."""
    sources: list[ExternalSource] = []

    if config.deribit_dvol.enabled:
        sources.append(DeribitDvolSource())
        logger.info("External source enabled: deribit_dvol")

    if config.fear_greed.enabled:
        sources.append(FearGreedSource())
        logger.info("External source enabled: fear_greed")

    if config.cryptopanic.enabled:
        api_key = os.getenv("KT_CRYPTOPANIC_API_KEY", "")
        if api_key:
            sources.append(
                CryptoPanicSource(
                    api_key=api_key,
                    max_results=config.cryptopanic.max_results,
                    max_headlines=config.cryptopanic.max_headlines,
                ),
            )
            logger.info("External source enabled: cryptopanic")
        else:
            logger.warning(
                "CryptoPanic enabled but KT_CRYPTOPANIC_API_KEY not set, skipping",
            )

    return sources
