from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any

import httpx

from claros_sdk.connectors.models import ConnectorTokenData
from claros_sdk.exceptions import ClarOSError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class HTTPConnector:
    """
    HTTP Connector for custom HTTP / REST and MCP endpoints.

    Applies authentication credentials (none, basic, bearer, api_key) and default headers,
    and forwards requests directly to the target URL.
    """

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
        auth_type: str = "none",
        token_data: ConnectorTokenData | None = None,
        httpx_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = base_url
        self.auth_type = auth_type
        self.token_data = token_data
        self._headers = dict(headers or {})
        self._external_client = httpx_client is not None
        self._client = httpx_client or httpx.AsyncClient()

    @property
    def headers(self) -> dict[str, str]:
        """Configured base headers including auth."""
        return dict(self._headers)

    def _build_url(self, path: str = "") -> str:
        if not path:
            return self.url
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.url.rstrip('/')}/{path.lstrip('/')}"

    async def get(
        self,
        path: str = "",
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Execute a GET request against connector URL.

        # ponytail: return httpx.Response directly; upgrade to custom typed connector models if schema validation needed.
        """
        return await self.request(
            method="GET",
            path=path,
            params=params,
            headers=headers,
            **kwargs,
        )

    async def post(
        self,
        body: Any = None,
        path: str = "",
        *,
        json: Any = None,
        data: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Execute a POST request against connector URL.

        Parameters:
            body: Payload for the request. Dict/list is sent as JSON.
            path: Optional relative path or URL.
            json: Explicit JSON payload.
            data: Explicit data payload.
            params: Query parameters.
            headers: Additional request headers.

        # ponytail: return httpx.Response directly; upgrade to custom typed connector models if schema validation needed.
        """
        if path == "" and isinstance(body, str) and (body.startswith("/") or body.startswith("http://") or body.startswith("https://")):
            path = body
            body = None

        req_kwargs: dict[str, Any] = dict(kwargs)
        if json is not None:
            req_kwargs["json"] = json
        elif body is not None:
            if isinstance(body, (dict, list)):
                req_kwargs["json"] = body
            else:
                req_kwargs["content"] = body
        elif data is not None:
            req_kwargs["data"] = data

        return await self.request(
            method="POST",
            path=path,
            params=params,
            headers=headers,
            **req_kwargs,
        )

    async def request(
        self,
        method: str,
        path: str = "",
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an arbitrary HTTP request against connector URL."""
        url = self._build_url(path)
        req_headers = {**self._headers}
        if headers:
            req_headers.update(headers)

        return await self._client.request(
            method=method,
            url=url,
            params=params,
            headers=req_headers,
            **kwargs,
        )

    async def close(self) -> None:
        """Close underlying HTTP client if privately owned."""
        if not self._external_client and self._client:
            await self._client.aclose()

    async def __aenter__(self) -> HTTPConnector:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()


def build_http_connector(
    token_data: ConnectorTokenData,
    httpx_client: httpx.AsyncClient | None = None,
    **kwargs: Any,
) -> HTTPConnector:
    """
    Construct HTTPConnector with authentication and headers applied.

    Parameters:
        token_data: Connector token payload containing url and credentials.
        httpx_client: Optional custom httpx.AsyncClient.
    """
    creds = token_data.credentials or {}
    url = creds.get("url") or getattr(token_data, "url", None)
    if not url:
        raise ClarOSError(
            f"HTTP connector '{token_data.connection_key}' credentials missing required 'url' field"
        )

    auth_type = (creds.get("auth_type") or token_data.auth_type or "").lower()
    headers: dict[str, str] = dict(creds.get("headers") or {})

    # Infer auth_type if not explicitly set
    if not auth_type:
        if "username" in creds and "password" in creds:
            auth_type = "basic"
        elif "api_key" in creds:
            auth_type = "api_key"
        elif "token" in creds or token_data.token:
            auth_type = "bearer"
        else:
            auth_type = "none"

    if auth_type == "basic":
        username = str(creds.get("username", ""))
        password = str(creds.get("password", ""))
        auth_bytes = f"{username}:{password}".encode("latin1")
        b64_auth = base64.b64encode(auth_bytes).decode("ascii")
        headers["Authorization"] = f"Basic {b64_auth}"
    elif auth_type == "bearer":
        token = creds.get("token") or token_data.token or ""
        headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "api_key":
        api_key = creds.get("api_key") or token_data.token or ""
        header_name = creds.get("header_name") or "X-API-Key"
        headers[header_name] = str(api_key)
    elif auth_type == "none":
        pass

    return HTTPConnector(
        base_url=url,
        headers=headers,
        auth_type=auth_type,
        token_data=token_data,
        httpx_client=httpx_client,
        **kwargs,
    )
