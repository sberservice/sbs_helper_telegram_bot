"""
FIAS provider implementations and registry.

Provides a pluggable provider interface for address suggestions.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Dict, Optional, Protocol

from . import settings

logger = logging.getLogger(__name__)


class FiasProviderError(RuntimeError):
    """Base error for FIAS provider failures."""


class FiasProviderRateLimitError(FiasProviderError):
    """Raised when provider rate limits are exceeded."""


class FiasProviderConfigError(FiasProviderError):
    """Raised when provider configuration is invalid or missing."""


class FiasProvider(Protocol):
    """FIAS provider interface."""

    def has_suggestions(self, address: str) -> bool:
        """Return True when suggestions exist for the given address."""


@dataclass
class DailyRateLimiter:
    """Simple in-memory daily request limiter."""

    limit: int
    count: int = 0
    day: date = field(default_factory=date.today)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self) -> bool:
        if self.limit <= 0:
            return True
        with self.lock:
            today = date.today()
            if self.day != today:
                self.day = today
                self.count = 0
            if self.count >= self.limit:
                return False
            self.count += 1
            return True


class DadataFiasProvider:
    """DaData FIAS suggestions provider."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        daily_limit: int,
        suggestions_count: int,
    ) -> None:
        if not api_key:
            raise FiasProviderConfigError("DaData API key is not configured")
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._count = suggestions_count
        self._rate_limiter = DailyRateLimiter(daily_limit)

    def has_suggestions(self, address: str) -> bool:
        address = (address or "").strip()
        if not address:
            return False
        if len(address) > settings.FIAS_MAX_QUERY_LENGTH:
            address = address[: settings.FIAS_MAX_QUERY_LENGTH]
        return self._has_suggestions_cached(address)

    @lru_cache(maxsize=1024)
    def _has_suggestions_cached(self, address: str) -> bool:
        try:
            import requests
        except ImportError as exc:
            raise FiasProviderConfigError("requests is not installed") from exc

        if not self._rate_limiter.allow():
            raise FiasProviderRateLimitError("Daily request limit reached")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {self._api_key}",
        }
        payload = {
            "query": address,
            "count": self._count,
        }

        try:
            response = requests.post(
                self._base_url,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise FiasProviderError(f"Request failed: {exc}") from exc

        if response.status_code == 200:
            data = response.json()
            suggestions = data.get("suggestions", []) if isinstance(data, dict) else []
            return len(suggestions) > 0

        if response.status_code in {403, 429}:
            raise FiasProviderRateLimitError(
                f"Provider rate limit exceeded (status {response.status_code})"
            )

        raise FiasProviderError(
            f"Provider error (status {response.status_code}): {response.text}"
        )


_PROVIDERS: Dict[str, FiasProvider] = {}


def _build_dadata_provider() -> DadataFiasProvider:
    return DadataFiasProvider(
        api_key=settings.FIAS_DADATA_API_KEY,
        base_url=settings.FIAS_DADATA_BASE_URL,
        timeout_seconds=settings.FIAS_DADATA_TIMEOUT_SECONDS,
        daily_limit=settings.FIAS_DADATA_DAILY_LIMIT,
        suggestions_count=settings.FIAS_DADATA_SUGGESTIONS_COUNT,
    )


def get_fias_provider(name: Optional[str] = None) -> FiasProvider:
    """Return a FIAS provider instance by name."""
    provider_name = (name or settings.FIAS_PROVIDER).strip().lower()
    if provider_name in _PROVIDERS:
        return _PROVIDERS[provider_name]

    if provider_name == "dadata":
        provider = _build_dadata_provider()
    else:
        raise FiasProviderConfigError(f"Unknown FIAS provider: {provider_name}")

    _PROVIDERS[provider_name] = provider
    return provider


def reset_fias_providers() -> None:
    """Reset cached provider instances (test helper)."""
    _PROVIDERS.clear()