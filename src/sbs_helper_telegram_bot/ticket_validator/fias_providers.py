"""
FIAS Address Validation Providers

Provides a pluggable provider architecture for validating addresses against
FIAS (Федеральная информационная адресная система) or similar address databases.

The provider pattern allows swapping the underlying API without changing the
validation rule logic. Currently supported providers:

- **DaDataFIASProvider** — uses the DaData Suggestions API (https://dadata.ru/api/suggest/address/).
  Free tier: up to 10 000 requests/day. Requires an API key set via the
  ``DADATA_API_KEY`` environment variable.

To add a new provider, subclass :class:`BaseFIASProvider` and implement
:meth:`validate_address`.

Usage example::

    from .fias_providers import get_fias_provider

    provider = get_fias_provider()          # returns the active provider
    result   = provider.validate_address("Москва, ул Льва Толстого 16")
    if result.is_valid:
        print("Address found in FIAS:", result.suggested_address)
    else:
        print("Address not found:", result.error_message)
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FIASValidationResult:
    """Result of an address validation against FIAS.

    Attributes:
        is_valid: ``True`` when at least one suggestion was returned by the API.
        address_query: The original address string that was checked.
        suggested_address: The best suggestion returned by the API (if any).
        suggestions_count: Total number of suggestions returned.
        all_suggestions: Raw list of suggestion values (for debugging).
        error_message: Human-readable error when validation failed or API error occurred.
        provider_name: Name of the provider that performed the check.
        fias_id: FIAS identifier of the best suggestion (if available).
        fias_level: FIAS detail level of the best suggestion (if available).
    """

    is_valid: bool
    address_query: str = ""
    suggested_address: Optional[str] = None
    suggestions_count: int = 0
    all_suggestions: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    provider_name: str = ""
    fias_id: Optional[str] = None
    fias_level: Optional[str] = None


# ---------------------------------------------------------------------------
# Abstract base provider
# ---------------------------------------------------------------------------

class BaseFIASProvider(ABC):
    """Abstract base class for FIAS address validation providers.

    Every concrete provider **must** implement :meth:`validate_address`.

    Subclasses may also override:
    * :attr:`provider_name` — human-readable label shown in logs / messages.
    * :meth:`is_configured` — returns ``False`` when required credentials are
      missing so the caller can fail early.
    """

    provider_name: str = "base"

    @abstractmethod
    def validate_address(self, address: str) -> FIASValidationResult:
        """Validate *address* against the FIAS database.

        Args:
            address: Free-form address string to look up.

        Returns:
            A :class:`FIASValidationResult` describing the outcome.
        """

    def is_configured(self) -> bool:  # noqa: D401
        """Return ``True`` when the provider has all the credentials it needs."""
        return True


# ---------------------------------------------------------------------------
# DaData provider
# ---------------------------------------------------------------------------

class DaDataFIASProvider(BaseFIASProvider):
    """FIAS validation via the DaData Suggestions API.

    API reference: https://dadata.ru/api/suggest/address/

    The provider sends a POST request to the ``/suggest/address`` endpoint
    and considers the address **valid** when the ``suggestions`` array in the
    response is not empty.

    Configuration (environment variables):
        * ``DADATA_API_KEY`` — **required**.  Your DaData API key.
        * ``DADATA_API_URL`` — *optional*.  Override the base URL
          (default ``https://suggestions.dadata.ru/suggestions/api/4_1/rs``).

    Rate limits (free tier):
        * 10 000 requests / day
        * 30 requests / second per IP
        * 60 new connections / minute per IP

    HTTP status codes to watch for:
        * 403 — invalid key **or** daily quota exceeded
        * 429 — per-second rate limit hit
    """

    provider_name: str = "dadata"

    # Default endpoint — the *address* suggest, not FIAS-only, per DaData's own
    # recommendation (the ``/suggest/address`` endpoint is more complete).
    DEFAULT_API_URL = (
        "https://suggestions.dadata.ru/suggestions/api/4_1/rs"
    )

    SUGGEST_ADDRESS_PATH = "/suggest/address"

    # Timeout for each HTTP request (seconds).
    REQUEST_TIMEOUT = 10

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("DADATA_API_KEY", "")
        self.api_url = (
            api_url
            or os.getenv("DADATA_API_URL", "")
            or self.DEFAULT_API_URL
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """Check that the API key is present."""
        return bool(self.api_key)

    def validate_address(self, address: str) -> FIASValidationResult:
        """Query DaData and return a :class:`FIASValidationResult`.

        If the API key is missing or the request fails, the result is marked
        as *valid* (fail-open) so that a misconfiguration does not block every
        ticket.  The ``error_message`` field will contain the details.
        """
        if not self.is_configured():
            logger.warning("DaData API key is not configured — skipping FIAS check")
            return FIASValidationResult(
                is_valid=True,
                address_query=address,
                error_message="DADATA_API_KEY не настроен — проверка ФИАС пропущена",
                provider_name=self.provider_name,
            )

        url = self.api_url.rstrip("/") + self.SUGGEST_ADDRESS_PATH

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {self.api_key}",
        }

        payload = {
            "query": address,
            "count": 1,
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.REQUEST_TIMEOUT,
            )

            if response.status_code == 403:
                logger.error(
                    "DaData API returned 403 — invalid key or daily quota exceeded"
                )
                return FIASValidationResult(
                    is_valid=True,  # fail-open
                    address_query=address,
                    error_message="Ошибка авторизации DaData (403) — проверка ФИАС пропущена",
                    provider_name=self.provider_name,
                )

            if response.status_code == 429:
                logger.warning("DaData API rate-limit hit (429)")
                return FIASValidationResult(
                    is_valid=True,  # fail-open
                    address_query=address,
                    error_message="Превышен лимит запросов DaData (429) — проверка ФИАС пропущена",
                    provider_name=self.provider_name,
                )

            response.raise_for_status()

            data = response.json()
            suggestions = data.get("suggestions", [])

            if suggestions:
                best = suggestions[0]
                return FIASValidationResult(
                    is_valid=True,
                    address_query=address,
                    suggested_address=best.get("value", ""),
                    suggestions_count=len(suggestions),
                    all_suggestions=[s.get("value", "") for s in suggestions],
                    provider_name=self.provider_name,
                    fias_id=(best.get("data") or {}).get("fias_id"),
                    fias_level=str((best.get("data") or {}).get("fias_level", "")),
                )
            else:
                return FIASValidationResult(
                    is_valid=False,
                    address_query=address,
                    suggestions_count=0,
                    error_message="Адрес не найден в базе ФИАС",
                    provider_name=self.provider_name,
                )

        except requests.exceptions.Timeout:
            logger.error("DaData API request timed out")
            return FIASValidationResult(
                is_valid=True,  # fail-open
                address_query=address,
                error_message="Таймаут запроса к DaData — проверка ФИАС пропущена",
                provider_name=self.provider_name,
            )

        except requests.exceptions.RequestException as exc:
            logger.error("DaData API request failed: %s", exc)
            return FIASValidationResult(
                is_valid=True,  # fail-open
                address_query=address,
                error_message=f"Ошибка запроса к DaData: {exc}",
                provider_name=self.provider_name,
            )

        except (ValueError, KeyError) as exc:
            logger.error("Failed to parse DaData response: %s", exc)
            return FIASValidationResult(
                is_valid=True,  # fail-open
                address_query=address,
                error_message=f"Ошибка разбора ответа DaData: {exc}",
                provider_name=self.provider_name,
            )


# ---------------------------------------------------------------------------
# Provider registry & factory
# ---------------------------------------------------------------------------

# Maps provider names to classes.  Extend this dict when adding new providers.
_PROVIDER_REGISTRY: dict[str, type[BaseFIASProvider]] = {
    "dadata": DaDataFIASProvider,
}

# Module-level singleton — lazily initialised by :func:`get_fias_provider`.
_active_provider: Optional[BaseFIASProvider] = None


def get_fias_provider(
    provider_name: Optional[str] = None,
) -> BaseFIASProvider:
    """Return the active FIAS provider (singleton).

    The provider is selected in the following priority order:

    1. *provider_name* argument (explicit override).
    2. ``FIAS_PROVIDER`` environment variable.
    3. Falls back to ``"dadata"``.

    The instance is cached so that subsequent calls return the same object
    (and the same HTTP session, if the provider uses one).
    """
    global _active_provider  # noqa: PLW0603

    desired = (
        provider_name
        or os.getenv("FIAS_PROVIDER", "")
        or "dadata"
    ).lower()

    # Return cached instance if it matches
    if _active_provider is not None and _active_provider.provider_name == desired:
        return _active_provider

    provider_cls = _PROVIDER_REGISTRY.get(desired)
    if provider_cls is None:
        raise ValueError(
            f"Unknown FIAS provider '{desired}'. "
            f"Available: {', '.join(_PROVIDER_REGISTRY)}"
        )

    _active_provider = provider_cls()
    logger.info("FIAS provider initialised: %s", _active_provider.provider_name)
    return _active_provider


def reset_fias_provider() -> None:
    """Reset the cached provider (useful in tests)."""
    global _active_provider  # noqa: PLW0603
    _active_provider = None
