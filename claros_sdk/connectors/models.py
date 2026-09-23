from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConnectorTokenData(BaseModel):
    """Token and credentials payload for a third-party connection."""

    model_config = ConfigDict(extra="allow")

    connection_key: str
    provider: str
    credentials: dict[str, Any] = Field(default_factory=dict)
    auth_type: str | None = None
    connector_id: str | None = None
    status: str | None = None
    tenant_id: str | None = None
    metadata: Any = None
    expires_at: datetime | str | None = None
    expires_in: int | float | None = None

    token: str | None = None
    token_type: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if not self.token:
            if "access_token" in self.credentials:
                object.__setattr__(self, "token", self.credentials["access_token"])
            elif "token" in self.credentials:
                object.__setattr__(self, "token", self.credentials["token"])
            elif "api_key" in self.credentials:
                object.__setattr__(self, "token", self.credentials["api_key"])
            else:
                object.__setattr__(self, "token", "")
        elif self.token and not self.credentials:
            object.__setattr__(self, "credentials", {"token": self.token, "api_key": self.token})

        if not self.token_type:
            tt = self.credentials.get("token_type") or "Bearer"
            object.__setattr__(self, "token_type", tt)


class ConnectorResolveResponse(BaseModel):
    """Response returned by ClarOS GET /api/v1/platform/connectors/:key/resolve."""

    model_config = ConfigDict(extra="allow")

    success: bool = True
    message: str = ""
    payload: ConnectorTokenData | None = None
    data: ConnectorTokenData | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.payload is None and self.data is not None:
            object.__setattr__(self, "payload", self.data)
        elif self.data is None and self.payload is not None:
            object.__setattr__(self, "data", self.payload)


ConnectorResolvePayload = ConnectorTokenData
ConnectorTokenResponse = ConnectorResolveResponse


class CachedConnectorToken:
    """In-memory cache entry for a connector token with expiration tracking."""

    def __init__(
        self,
        data: ConnectorTokenData,
        cached_at: float | None = None,
    ) -> None:
        self.data = data
        self.cached_at = cached_at if cached_at is not None else time.time()

    @property
    def token(self) -> str:
        return self.data.token or ""

    def is_valid(self, leeway_seconds: float = 60.0) -> bool:
        """
        Check whether the cached token is still valid.
        Considers either expires_at (ISO datetime) or expires_in (seconds).
        Returns True if no expiration is specified (e.g. permanent API keys).
        """
        current_time = time.time()

        if self.data.expires_at is not None:
            if isinstance(self.data.expires_at, datetime):
                expires_at_dt = self.data.expires_at
            else:
                try:
                    dt_str = str(self.data.expires_at).replace("Z", "+00:00")
                    expires_at_dt = datetime.fromisoformat(dt_str)
                except Exception:
                    expires_at_dt = None

            if expires_at_dt is not None:
                if expires_at_dt.tzinfo is None:
                    expires_at_dt = expires_at_dt.replace(tzinfo=timezone.utc)
                expire_timestamp = expires_at_dt.timestamp()
                return current_time < (expire_timestamp - leeway_seconds)

        if self.data.expires_in is not None:
            expire_timestamp = self.cached_at + float(self.data.expires_in)
            return current_time < (expire_timestamp - leeway_seconds)

        return True
