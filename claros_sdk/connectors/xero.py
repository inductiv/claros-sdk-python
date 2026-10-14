from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from claros_sdk.connectors.models import ConnectorTokenData
from claros_sdk.exceptions import ClarOSError

if TYPE_CHECKING:
    from xero_python.api_client import ApiClient

logger = logging.getLogger(__name__)


def _check_xero_dependencies() -> None:
    """Verify xero-python package is installed."""
    try:
        import xero_python  # noqa: F401
    except ImportError as exc:
        raise ClarOSError(
            "Xero connector dependency is not installed. "
            "Install it using: pip install 'claros-sdk[xero]' or uv add 'claros-sdk[xero]'"
        ) from exc


def build_xero_client(
    token_data: ConnectorTokenData,
    **kwargs: Any,
) -> ApiClient:
    """
    Construct and return an official Xero ApiClient with credentials applied.

    Parameters:
        token_data: The connector token payload retrieved from ClarOS.
        **kwargs: Additional arguments passed to Configuration() or ApiClient().
    """
    _check_xero_dependencies()

    from xero_python.api_client import ApiClient
    from xero_python.api_client.configuration import Configuration
    from xero_python.api_client.oauth2 import OAuth2Token

    creds = token_data.credentials
    access_token = creds.get("access_token") or token_data.token or ""
    token_type = creds.get("token_type") or token_data.token_type or "Bearer"
    scope = creds.get("scope") or ""
    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")
    refresh_token = creds.get("refresh_token")
    id_token = creds.get("id_token")
    expires_in = creds.get("expires_in") or token_data.expires_in

    expires_at_ts: float | None = None
    if client_id and client_secret and refresh_token:
        expires_at = creds.get("expires_at") or token_data.expires_at
        if isinstance(expires_at, (int, float)):
            expires_at_ts = float(expires_at)
        elif isinstance(expires_at, datetime):
            expires_at_ts = expires_at.timestamp()
        elif isinstance(expires_at, str):
            try:
                expires_at_ts = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
            except Exception:
                expires_at_ts = None

    token_dict: dict[str, Any] = {
        "access_token": access_token,
        "token_type": token_type,
        "scope": scope,
        "expires_in": expires_in,
        "expires_at": expires_at_ts,
        "refresh_token": refresh_token,
        "id_token": id_token,
    }

    oauth2_token = OAuth2Token(client_id=client_id, client_secret=client_secret)
    oauth2_token.update_token(**token_dict)

    config = kwargs.pop("configuration", None)
    if config is None:
        config = Configuration()
        config.oauth2_token = oauth2_token
        if "debug" in kwargs:
            config.debug = kwargs.pop("debug")
    elif config.oauth2_token is None:
        config.oauth2_token = oauth2_token

    def _default_saver(new_token: dict[str, Any]) -> None:
        token_dict.update(new_token)

    getter = kwargs.pop("oauth2_token_getter", lambda: token_dict)
    saver = kwargs.pop("oauth2_token_saver", _default_saver)

    tenant_id = (
        kwargs.pop("tenant_id", None)
        or token_data.tenant_id
        or creds.get("tenant_id")
        or creds.get("xero_tenant_id")
    )

    client = ApiClient(
        configuration=config,
        oauth2_token_getter=getter,
        oauth2_token_saver=saver,
        **kwargs,
    )

    if tenant_id:
        client.set_default_header("xero-tenant-id", tenant_id)

    return client
