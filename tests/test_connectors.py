from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from claros_sdk import ClarOSClient
from claros_sdk.connectors import (
    CachedConnectorToken,
    ConnectorTokenData,
    ConnectorTokenResponse,
    ConnectorsManager,
)
from claros_sdk.exceptions import ClarOSAPIError, ClarOSError


def test_cached_connector_token_validity():
    # 1. Permanent token (no expires_at or expires_in)
    permanent = CachedConnectorToken(
        ConnectorTokenData(
            token="sk_live_123",
            token_type="ApiKey",
            provider="stripe",
            connection_key="stripe",
        )
    )
    assert permanent.is_valid() is True

    # 2. expires_in valid
    valid_in = CachedConnectorToken(
        ConnectorTokenData(
            token="token_abc",
            provider="google",
            connection_key="sheets",
            expires_in=3600,
        ),
        cached_at=1000.0,
    )
    with patch("time.time", return_value=1500.0):
        assert valid_in.is_valid(leeway_seconds=60) is True
    with patch("time.time", return_value=4600.0):
        assert valid_in.is_valid(leeway_seconds=60) is False

    # 3. expires_at ISO string
    iso_token = CachedConnectorToken(
        ConnectorTokenData(
            token="ya29.xyz",
            provider="google",
            connection_key="sheets",
            expires_at="2026-09-07T14:00:00Z",
        )
    )
    # 2026-09-07 14:00:00 UTC = timestamp 1788789600
    target_ts = datetime(2026, 9, 7, 14, 0, 0, tzinfo=timezone.utc).timestamp()
    with patch("time.time", return_value=target_ts - 100):
        assert iso_token.is_valid(leeway_seconds=60) is True
    with patch("time.time", return_value=target_ts - 30):
        # Within 60s leeway
        assert iso_token.is_valid(leeway_seconds=60) is False


@pytest.mark.asyncio
async def test_get_token_and_caching():
    call_counts = {"token": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/connectors/sheets/token"
        call_counts["token"] += 1
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "Connector token retrieved successfully",
                "data": {
                    "token": "ya29.mock_token_abc",
                    "token_type": "Bearer",
                    "expires_at": "2026-09-07T12:58:30Z",
                    "expires_in": 3600,
                    "provider": "google",
                    "connection_key": "sheets",
                },
            },
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="http://localhost:8080", httpx_client=httpx_client) as client:
        # First call fetches from API
        token_data = await client.connectors.get_token("sheets")
        assert token_data.token == "ya29.mock_token_abc"
        assert token_data.provider == "google"
        assert token_data.connection_key == "sheets"
        assert call_counts["token"] == 1

        # Second call returns from in-memory cache
        cached_token = await client.connectors.get_token("sheets")
        assert cached_token.token == "ya29.mock_token_abc"
        assert call_counts["token"] == 1

        # Force refresh bypasses cache
        refreshed = await client.connectors.get_token("sheets", force_refresh=True)
        assert refreshed.token == "ya29.mock_token_abc"
        assert call_counts["token"] == 2

        # Clear cache works
        client.connectors.clear_cache("sheets")
        after_clear = await client.connectors.get_token("sheets")
        assert after_clear.token == "ya29.mock_token_abc"
        assert call_counts["token"] == 3


@pytest.mark.asyncio
async def test_get_token_error_raises_claros_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Connector not found"})

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="http://localhost:8080", httpx_client=httpx_client) as client:
        with pytest.raises(ClarOSAPIError) as exc_info:
            await client.connectors.get_token("nonexistent")
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_google_missing_dependency_raises_helpful_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "OK",
                "data": {
                    "token": "ya29.test",
                    "provider": "google",
                    "connection_key": "sheets",
                },
            },
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="http://localhost:8080", httpx_client=httpx_client) as client:
        with patch.dict("sys.modules", {"googleapiclient": None, "googleapiclient.discovery": None}):
            with pytest.raises(ClarOSError) as exc_info:
                await client.connectors.google("sheets")
            assert "pip install 'claros-sdk[google]'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_stripe_missing_dependency_raises_helpful_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "OK",
                "data": {
                    "token": "sk_test_123",
                    "token_type": "ApiKey",
                    "provider": "stripe",
                    "connection_key": "stripe",
                },
            },
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="http://localhost:8080", httpx_client=httpx_client) as client:
        with patch.dict("sys.modules", {"stripe": None}):
            with pytest.raises(ClarOSError) as exc_info:
                await client.connectors.stripe("stripe")
            assert "pip install 'claros-sdk[stripe]'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_google_client_build():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "OK",
                "data": {
                    "token": "ya29.mock_oauth_token",
                    "token_type": "Bearer",
                    "provider": "google",
                    "connection_key": "sheets",
                },
            },
        )

    mock_credentials = MagicMock()
    mock_creds_cls = MagicMock(return_value=mock_credentials)
    mock_creds_mod = MagicMock(Credentials=mock_creds_cls)
    mock_build = MagicMock(return_value=MagicMock(name="SheetsServiceResource"))
    mock_discovery = MagicMock(build=mock_build)

    mock_modules = {
        "google": MagicMock(),
        "google.auth": MagicMock(),
        "google.oauth2": MagicMock(),
        "google.oauth2.credentials": mock_creds_mod,
        "googleapiclient": MagicMock(discovery=mock_discovery),
        "googleapiclient.discovery": mock_discovery,
    }

    with patch.dict("sys.modules", mock_modules):
        httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with ClarOSClient(base_url="http://localhost:8080", httpx_client=httpx_client) as client:
            sheets = await client.connectors.google("sheets")

            mock_creds_cls.assert_called_once_with(token="ya29.mock_oauth_token")
            mock_build.assert_called_once_with(
                serviceName="sheets",
                version="v4",
                credentials=mock_credentials,
            )
            assert sheets == mock_build.return_value


