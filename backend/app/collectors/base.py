from abc import ABC, abstractmethod

from app.models import NormalizedTick


class ExchangeAdapter(ABC):
    """Common interface for monitor exchange market-data adapters."""

    name: str

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> NormalizedTick | None:
        """Fetch current bid/ask/mid for a symbol."""

    @abstractmethod
    async def health_check(self) -> dict:
        """Return exchange connectivity status."""

    @abstractmethod
    async def close(self) -> None:
        """Close any persistent connections owned by this adapter."""

    @property
    @abstractmethod
    def supported_symbols(self) -> list[str]:
        """Return symbols this exchange adapter can fetch."""
