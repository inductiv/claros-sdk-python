from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from claros_sdk.exceptions import ClarOSError


class TokenVerifyPayload(BaseModel):
    """Payload returned by ClarOS token verification service."""

    valid: bool
    user_id: str
    session_id: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class TokenVerifyResponse(BaseModel):
    """Top-level response envelope from ClarOS token verification service."""

    success: bool
    message: str
    payload: TokenVerifyPayload


class TenantAuthContextPayload(BaseModel):
    """Payload returned by ClarOS tenant authorization service."""

    allowed: bool
    user_id: str
    tenant_id: str
    tenant_slug: str
    role: str
    permissions: list[str] = Field(default_factory=list)
    license_tier: str
    headers: dict[str, str] = Field(default_factory=dict)


class TenantAuthContextResponse(BaseModel):
    """Top-level response envelope from ClarOS tenant authorization service."""

    success: bool
    message: str
    payload: TenantAuthContextPayload


class ClarOSAuthContext(BaseModel):
    """Resolved authorization context model returned after authentication."""

    user_id: str
    tenant_id: str
    tenant_slug: str
    role: str
    permissions: list[str] = Field(default_factory=list)
    license_tier: str
    headers: dict[str, str] = Field(default_factory=dict)


class InboundEventSource(BaseModel):
    """Source context of an inbound message event."""

    workspace_id: str = ""
    channel_id: str = ""
    user_id: str = ""
    thread_id: str | None = None
    message_id: str = ""

    model_config = {"extra": "allow"}


class InboundEventMessage(BaseModel):
    """Message payload within an inbound event."""

    text: str = ""
    event_type: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class InboundMessageEvent(BaseModel):
    """Inbound message event received from ClarOS SSE stream."""

    event_id: str = ""
    tenant_id: str = ""
    config_key: str = ""
    channel_type: str = ""
    received_at: str = ""
    source: InboundEventSource = Field(default_factory=InboundEventSource)
    message: InboundEventMessage = Field(default_factory=InboundEventMessage)

    model_config = {"extra": "allow", "arbitrary_types_allowed": True}

    def set_client(self, client: Any) -> None:
        """Attach client instance for contextual auto-reply."""
        object.__setattr__(self, "_client", client)

    async def reply(
        self,
        message: str = "",
        text: str = "",
        title: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Contextual auto-reply: automatically replies using the receiving
        bot/config_key and channel.
        """
        client = getattr(self, "_client", None)
        if not client:
            raise ClarOSError("Cannot reply: No active ClarOSClient bound to this event.")

        channel_id = self.source.channel_id or self.source.user_id
        target_channel = channel_id if channel_id else None
        config_key = self.config_key if self.config_key else None
        msg = message or text or ""

        if self.channel_type == "slack":
            return await client.slack.send(
                channel=target_channel,
                message=msg,
                title=title,
                config_key=config_key,
                **kwargs,
            )
        elif self.channel_type == "discord":
            return await client.discord.send(
                channel=target_channel,
                message=msg,
                title=title,
                config_key=config_key,
                **kwargs,
            )
        else:
            return await client.channel(self.channel_type).send(
                channel=target_channel,
                message=msg,
                title=title,
                config_key=config_key,
                **kwargs,
            )
