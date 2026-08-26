from __future__ import annotations

from typing import TYPE_CHECKING, Any

from claros_sdk.channels.base import BaseChannel

if TYPE_CHECKING:
    from claros_sdk.client import ClarOSClient


class EmailChannel(BaseChannel):
    """Channel adapter for Email messaging and inbound events."""

    channel_type: str = "email"

    def __init__(self, client: ClarOSClient) -> None:
        super().__init__(client=client, channel_type="email")

    async def send(
        self,
        recipient_email: str,
        recipient_name: str | None = None,
        subject: str = "",
        template_name: str = "welcome-email",
        template_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Send an email via ClarOS Communication API.

        Usage:
            await client.email.send(
                recipient_email="user@example.com",
                recipient_name="John Doe",
                subject="Welcome!",
                template_name="welcome-email",
                template_data={"Name": "John"},
            )

        Args:
            recipient_email: Target email address
            recipient_name: Target recipient name (defaults to email prefix)
            subject: Email subject line
            template_name: Template identifier
            template_data: Dictionary containing template substitution data
            **kwargs: Extra parameters passed to API payload
        """
        payload: dict[str, Any] = {
            "recipient_email": recipient_email,
            "recipient_name": recipient_name or recipient_email.split("@")[0],
            "subject": subject,
            "template_name": template_name,
            "template_data": template_data or {},
            **kwargs,
        }

        return await self._client.post("/api/v1/comm/email", json=payload)
