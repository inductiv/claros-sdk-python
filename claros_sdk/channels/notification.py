from __future__ import annotations

from typing import TYPE_CHECKING, Any

from claros_sdk.channels.base import BaseChannel

if TYPE_CHECKING:
    from claros_sdk.client import ClarOSClient


class NotificationChannel(BaseChannel):
    """Channel adapter for In-App notification messaging."""

    channel_type: str = "in-app"

    def __init__(self, client: ClarOSClient) -> None:
        super().__init__(client=client, channel_type="in-app")

    async def send(
        self,
        title: str,
        message: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Send an in-app notification via ClarOS Communication API.

        Args:
            title: Title of the notification (required)
            message: Message body (required)
            action_url: Optional URL action link
            severity: Optional severity level (e.g. 'info', 'warning', 'error')
            metadata: Optional dictionary with custom metadata
            **kwargs: Extra parameters passed to API payload
        """
        if not title:
            raise ValueError("title is required")
        if not message:
            raise ValueError("message is required")

        payload: dict[str, Any] = {
            "title": title,
            "message": message,
        }
        payload.update(kwargs)

        return await self._client.post(f"/api/v1/comm/{self.channel_type}", json=payload)
