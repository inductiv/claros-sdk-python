from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from claros_sdk.connectors.google import DEFAULT_SERVICE_VERSIONS, build_google_client
from claros_sdk.connectors.models import (
    CachedConnectorToken,
    ConnectorTokenData,
    ConnectorTokenResponse,
)
from claros_sdk.connectors.stripe import build_stripe_client
from claros_sdk.exceptions import ClarOSAPIError, ClarOSError

if TYPE_CHECKING:
    from claros_sdk.client import ClarOSClient

logger = logging.getLogger(__name__)


class ConnectorsManager:
    """
    Manager for ClarOS third-party connectors (Google, Stripe, etc.).

    Handles token retrieval, in-memory caching with expiration/leeway,
    and official SDK client construction with applied credentials.
    """

    def __init__(
        self,
        client: ClarOSClient,
        leeway_seconds: float = 60.0,
    ) -> None:
        self._client = client
        self.leeway_seconds = leeway_seconds
        self._cache: dict[str, CachedConnectorToken] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def clear_cache(self, key: str | None = None) -> None:
        """Clear cached tokens for a specific key, or for all keys if None."""
        if key is not None:
            self._cache.pop(key, None)
        else:
            self._cache.clear()

    async def get_token(
        self,
        key: str,
        force_refresh: bool = False,
    ) -> ConnectorTokenData:
        """
        Fetch connection token for the specified key from ClarOS API.
        Caches token in-memory and reuses it if still valid according to expires_at / expires_in.
        """
        if not force_refresh and key in self._cache:
            cached = self._cache[key]
            if cached.is_valid(leeway_seconds=self.leeway_seconds):
                return cached.data

        lock = self._get_lock(key)
        async with lock:
            # Double check cache inside lock
            if not force_refresh and key in self._cache:
                cached = self._cache[key]
                if cached.is_valid(leeway_seconds=self.leeway_seconds):
                    return cached.data

            path = f"/api/v1/connectors/{key}/token"
            try:
                res = await self._client.get(path)
            except ClarOSAPIError:
                raise
            except Exception as exc:
                raise ClarOSError(
                    f"Failed to fetch connector token for key '{key}': {exc}"
                ) from exc

            # Parse response data
            if isinstance(res, dict) and "data" in res and isinstance(res["data"], dict):
                token_data = ConnectorTokenData.model_validate(res["data"])
            elif isinstance(res, dict) and "token" in res:
                token_data = ConnectorTokenData.model_validate(res)
            else:
                try:
                    resp_model = ConnectorTokenResponse.model_validate(res)
                    token_data = resp_model.data
                except Exception as exc:
                    raise ClarOSError(
                        f"Unexpected connector response structure from '{path}': {res}"
                    ) from exc

            self._cache[key] = CachedConnectorToken(token_data)
            return token_data

    async def google(
        self,
        key: str,
        service: str | None = None,
        version: str | None = None,
        force_refresh: bool = False,
        **kwargs: Any,
    ) -> Any:
        """
        Obtain official Google API client resource with credentials for connection key.

        Parameters:
            key: Connection key configured in ClarOS (e.g. 'sheets').
            service: Google service name ('sheets', 'drive', etc.). If None, infers from key or defaults to 'sheets'.
            version: API version (e.g. 'v4' for sheets). If None, uses default version for service.
            force_refresh: Whether to force re-fetching the token from ClarOS.
            **kwargs: Extra arguments passed to googleapiclient.discovery.build().
        """
        token_data = await self.get_token(key, force_refresh=force_refresh)

        if service is None:
            service = key if key in DEFAULT_SERVICE_VERSIONS else "sheets"

        return build_google_client(
            token_data=token_data,
            service=service,
            version=version,
            **kwargs,
        )

    async def stripe(
        self,
        key: str,
        force_refresh: bool = False,
        **kwargs: Any,
    ) -> Any:
        """
        Obtain official StripeClient with API key credentials for connection key.

        Parameters:
            key: Connection key configured in ClarOS (e.g. 'stripe').
            force_refresh: Whether to force re-fetching the token from ClarOS.
            **kwargs: Extra arguments passed to stripe.StripeClient().
        """
        token_data = await self.get_token(key, force_refresh=force_refresh)

        return build_stripe_client(token_data=token_data, **kwargs)
