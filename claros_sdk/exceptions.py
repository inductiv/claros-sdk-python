from __future__ import annotations


class ClarOSError(Exception):
    """Base exception for ClarOS SDK errors."""


class ClarOSAuthError(ClarOSError):
    """Raised when authentication or token acquisition fails."""


class ClarOSAPIError(ClarOSError):
    """Raised when an API endpoint returns an error status code."""

    def __init__(self, status_code: int, message: str, payload: dict | None = None) -> None:
        super().__init__(f"ClarOS API Error [{status_code}]: {message}")
        self.status_code = status_code
        self.message = message
        self.payload = payload or {}
