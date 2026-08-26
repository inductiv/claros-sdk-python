import json
import httpx
import pytest
from claros_sdk import ClarOSClient
from claros_sdk.channels import BaseChannel, DiscordBot, DiscordChannel, EmailChannel, SlackBot, SlackChannel


def create_channels_mock_transport():
    call_counts = {"token": 0, "slack": 0, "email": 0, "discord": 0}
    last_requests = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        last_requests[path] = request

        if path == "/api/v1/auth/oauth/token":
            call_counts["token"] += 1
            return httpx.Response(
                200,
                json={"access_token": "mock-token-abc", "expires_in": 3600},
            )
        elif path == "/api/v1/comm/slack":
            call_counts["slack"] += 1
            return httpx.Response(200, json={"status": "delivered", "ok": True})
        elif path == "/api/v1/comm/email":
            call_counts["email"] += 1
            return httpx.Response(200, json={"status": "sent", "id": "email-1"})
        elif path == "/api/v1/comm/discord":
            call_counts["discord"] += 1
            return httpx.Response(200, json={"status": "delivered", "ok": True})

        return httpx.Response(404, json={"error": "Not Found"})

    return httpx.MockTransport(handler), call_counts, last_requests


@pytest.mark.asyncio
async def test_slack_channel_send_and_scoped_bot():
    transport, call_counts, last_requests = create_channels_mock_transport()
    httpx_client = httpx.AsyncClient(transport=transport)

    client = ClarOSClient(
        base_url="https://api.claros.ai",
        client_id="sa_test_123",
        client_secret="secret_test_456",
        httpx_client=httpx_client,
    )

    assert isinstance(client.slack, SlackChannel)

    # 1. Fallback to default (no channel, no config_key - e.g. Webhook) with message & title
    res1 = await client.slack.send(title="Alert", message="Deployment completed")
    assert res1["status"] == "delivered"
    payload1 = json.loads(last_requests["/api/v1/comm/slack"].content)
    assert payload1 == {"title": "Alert", "message": "Deployment completed"}
    assert "recipient" not in payload1
    assert "channel" not in payload1
    assert "text" not in payload1

    # 2. Inline parameters with channel, title, and config_key
    res2 = await client.slack.send(
        config_key="ABC-bot",
        channel="C0123456789",
        title="Support Notification",
        message="Hello from Customer Support Bot!",
    )
    assert res2["status"] == "delivered"
    payload2 = json.loads(last_requests["/api/v1/comm/slack"].content)
    assert payload2["recipient"] == "C0123456789"
    assert payload2["config_key"] == "ABC-bot"
    assert payload2["title"] == "Support Notification"
    assert payload2["message"] == "Hello from Customer Support Bot!"
    assert "channel" not in payload2

    # 3. Scoped bot client
    support_bot = client.slack.bot("ABC-bot")
    billing_bot = client.slack.bot("XYZ-bot")
    assert isinstance(support_bot, SlackBot)
    assert isinstance(billing_bot, SlackBot)

    await support_bot.send(channel="C123", message="Support ticket opened")
    payload_support = json.loads(last_requests["/api/v1/comm/slack"].content)
    assert payload_support["recipient"] == "C123"
    assert payload_support["config_key"] == "ABC-bot"
    assert payload_support["message"] == "Support ticket opened"

    await billing_bot.send(channel="C456", title="Invoice", message="Invoice generated")
    payload_billing = json.loads(last_requests["/api/v1/comm/slack"].content)
    assert payload_billing["recipient"] == "C456"
    assert payload_billing["config_key"] == "XYZ-bot"
    assert payload_billing["title"] == "Invoice"
    assert payload_billing["message"] == "Invoice generated"

    await client.close()


@pytest.mark.asyncio
async def test_email_channel_send_modular():
    transport, call_counts, last_requests = create_channels_mock_transport()
    httpx_client = httpx.AsyncClient(transport=transport)

    client = ClarOSClient(
        base_url="https://api.claros.ai",
        client_id="sa_test_123",
        client_secret="secret_test_456",
        httpx_client=httpx_client,
    )

    assert isinstance(client.email, EmailChannel)

    res = await client.email.send(
        recipient_email="jane@example.com",
        recipient_name="Jane Doe",
        subject="Welcome Onboard",
        template_name="welcome",
        template_data={"Team": "Engineering"},
    )
    assert res["status"] == "sent"
    assert call_counts["email"] == 1

    last_req = last_requests["/api/v1/comm/email"]
    payload = json.loads(last_req.content)
    assert payload["recipient_email"] == "jane@example.com"
    assert payload["recipient_name"] == "Jane Doe"
    assert payload["subject"] == "Welcome Onboard"
    assert payload["template_name"] == "welcome"
    assert payload["template_data"] == {"Team": "Engineering"}

    await client.close()


@pytest.mark.asyncio
async def test_discord_channel_send_and_scoped_bot():
    transport, call_counts, last_requests = create_channels_mock_transport()
    httpx_client = httpx.AsyncClient(transport=transport)

    client = ClarOSClient(
        base_url="https://api.claros.ai",
        client_id="sa_test_123",
        client_secret="secret_test_456",
        httpx_client=httpx_client,
    )

    assert isinstance(client.discord, DiscordChannel)

    discord_bot = client.discord.bot("discord-main")
    assert isinstance(discord_bot, DiscordBot)

    res = await discord_bot.send(
        channel="9876543210",
        title="Notice",
        message="Discord announcement",
    )
    assert res["status"] == "delivered"
    assert call_counts["discord"] == 1

    last_req = last_requests["/api/v1/comm/discord"]
    payload = json.loads(last_req.content)
    assert payload["recipient"] == "9876543210"
    assert payload["config_key"] == "discord-main"
    assert payload["title"] == "Notice"
    assert payload["message"] == "Discord announcement"
    assert "channel" not in payload

    # Generic channel lookup
    custom_ch = client.channel("whatsapp")
    assert isinstance(custom_ch, BaseChannel)
    assert custom_ch.channel_type == "whatsapp"

    await client.close()
