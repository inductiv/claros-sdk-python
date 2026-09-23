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


class ChannelBot:
    """Scoped bot client bound to a specific config_key."""

    def __init__(self, channel: ChatChannel, config_key: str) -> None:
        self._channel = channel
        self.config_key = config_key

    async def send(
        self,
        message: str = "",
        channel: str | None = None,
        title: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a message scoped to this bot's config_key."""
        return await self._channel.send(
            message=message,
            channel=channel,
            title=title,
            config_key=self.config_key,
            **kwargs,
        )

    def on_message(
        self, handler: Callable[[InboundMessageEvent], Any] | None = None
    ) -> Callable[[InboundMessageEvent], Any]:
        """Listen only to messages sent to this bot (matching config_key)."""
        self._channel._client.ensure_stream_connected()
        event_name = f"{self._channel.channel_type}.message.{self.config_key}"
        return self._channel._client.dispatcher.on(event_name, handler)


class ChatChannel(BaseChannel):
    """Base adapter for chat messaging channels (Slack, Discord)."""

    bot_class: type[ChannelBot] = ChannelBot

    def bot(self, config_key: str) -> Any:
        """Create a scoped bot client for a specific config_key."""
        return self.bot_class(self, config_key=config_key)

    async def send(
        self,
        message: str = "",
        channel: str | None = None,
        title: str | None = None,
        config_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a chat message."""
        payload: dict[str, Any] = {}
        if message:
            payload["message"] = message
        if title:
            payload["title"] = title
        if channel:
            payload["recipient"] = channel
        if config_key is not None:
            payload["config_key"] = config_key
        payload.update(kwargs)
        return await self._client.post(f"/api/v1/comm/{self.channel_type}", json=payload)

