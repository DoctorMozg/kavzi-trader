import abc

from pydantic import BaseModel


class ExternalSource(abc.ABC):
    """Base class for all external data sources.

    Each source fetches market-wide (not per-symbol) data from an external
    API and returns a Pydantic schema representing the parsed result.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique source identifier, e.g. 'deribit_dvol'."""

    @abc.abstractmethod
    async def fetch(self) -> BaseModel | None:
        """Fetch and parse the latest data.

        Returns a frozen Pydantic schema on success, or None on failure.
        Implementations must handle their own exceptions internally and
        log errors — returning None signals graceful degradation.
        """
