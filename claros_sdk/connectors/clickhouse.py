from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from claros_sdk.connectors.models import ConnectorTokenData
from claros_sdk.exceptions import ClarOSError

if TYPE_CHECKING:
    from clickhouse_connect.driver.client import Client

logger = logging.getLogger(__name__)


def _check_clickhouse_dependencies() -> None:
    """Verify clickhouse-connect package is installed."""
    try:
        import clickhouse_connect  # noqa: F401
    except ImportError as exc:
        raise ClarOSError(
            "ClickHouse connector dependency is not installed. "
            "Install it using: pip install 'claros-sdk[clickhouse]' or uv add 'claros-sdk[clickhouse]'"
        ) from exc


def build_clickhouse_client(
    token_data: ConnectorTokenData,
    **kwargs: Any,
) -> Client:
    """
    Construct and return an official ClickHouse client with credentials applied.

    Parameters:
        token_data: The connector token payload retrieved from ClarOS.
        **kwargs: Additional keyword arguments passed directly to clickhouse_connect.get_client().
    """
    _check_clickhouse_dependencies()

    import clickhouse_connect

    creds = token_data.credentials
    host = creds.get("host", "localhost")
    port = int(creds.get("port", 8123))
    username = creds.get("username", "default")
    password = creds.get("password", "")
    database = creds.get("database", "default")
    interface = creds.get("protocol", "http")

    conn_params: dict[str, Any] = {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "database": database,
        "interface": interface,
    }
    conn_params.update(kwargs)

    return clickhouse_connect.get_client(**conn_params)
