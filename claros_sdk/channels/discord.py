from __future__ import annotations

from typing import TYPE_CHECKING

from claros_sdk.channels.base import ChannelBot, ChatChannel

if TYPE_CHECKING:
    from claros_sdk.client import ClarOSClient


class DiscordBot(ChannelBot):
    """Scoped Discord bot client bound to a specific config_key."""


class DiscordChannel(ChatChannel):
    """Channel adapter for Discord messaging and inbound events."""

    channel_type: str = "discord"
    bot_class = DiscordBot

    def __init__(self, client: ClarOSClient) -> None:
        super().__init__(client=client, channel_type="discord")

    def bot(self, config_key: str) -> DiscordBot:
        """Create a scoped Discord bot client for a specific config_key."""
        return DiscordBot(self, config_key=config_key)
