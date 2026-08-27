from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from claros_sdk.channels.base import BaseChannel

if TYPE_CHECKING:
    from claros_sdk.client import ClarOSClient
    from claros_sdk.models import InboundMessageEvent


class DiscordBot:
    """Scoped Discord bot client bound to a specific config_key."""

    def __init__(self, channel: DiscordChannel, config_key: str) -> None:
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


class DiscordChannel(BaseChannel):
    """Channel adapter for Discord messaging and inbound events."""

    channel_type: str = "discord"

    def __init__(self, client: ClarOSClient) -> None:
        super().__init__(client=client, channel_type="discord")

    def bot(self, config_key: str) -> DiscordBot:
        """Create a scoped Discord bot client for a specific config_key."""
        return DiscordBot(self, config_key=config_key)

    async def send(
        self,
        message: str = "",
        channel: str | None = None,
        title: str | None = None,
        config_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Send a Discord message.

        Args:
            message: Message body text (mapped to 'message' in inner payload)
            channel: Target Discord channel (mapped to 'recipient' in inner payload, optional)
            title: Message title (mapped to 'title' in inner payload, optional)
            config_key: Bot configuration key (optional)
            **kwargs: Extra parameters passed to API payload
        """
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

        return await self._client.post("/api/v1/comm/discord", json=payload)
