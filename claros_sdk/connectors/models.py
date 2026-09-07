from __future__ import annotations

from datetime import datetime, timezone
import time

from pydantic import BaseModel, ConfigDict


class ConnectorTokenData(BaseModel):
    """Token and metadata payload for a third-party connection."""

    model_config = ConfigDict(extra="allow")

    token: str
    token_type: str = "Bearer"
    expires_at: datetime | str | None = None
    expires_in: int | float | None = None
    provider: str
    connection_key: str


class ConnectorTokenResponse(BaseModel):
    """Response returned by ClarOS GET /api/v1/platform/connectors/:key/token."""

    model_config = ConfigDict(extra="allow")

    code: int = 200
    message: str = ""
    data: ConnectorTokenData


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
        return self.data.token

    def is_valid(self, leeway_seconds: float = 60.0) -> bool:
        """
        Check whether the cached token is still valid.
        Considers either expires_at (ISO datetime) or expires_in (seconds).
        Returns True if no expiration is specified (e.g. permanent API keys).
        """
        current_time = time.time()

        # Check expires_at if present
        if self.data.expires_at is not None:
            if isinstance(self.data.expires_at, datetime):
                expires_at_dt = self.data.expires_at
            else:
                try:
                    # Support ISO strings like 2026-09-07T12:58:30Z
                    dt_str = str(self.data.expires_at).replace("Z", "+00:00")
                    expires_at_dt = datetime.fromisoformat(dt_str)
                except Exception:
                    expires_at_dt = None

            if expires_at_dt is not None:
                if expires_at_dt.tzinfo is None:
                    expires_at_dt = expires_at_dt.replace(tzinfo=timezone.utc)
                expire_timestamp = expires_at_dt.timestamp()
                return current_time < (expire_timestamp - leeway_seconds)

        # Fall back to expires_in relative to cached_at
        if self.data.expires_in is not None:
            expire_timestamp = self.cached_at + float(self.data.expires_in)
            return current_time < (expire_timestamp - leeway_seconds)

        # If neither expiration is given (e.g. ApiKey), consider token valid
        return True
