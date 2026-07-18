"""Connector interface shared by all provider integrations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class Connector(ABC):
    """A connector pulls raw data from one provider for a brand + period.

    Implementations should keep `fetch` side-effect free (return raw payloads);
    persistence into raw_pulls is the caller's job. `normalize` converts a raw
    payload into the shape the compute layer expects.
    """

    provider: str

    def __init__(self, credentials: dict[str, Any] | None = None,
                 config: dict[str, Any] | None = None) -> None:
        self.credentials = credentials or {}
        self.config = config or {}

    @abstractmethod
    def fetch(self, period_start: datetime, period_end: datetime) -> dict[str, Any]:
        """Return a raw payload for the period."""

    @abstractmethod
    def normalize(self, payload: dict[str, Any]) -> Any:
        """Convert a raw payload into normalized records."""
