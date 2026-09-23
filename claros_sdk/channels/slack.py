from __future__ import annotations

from typing import TYPE_CHECKING

from claros_sdk.channels.base import ChannelBot, ChatChannel

if TYPE_CHECKING:
    from claros_sdk.client import ClarOSClient


class SlackBot(ChannelBot):
    """Scoped Slack bot client bound to a specific config_key."""


class SlackChannel(ChatChannel):
    """Channel adapter for Slack messaging and inbound events."""

    channel_type: str = "slack"
    bot_class = SlackBot

    def __init__(self, client: ClarOSClient) -> None:
        super().__init__(client=client, channel_type="slack")

    def bot(self, config_key: str) -> SlackBot:
        """Create a scoped Slack bot client for a specific config_key."""
        return SlackBot(self, config_key=config_key)
