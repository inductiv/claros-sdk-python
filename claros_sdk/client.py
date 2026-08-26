from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from claros_sdk.exceptions import ClarOSAPIError, ClarOSAuthError, ClarOSError
from claros_sdk.models import (
    ClarOSAuthContext,
    TenantAuthContextResponse,
    TokenVerifyResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_LEEWAY_SECONDS = 60


class ClarOSClient:
    """Client SDK for ClarOS Communication & Auth Service."""

    def __init__(
        self,
        base_url: str,
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

    async def __aenter__(self) -> ClarOSClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    @property
    def access_token(self) -> str | None:
        return self._access_token

    @property
    def is_token_valid(self) -> bool:
        return bool(
            self._access_token and time.time() < (self._expires_at - DEFAULT_LEEWAY_SECONDS)
        )

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
    # Communication Endpoints
    # ---------------------------------------------------------------------------

    async def send_email(
        self,
        recipient_email: str,
        recipient_name: str | None = None,
        subject: str = "",
        template_name: str = "welcome-email",
        template_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an email via ClarOS Communication API."""
        token = await self.get_token()
        url = f"{self.base_url}/api/v1/comm/email"
        payload = {
            "recipient_email": recipient_email,
            "recipient_name": recipient_name or recipient_email.split("@")[0],
            "subject": subject,
            "template_name": template_name,
            "template_data": template_data or {},
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._client.post(url, json=payload, headers=headers)
        except Exception as exc:
            raise ClarOSError(f"ClarOS send_email request failed: {exc}") from exc

        if response.status_code not in (200, 201, 202):
            raise ClarOSAPIError(
                status_code=response.status_code,
                message=response.text,
                payload=payload,
            )

        try:
            return response.json()
        except Exception:
            return {"status": "ok", "status_code": response.status_code}

    async def send_slack(
        self,
        title: str,
        message: str,
        channel: str | None = None,
    ) -> dict[str, Any]:
        """Send a Slack notification via ClarOS Communication API."""
        token = await self.get_token()
        url = f"{self.base_url}/api/v1/comm/slack"
        payload = {
            "title": title,
            "message": message,
            "recipient": channel,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._client.post(url, json=payload, headers=headers)
        except Exception as exc:
            raise ClarOSError(f"ClarOS send_slack request failed: {exc}") from exc

        if response.status_code not in (200, 201, 202):
            raise ClarOSAPIError(
                status_code=response.status_code,
                message=response.text,
                payload=payload,
            )

        try:
            return response.json()
        except Exception:
            return {"status": "ok", "status_code": response.status_code}
