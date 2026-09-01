from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

try:
    from starlette.requests import Request
except ImportError:
    try:
        from fastapi import Request
    except ImportError:
        Request = Any  # type: ignore[misc,assignment]

from claros_sdk.client import ClarOSClient
from claros_sdk.exceptions import ClarOSAuthError
from claros_sdk.models import ClarOSAuthContext

logger = logging.getLogger(__name__)


def extract_bearer_token(
    headers: dict[str, str], cookies: dict[str, str] | None = None
) -> str | None:
    """Extract Bearer token from Authorization header or cookies."""
    auth_header = headers.get("Authorization") or headers.get("authorization")
    if auth_header and auth_header.strip():
        token = auth_header.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        return token

    if cookies:
        token = cookies.get("access_token")
        if token and token.strip():
            return token.strip()

    return None


class ClarOSGuard:
    """
    ClarOS Authentication & Authorization Guard for FastAPI routes.

    Usage:
        guard = ClarOSGuard(get_claros_client)

        @app.get("/api/v1/protected")
        async def protected_route(auth: ClarOSAuthContext = Depends(guard)):
            return {"user_id": auth.user_id, "tenant_id": auth.tenant_id}
    """

    def __init__(
        self,
        client_factory: Callable[[], ClarOSClient] | ClarOSClient | None = None,
    ) -> None:
        self.client_factory = client_factory

    async def __call__(
        self,
        request: Request,
        token: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> ClarOSAuthContext:
        headers_dict = dict(request.headers)
        cookies_dict = dict(request.cookies) if hasattr(request, "cookies") else {}

        bearer_token = token or extract_bearer_token(headers_dict, cookies_dict)
        if not bearer_token:
            raise ClarOSAuthError(
                "Authentication required: missing Bearer token or access_token cookie"
            )

        target_tenant_id = tenant_id or headers_dict.get("X-Tenant-ID") or headers_dict.get("x-tenant-id")
        target_workspace_id = workspace_id or headers_dict.get("X-Workspace-ID") or headers_dict.get("x-workspace-id")

        if callable(self.client_factory):
            client = self.client_factory()
        elif isinstance(self.client_factory, ClarOSClient):
            client = self.client_factory
        else:
            raise ClarOSAuthError("ClarOSGuard requires a valid client or client_factory")

        auth_context = await client.authenticate(
            token=bearer_token,
            tenant_id=target_tenant_id,
            workspace_id=target_workspace_id,
        )

        if hasattr(request, "state"):
            request.state.auth_headers = auth_context.headers
            request.state.claros_auth_context = auth_context

        return auth_context
