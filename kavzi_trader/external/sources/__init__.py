import logging

from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.config import ExternalSourcesConfigSchema
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

    return sources
