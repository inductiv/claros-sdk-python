from __future__ import annotations

import logging
from typing import Any

from claros_sdk.connectors.models import ConnectorTokenData
from claros_sdk.exceptions import ClarOSError

logger = logging.getLogger(__name__)


def _check_stripe_dependencies() -> None:
    """Verify stripe package is installed."""
    try:
        import stripe  # noqa: F401
    except ImportError as exc:
        raise ClarOSError(
            "Stripe connector dependency is not installed. "
            "Install it using: pip install 'claros-sdk[stripe]' or uv add 'claros-sdk[stripe]'"
        ) from exc


def build_stripe_client(
    token_data: ConnectorTokenData,
    **kwargs: Any,
) -> Any:
    """
    Construct and return an official Stripe client with api_key applied.

    Parameters:
        token_data: The connector token payload retrieved from ClarOS.
        **kwargs: Additional keyword arguments passed directly to stripe.StripeClient().
    """
    _check_stripe_dependencies()

    import stripe

    return stripe.StripeClient(api_key=token_data.token, **kwargs)
