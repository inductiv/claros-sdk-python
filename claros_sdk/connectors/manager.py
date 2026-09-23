from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Literal, overload

from claros_sdk.connectors.clickhouse import build_clickhouse_client
from claros_sdk.connectors.google import DEFAULT_SERVICE_VERSIONS, build_google_client
from claros_sdk.connectors.models import (
    CachedConnectorToken,
    ConnectorResolveResponse,
    ConnectorTokenData,
    ConnectorTokenResponse,
)
from claros_sdk.connectors.stripe import build_stripe_client
from claros_sdk.exceptions import ClarOSAPIError, ClarOSError

if TYPE_CHECKING:
    import stripe
    from clickhouse_connect.driver.client import Client as ClickHouseClient
    from googleapiclient.discovery import Resource

    import googleapiclient._apis.calendar.v3
    import googleapiclient._apis.drive.v3
    import googleapiclient._apis.gmail.v1
    import googleapiclient._apis.sheets.v4

    from claros_sdk.client import ClarOSClient

logger = logging.getLogger(__name__)


class ConnectorsManager:
    """
    Manager for ClarOS third-party connectors (Google, Stripe, ClickHouse, etc.).

    Handles credential resolution, in-memory caching with expiration/leeway,
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

    async def resolve(
        self,
        key: str,
        force_refresh: bool = False,
    ) -> ConnectorTokenData:
        """
        Resolve connection credentials for the specified key from ClarOS API.
        Caches token in-memory and reuses it if still valid according to expires_at / expires_in.
        """
        if not force_refresh and key in self._cache:
            cached = self._cache[key]
            if cached.is_valid(leeway_seconds=self.leeway_seconds):
                return cached.data

        lock = self._get_lock(key)
        async with lock:
            if not force_refresh and key in self._cache:
                cached = self._cache[key]
                if cached.is_valid(leeway_seconds=self.leeway_seconds):
                    return cached.data

            path = f"/api/v1/platform/connectors/{key}/resolve"
            try:
                res = await self._client.get(path)
            except ClarOSAPIError:
                raise
            except Exception as exc:
                raise ClarOSError(
                    f"Failed to resolve connector credentials for key '{key}': {exc}"
                ) from exc

            if isinstance(res, dict) and "payload" in res and isinstance(res["payload"], dict):
                token_data = ConnectorTokenData.model_validate(res["payload"])
            elif isinstance(res, dict) and "data" in res and isinstance(res["data"], dict):
                token_data = ConnectorTokenData.model_validate(res["data"])
            elif isinstance(res, dict) and ("token" in res or "credentials" in res):
                token_data = ConnectorTokenData.model_validate(res)
            else:
                try:
                    resp_model = ConnectorResolveResponse.model_validate(res)
                    if resp_model.payload is not None:
                        token_data = resp_model.payload
                    elif resp_model.data is not None:
                        token_data = resp_model.data
                    else:
                        raise ValueError("No payload or data in response")
                except Exception as exc:
                    raise ClarOSError(
                        f"Unexpected connector response structure from '{path}': {res}"
                    ) from exc

            self._cache[key] = CachedConnectorToken(token_data)
            return token_data

    get_token = resolve

    @overload
    async def google(
        self,
        key: str,
        service: Literal["sheets"] = "sheets",
        version: Literal["v4"] | None = None,
        force_refresh: bool = False,
        **kwargs: Any,
    ) -> googleapiclient._apis.sheets.v4.SheetsResource: ...

    @overload
    async def google(
        self,
        key: str,
        service: Literal["drive"],
        version: Literal["v3"] | None = None,
        force_refresh: bool = False,
        **kwargs: Any,
    ) -> googleapiclient._apis.drive.v3.DriveResource: ...

    @overload
    async def google(
        self,
        key: str,
        service: Literal["gmail"],
        version: Literal["v1"] | None = None,
        force_refresh: bool = False,
        **kwargs: Any,
    ) -> googleapiclient._apis.gmail.v1.GmailResource: ...

    @overload
    async def google(
        self,
        key: str,
        service: Literal["calendar"],
        version: Literal["v3"] | None = None,
        force_refresh: bool = False,
        **kwargs: Any,
    ) -> googleapiclient._apis.calendar.v3.CalendarResource: ...

    @overload
    async def google(
        self,
        key: str,
        service: str,
        version: str | None = None,
        force_refresh: bool = False,
        **kwargs: Any,
    ) -> Resource: ...

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
        token_data = await self.resolve(key, force_refresh=force_refresh)

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
    ) -> stripe.StripeClient:
        """
        Obtain official StripeClient with API key credentials for connection key.

        Parameters:
            key: Connection key configured in ClarOS (e.g. 'stripe').
            force_refresh: Whether to force re-fetching the token from ClarOS.
            **kwargs: Extra arguments passed to stripe.StripeClient().
        """
        token_data = await self.resolve(key, force_refresh=force_refresh)

        return build_stripe_client(token_data=token_data, **kwargs)

    async def clickhouse(
        self,
        key: str,
        force_refresh: bool = False,
        **kwargs: Any,
    ) -> ClickHouseClient:
        """
        Obtain official ClickHouse client with credentials for connection key.

        Parameters:
            key: Connection key configured in ClarOS (e.g. 'clickhouse').
            force_refresh: Whether to force re-fetching the credentials from ClarOS.
            **kwargs: Extra arguments passed to clickhouse_connect.get_client().
        """
        token_data = await self.resolve(key, force_refresh=force_refresh)

        return build_clickhouse_client(token_data=token_data, **kwargs)
