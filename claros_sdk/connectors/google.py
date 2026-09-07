from __future__ import annotations

import logging
from typing import Any

from claros_sdk.connectors.models import ConnectorTokenData
from claros_sdk.exceptions import ClarOSError

logger = logging.getLogger(__name__)

DEFAULT_SERVICE_VERSIONS: dict[str, str] = {
    "sheets": "v4",
    "drive": "v3",
    "gmail": "v1",
    "calendar": "v3",
    "docs": "v1",
    "slides": "v1",
    "bigquery": "v2",
    "admin": "directory_v1",
}


def _check_google_dependencies() -> None:
    """Verify Google API Python Client and Google Auth packages are installed."""
    try:
        import google.auth  # noqa: F401
        import google.oauth2.credentials  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
    except ImportError as exc:
        raise ClarOSError(
            "Google connector dependencies are not installed. "
            "Install them using: pip install 'claros-sdk[google]' or uv add 'claros-sdk[google]'"
        ) from exc


def build_google_client(
    token_data: ConnectorTokenData,
    service: str = "sheets",
    version: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    Construct and return the raw official Google API client Resource with credentials applied.

    Parameters:
        token_data: The connector token payload retrieved from ClarOS.
        service: Google service name (e.g. 'sheets', 'drive', 'gmail'). Defaults to 'sheets'.
        version: API version (e.g. 'v4' for sheets). If None, resolves from DEFAULT_SERVICE_VERSIONS.
        **kwargs: Additional parameters passed directly to googleapiclient.discovery.build().
    """
    _check_google_dependencies()

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if version is None:
        version = DEFAULT_SERVICE_VERSIONS.get(service, "v1")

    # Initialize Google OAuth2 credentials with the Bearer access token
    credentials = Credentials(token=token_data.token)

    # Build and return the raw official Google API resource
    return build(serviceName=service, version=version, credentials=credentials, **kwargs)