@pytest.mark.asyncio
async def test_google_client_custom_service():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "OK",
                "data": {
                    "token": "ya29.mock_token",
                    "token_type": "Bearer",
                    "provider": "google",
                    "connection_key": "my_google_conn",
                },
            },
        )

    mock_credentials = MagicMock()
    mock_creds_cls = MagicMock(return_value=mock_credentials)
    mock_creds_mod = MagicMock(Credentials=mock_creds_cls)
    mock_build = MagicMock()
    mock_discovery = MagicMock(build=mock_build)

    mock_modules = {
        "google": MagicMock(),
        "google.auth": MagicMock(),
        "google.oauth2": MagicMock(),
        "google.oauth2.credentials": mock_creds_mod,
        "googleapiclient": MagicMock(discovery=mock_discovery),
        "googleapiclient.discovery": mock_discovery,
    }

    with patch.dict("sys.modules", mock_modules):
        httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with ClarOSClient(base_url="http://localhost:8080", httpx_client=httpx_client) as client:
            await client.connectors.google("my_google_conn", service="drive", version="v3")

            mock_build.assert_called_once_with(
                serviceName="drive",
                version="v3",
                credentials=mock_credentials,
            )


@pytest.mark.asyncio
async def test_stripe_client_build():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "OK",
                "data": {
                    "token": "sk_test_abc123",
                    "token_type": "ApiKey",
                    "provider": "stripe",
                    "connection_key": "stripe",
                },
            },
        )

    mock_instance = MagicMock(name="StripeClientInstance")
    mock_stripe_cls = MagicMock(return_value=mock_instance)
    mock_stripe_mod = MagicMock(StripeClient=mock_stripe_cls)

    with patch.dict("sys.modules", {"stripe": mock_stripe_mod}):
        httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with ClarOSClient(base_url="http://localhost:8080", httpx_client=httpx_client) as client:
            stripe = await client.connectors.stripe("stripe")

            mock_stripe_cls.assert_called_once_with(api_key="sk_test_abc123")
            assert stripe == mock_instance



@pytest.mark.asyncio
async def test_concurrent_get_token_deduplication():
    call_counts = {"token": 0}

    async def delayed_handler(request: httpx.Request) -> httpx.Response:
        call_counts["token"] += 1
        await asyncio.sleep(0.05)
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "OK",
                "data": {
                    "token": "token_concurrent",
                    "provider": "google",
                    "connection_key": "sheets",
                    "expires_in": 3600,
                },
            },
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(delayed_handler))
    async with ClarOSClient(base_url="http://localhost:8080", httpx_client=httpx_client) as client:
        # Launch 5 concurrent calls for the same key
        results = await asyncio.gather(
            client.connectors.get_token("sheets"),
            client.connectors.get_token("sheets"),
            client.connectors.get_token("sheets"),
            client.connectors.get_token("sheets"),
            client.connectors.get_token("sheets"),
        )
        assert len(results) == 5
        assert all(r.token == "token_concurrent" for r in results)
        # Verify deduplication due to lock
        assert call_counts["token"] == 1


@pytest.mark.asyncio
async def test_real_stripe_client_initialization():
    import stripe

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "OK",
                "data": {
                    "token": "sk_test_real_key_999",
                    "token_type": "ApiKey",
                    "provider": "stripe",
                    "connection_key": "stripe",
                },
            },
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="http://localhost:8080", httpx_client=httpx_client) as client:
        stripe_client = await client.connectors.stripe("stripe")
        assert isinstance(stripe_client, stripe.StripeClient)
        assert stripe_client._requestor._options.api_key == "sk_test_real_key_999"


@pytest.mark.asyncio
async def test_real_google_dependencies_and_credentials():
    from google.oauth2.credentials import Credentials

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "OK",
                "data": {
                    "token": "ya29.real_google_token",
                    "token_type": "Bearer",
                    "provider": "google",
                    "connection_key": "sheets",
                },
            },
        )

    # Mock build only to avoid network call to googleapis.com discovery endpoint
    with patch("googleapiclient.discovery.build") as mock_build:
        mock_build.return_value = MagicMock(name="RealGoogleResource")

        httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with ClarOSClient(base_url="http://localhost:8080", httpx_client=httpx_client) as client:
            sheets = await client.connectors.google("sheets")
            assert sheets == mock_build.return_value

            # Check that credentials passed to build were real google Credentials object
            _, kwargs = mock_build.call_args
            creds = kwargs.get("credentials")
            assert isinstance(creds, Credentials)
            assert creds.token == "ya29.real_google_token"
