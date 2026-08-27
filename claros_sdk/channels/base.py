from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from claros_sdk.client import ClarOSClient
    from claros_sdk.models import InboundMessageEvent


class BaseChannel:
    """Base class for modular ClarOS communication channels."""

    channel_type: str = ""

    def __init__(self, client: ClarOSClient, channel_type: str | None = None) -> None:
        self._client = client
        if channel_type is not None:
            self.channel_type = channel_type

    def on_message(
        self, handler: Callable[[InboundMessageEvent], Any] | None = None
    ) -> Callable[[InboundMessageEvent], Any]:
        """
        Register a listener for inbound messages for this channel.
        Can be used as a method call or a decorator:

            client.slack.on_message(my_handler)

            @client.slack.on_message
            async def my_handler(event: InboundMessageEvent): ...
        """
        self._client.ensure_stream_connected()
        event_name = f"{self.channel_type}.message" if self.channel_type else "message"
        return self._client.dispatcher.on(event_name, handler)

    def on(
        self, event_name: str, handler: Callable[..., Any] | None = None
    ) -> Callable[..., Any]:
        """
        Register a generic event listener under this channel's namespace.
        Can be used as a method call or a decorator.
        """
        self._client.ensure_stream_connected()
        full_event_name = (
            f"{self.channel_type}.{event_name}" if self.channel_type else event_name
        )
        return self._client.dispatcher.on(full_event_name, handler)

    def off_message(self, handler: Callable[[InboundMessageEvent], Any]) -> None:
        """Remove a previously registered message listener."""
        event_name = f"{self.channel_type}.message" if self.channel_type else "message"
        self._client.dispatcher.off(event_name, handler)

    async def send(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Send a message through this channel."""
        raise NotImplementedError("Channel subclasses must implement send()")
