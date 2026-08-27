from __future__ import annotations

import asyncio
import collections
import json
import logging
import random
import time
from typing import Any

import httpx

from claros_sdk.channels.base import BaseChannel
from claros_sdk.channels.discord import DiscordChannel
from claros_sdk.channels.email import EmailChannel
from claros_sdk.channels.slack import SlackChannel
from claros_sdk.events import EventEmitter
from claros_sdk.exceptions import ClarOSAPIError, ClarOSAuthError, ClarOSError
from claros_sdk.models import (
    ClarOSAuthContext,
    InboundMessageEvent,
    TenantAuthContextResponse,
    TokenVerifyResponse,
    UserTenantResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_LEEWAY_SECONDS = 60


class ClarOSClient:
    """Client SDK for ClarOS Communication & Auth Service."""

    def __init__(
        self,
        base_url: str = "https://api.claros.ai",
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: float = 10.0,
        httpx_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

        self._external_client = httpx_client is not None
        self._client = httpx_client or httpx.AsyncClient(timeout=timeout)

        self._access_token: str | None = None
        self._expires_at: float = 0.0

        # Event Dispatcher & SSE stream state
        self.dispatcher = EventEmitter()
        self._last_event_id: str | None = None
        self._is_connected = False
        self._reconnect_attempts = 0
        self._stopped = False
        self._stream_task: asyncio.Task[None] | None = None
        self._connection_lock: asyncio.Lock | None = None
        self._seen_event_ids: collections.deque[str] = collections.deque(maxlen=1000)

        # Modular Communication Channels
        self.slack = SlackChannel(self)
        self.email = EmailChannel(self)
        self.discord = DiscordChannel(self)

    def _get_lock(self) -> asyncio.Lock:
        if self._connection_lock is None:
            self._connection_lock = asyncio.Lock()
        return self._connection_lock

    async def __aenter__(self) -> ClarOSClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Stop SSE background streams and close HTTP client."""
        await self.stop_stream()
        if not self._external_client:
            await self._client.aclose()

    def channel(self, channel_type: str) -> BaseChannel:
        """Get or create a generic channel instance by identifier."""
        if channel_type == "slack":
            return self.slack
        elif channel_type == "email":
            return self.email
        elif channel_type == "discord":
            return self.discord
        return BaseChannel(self, channel_type=channel_type)

    @property
    def access_token(self) -> str | None:
        return self._access_token

    @property
    def is_token_valid(self) -> bool:
        return bool(
            self._access_token and time.time() < (self._expires_at - DEFAULT_LEEWAY_SECONDS)
        )

    @property
    def is_connected(self) -> bool:
        """Return True if the inbound SSE stream is currently connected."""
        return self._is_connected

    @property
    def last_event_id(self) -> str | None:
        """Return the last received SSE event ID."""
        return self._last_event_id

    # ---------------------------------------------------------------------------
    # HTTP Request Helpers
    # ---------------------------------------------------------------------------

    async def _get_auth_header(self) -> str | None:
        """Resolve Authorization header from M2M token."""
        if self.client_id and self.client_secret:
            token = await self.get_token()
            return f"Bearer {token}"
        if self._access_token:
            return f"Bearer {self._access_token}"
        return None

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Perform an authenticated GET request against ClarOS API."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        req_headers: dict[str, str] = {}

        auth_header = await self._get_auth_header()
        if auth_header:
            req_headers["Authorization"] = auth_header
        if headers:
            req_headers.update(headers)

        try:
            response = await self._client.get(url, params=params, headers=req_headers)
        except Exception as exc:
            raise ClarOSError(f"ClarOS GET {path} request failed: {exc}") from exc

        if response.status_code not in (200, 201, 202):
            raise ClarOSAPIError(
                status_code=response.status_code,
                message=response.text,
                payload=params,
            )

        try:
            return response.json()
        except Exception:
            return {"status": "ok", "status_code": response.status_code}

    async def post(
        self,
        path: str,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Perform an authenticated POST request against ClarOS API."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        req_headers = {"Content-Type": "application/json"}

        auth_header = await self._get_auth_header()
        if auth_header:
            req_headers["Authorization"] = auth_header
        if headers:
            req_headers.update(headers)

        try:
            response = await self._client.post(url, json=json, headers=req_headers)
        except Exception as exc:
            raise ClarOSError(f"ClarOS POST {path} request failed: {exc}") from exc

        if response.status_code not in (200, 201, 202):
            raise ClarOSAPIError(
                status_code=response.status_code,
                message=response.text,
                payload=json if isinstance(json, dict) else None,
            )

        try:
            return response.json()
        except Exception:
            return {"status": "ok", "status_code": response.status_code}

    # ---------------------------------------------------------------------------
    # M2M Token Acquisition
    # ---------------------------------------------------------------------------

    async def get_token(self, force_refresh: bool = False) -> str:
        """Fetch or return cached M2M OAuth access token."""
        if not force_refresh and self.is_token_valid and self._access_token:
            return self._access_token

        if not self.client_id or not self.client_secret:
            raise ClarOSAuthError(
                "client_id and client_secret are required to acquire an M2M access token"
            )

        url = f"{self.base_url}/api/v1/auth/oauth/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }

        try:
            response = await self._client.post(url, json=payload)
        except Exception as exc:
            raise ClarOSAuthError(f"Failed to connect to ClarOS auth endpoint: {exc}") from exc

        if response.status_code != 200:
            raise ClarOSAuthError(
                f"ClarOS auth failed [HTTP {response.status_code}]: {response.text}"
            )

        try:
            data = response.json()
            payload_data = data.get("payload", data) if isinstance(data, dict) else data
            token = payload_data["access_token"]
            expires_in = int(payload_data.get("expires_in", 3600))
        except (KeyError, ValueError, TypeError) as exc:
            raise ClarOSAuthError(
                f"Invalid OAuth token response structure from ClarOS: {response.text}"
            ) from exc

        self._access_token = token
        self._expires_at = time.time() + expires_in
        logger.debug("ClarOS M2M access token acquired successfully (expires in %ds)", expires_in)
        return token

    # ---------------------------------------------------------------------------
    # User & Tenant Resolution
    # ---------------------------------------------------------------------------

    async def resolve_user_tenant(self, email: str) -> UserTenantResponse:
        """
        Resolve user and tenant associations by email (ResolveUserTenant).
        Calls GET /api/v1/platform/users/email?email=<email>.
        """
        token = await self.get_token()
        url = f"{self.base_url}/api/v1/platform/users/email"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"email": email}

        try:
            response = await self._client.get(url, params=params, headers=headers)
        except Exception as exc:
            raise ClarOSError(f"ClarOS resolve_user_tenant request failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise ClarOSAuthError(f"Unauthorized to resolve user tenant: {response.text}")
        if response.status_code == 404:
            raise ClarOSAPIError(404, f"User with email '{email}' not found: {response.text}")
        if response.status_code != 200:
            raise ClarOSAPIError(
                response.status_code, f"Failed to resolve user tenant: {response.text}"
            )

        try:
            return UserTenantResponse.model_validate(response.json())
        except Exception as exc:
            raise ClarOSError(f"Failed to parse user tenant response: {exc}") from exc

    # Alias for ResolveUserTenant
    ResolveUserTenant = resolve_user_tenant

    # ---------------------------------------------------------------------------
    # 2-Hop Authentication & Authorization Context
    # ---------------------------------------------------------------------------

    async def verify_token(self, token: str) -> TokenVerifyResponse:
        """Hop 1: Call external token verification endpoint (POST /api/v1/auth/verify)."""
        clean_token = token.strip()
        auth_header = clean_token if clean_token.lower().startswith("bearer ") else f"Bearer {clean_token}"
        url = f"{self.base_url}/api/v1/auth/verify"
        headers = {"Authorization": auth_header}

        try:
            response = await self._client.post(url, headers=headers)
        except Exception as exc:
            raise ClarOSAuthError(f"ClarOS verify_token request failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise ClarOSAuthError("Invalid or expired access token")
        if response.status_code != 200:
            raise ClarOSAPIError(response.status_code, f"Token verification failed: {response.text}")

        try:
            res = TokenVerifyResponse.model_validate(response.json())
        except Exception as exc:
            raise ClarOSAuthError(f"Failed to parse token verification response: {exc}") from exc

        if not res.success or not res.payload.valid:
            raise ClarOSAuthError(res.message or "Invalid or expired access token")

        return res

    async def resolve_tenant_auth_context(
        self,
        token: str,
        user_id: str,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> TenantAuthContextResponse:
        """Hop 2: Call external tenant authorization context endpoint (POST /api/v1/platform/authorize/context)."""
        clean_token = token.strip()
        auth_header = clean_token if clean_token.lower().startswith("bearer ") else f"Bearer {clean_token}"
        url = f"{self.base_url}/api/v1/platform/authorize/context"
        headers = {
            "Authorization": auth_header,
            "X-User-ID": user_id,
        }
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        if workspace_id:
            headers["X-Workspace-ID"] = workspace_id

        try:
            response = await self._client.post(url, headers=headers)
        except Exception as exc:
            raise ClarOSAuthError(f"ClarOS resolve_tenant_auth_context request failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise ClarOSAuthError("Unauthorized tenant context resolution")
        if response.status_code != 200:
            raise ClarOSAPIError(response.status_code, f"Tenant context resolution failed: {response.text}")

        try:
            res = TenantAuthContextResponse.model_validate(response.json())
        except Exception as exc:
            raise ClarOSAuthError(f"Failed to parse tenant auth context response: {exc}") from exc

        if not res.success or not res.payload.allowed:
            raise ClarOSAuthError(res.message or "Tenant authorization denied")

        return res

    async def authenticate(
        self,
        token: str,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> ClarOSAuthContext:
        """Authenticate user token and resolve full tenant authorization context in a single call."""
        verify_res = await self.verify_token(token)
        user_id = verify_res.payload.user_id

        ctx_res = await self.resolve_tenant_auth_context(
            token=token,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        p = ctx_res.payload
        return ClarOSAuthContext(
            user_id=p.user_id,
            tenant_id=p.tenant_id,
            tenant_slug=p.tenant_slug,
            role=p.role,
            permissions=p.permissions,
            license_tier=p.license_tier,
            headers=p.headers,
        )

    # ---------------------------------------------------------------------------
    # Inbound SSE Connection Management
    # ---------------------------------------------------------------------------

    def ensure_stream_connected(self) -> None:
        """Establish and maintain background SSE connection if not already running."""
        if self._stream_task and not self._stream_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
            self._stopped = False
            self._stream_task = loop.create_task(self._connect_sse())
        except RuntimeError:
            pass

    async def start_stream(self) -> None:
        """Start inbound SSE streaming task."""
        if self._stream_task and not self._stream_task.done():
            return
        self._stopped = False
        self._stream_task = asyncio.create_task(self._connect_sse())

    async def stop_stream(self) -> None:
        """Stop inbound SSE streaming task."""
        self._stopped = True
        if self._stream_task:
            task = self._stream_task
            self._stream_task = None
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._is_connected = False

    async def listen(self) -> None:
        """Block and stream SSE events continuously on current coroutine."""
        if self._stream_task and not self._stream_task.done():
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            return

        self._stopped = False
        await self._connect_sse()

    async def _connect_sse(self) -> None:
        """Establish SSE connection with auto-reconnect and dispatch frames."""
        lock = self._get_lock()
        if lock.locked():
            logger.debug("[Claros SDK] SSE connection already active, skipping duplicate connection.")
            return

        async with lock:
            while not self._stopped:
                url = f"{self.base_url}/api/v1/comm/inbound/stream"
                headers: dict[str, str] = {
                    "Accept": "text/event-stream",
                    "Cache-Control": "no-cache",
                }
                try:
                    auth_header = await self._get_auth_header()
                except Exception as exc:
                    logger.warning("[Claros SDK] Could not resolve auth header for SSE stream: %s", exc)
                    auth_header = None

                if auth_header:
                    headers["Authorization"] = auth_header
                if self._last_event_id:
                    headers["Last-Event-ID"] = self._last_event_id

                try:
                    async with self._client.stream("GET", url, headers=headers, timeout=None) as response:
                        if response.status_code != 200:
                            logger.error(
                                "[Claros SDK] Stream connection rejected (HTTP %d)",
                                response.status_code,
                            )
                            await self._schedule_reconnect()
                            continue

                        self._is_connected = True
                        self._reconnect_attempts = 0
                        logger.debug("[Claros SDK] SSE stream connected successfully")

                        current_event = "message"
                        current_data_lines: list[str] = []

                        async for line in response.aiter_lines():
                            if self._stopped:
                                break
                            if line.startswith(":"):
                                continue  # Heartbeat comment

                            if line.startswith("event:"):
                                current_event = line[6:].strip()
                            elif line.startswith("id:"):
                                self._last_event_id = line[3:].strip()
                            elif line.startswith("data:"):
                                current_data_lines.append(line[5:].strip())
                            elif line == "":
                                # End of SSE frame
                                if current_data_lines:
                                    raw_data = "\n".join(current_data_lines)
                                    await self._handle_event(current_event, raw_data)
                                current_event = "message"
                                current_data_lines = []

                        if not self._stopped:
                            self._is_connected = False
                            await self._schedule_reconnect()

                except asyncio.CancelledError:
                    self._is_connected = False
                    break
                except Exception as exc:
                    if self._stopped:
                        break
                    logger.error("[Claros SDK] Stream error: %s", exc)
                    self._is_connected = False
                    await self._schedule_reconnect()

    async def _handle_event(self, event_type: str, raw_data: str) -> None:
        """Dispatch events to dispatcher by event name and channel type."""
        try:
            payload = json.loads(raw_data)
        except Exception:
            await self.dispatcher.emit(event_type, raw_data)
            return

        # Deduplicate events by event_id to prevent duplicate handling
        if isinstance(payload, dict):
            event_id = payload.get("event_id")
            if event_id:
                if event_id in self._seen_event_ids:
                    logger.debug("[Claros SDK] Dropping duplicate event_id: %s", event_id)
                    return
                self._seen_event_ids.append(event_id)

        event_model: InboundMessageEvent | None = None
        if isinstance(payload, dict):
            try:
                event_model = InboundMessageEvent.model_validate(payload)
                event_model.set_client(self)
            except Exception:
                event_model = None

        dispatch_data = event_model if event_model is not None else payload

        # General event emit
        await self.dispatcher.emit(event_type, dispatch_data)

        # Dispatch channel specific event (e.g. "slack.message", "discord.message")
        if event_type == "message" and isinstance(payload, dict):
            channel_type = payload.get("channel_type")
            config_key = payload.get("config_key")
            if channel_type:
                await self.dispatcher.emit(f"{channel_type}.message", dispatch_data)
                if config_key:
                    await self.dispatcher.emit(
                        f"{channel_type}.message.{config_key}", dispatch_data
                    )

    async def _schedule_reconnect(self) -> None:
        """Auto-reconnect with exponential backoff & jitter."""
        if self._stopped:
            return
        self._is_connected = False
        self._reconnect_attempts += 1
        base_delay = min(1.0 * (2 ** self._reconnect_attempts), 30.0)
        delay = base_delay + random.uniform(0.0, 1.0)
        logger.debug(
            "[Claros SDK] Reconnecting in %.2fs (attempt %d)", delay, self._reconnect_attempts
        )
        await asyncio.sleep(delay)
