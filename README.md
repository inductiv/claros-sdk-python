# ClarOS Python SDK

Python SDK for machine-to-machine (M2M) communication, templated email delivery, scoped bot routing, inbound Server-Sent Events (SSE) streaming, user authentication, and tenant authorization via the ClarOS platform services.

---

## 1. Outbound Communication

### A. Slack Messaging
Send messages to webhooks or specific Slack channels using `client.slack.send()`:

```python
# 1. Fallback to default Webhook
await client.slack.send(
    title="Deploy Alert",
    message="🚨 Deployment completed successfully",
)

# 2. Send to specific channel
await client.slack.send(
    channel="C0123456789",
    title="New Lead",
    message="A new customer requested a demo.",
)

# 3. Scoped Bot Builder
support_bot = client.slack.bot("ABC-bot")
billing_bot = client.slack.bot("XYZ-bot")

await support_bot.send(channel="C123", message="Support ticket opened")
await billing_bot.send(channel="C456", title="Invoice", message="Invoice generated")
```

---

### B. Transactional & Templated Email Delivery
Send templated transactional emails via Go `html/template` / `templ` compatible engines using `client.email.send()`:

```python
# `template_name` and `recipient_email` are required
response = await client.email.send(
    recipient_email="john.doe@example.com",
    template_name="monthly-kpi-report",
    recipient_name="John Doe",
    subject="Monthly KPI Report - August 2026",
    template_data={
        "Greeting": "Hi John,",
        "ReportDate": "August 2026",
        "MRR": "$124,500",
        "NewUsers": "1,420",
    },
)
print(f"Email sent with status: {response.get('status')}")
```

---

### C. Discord Messaging
```python
await client.discord.send(
    channel="9876543210",
    title="System Notice",
    message="Server maintenance scheduled for 02:00 UTC.",
)
```

---

## 2. Inbound (Receiving Messages via SSE)

Incoming SSE events delivered over `/api/v1/comm/inbound/stream` embed `config_key`, `channel_type`, and message details.

### A. Global Listener
```python
@client.slack.on_message
async def on_slack_message(event: InboundMessageEvent):
    print(f"Received from user {event.source.user_id} on bot: {event.config_key}")

    if event.config_key == "ABC-bot":
        # Handle support bot logic
        pass
    elif event.config_key == "XYZ-bot":
        # Handle billing bot logic
        pass
```

### B. Scoped Listener per Bot (Direct Binding)
Filter incoming SSE events by `config_key` before calling the handler:
```python
# Listens ONLY to messages sent to ABC-bot
@client.slack.bot("ABC-bot").on_message
async def on_support_message(event: InboundMessageEvent):
    print("Support bot received:", event.message.text)

# Listens ONLY to messages sent to XYZ-bot
@client.slack.bot("XYZ-bot").on_message
async def on_billing_message(event: InboundMessageEvent):
    print("Billing bot received:", event.message.text)
```

### C. Contextual Auto-Reply
The event object knows which bot and channel received the message and automatically replies:
```python
@client.slack.on_message
async def on_slack_message(event: InboundMessageEvent):
    # Automatically uses ABC-bot if event came to ABC-bot, or XYZ-bot if it came to XYZ-bot
    await event.reply(message="Thanks! Looking into this now.")
```

---

## Complete Example

```python
import asyncio
from claros_sdk import ClarOSClient, InboundMessageEvent

async def main():
    client = ClarOSClient(
        base_url="https://api.claros.ai",
        client_id="your-client-id",
        client_secret="your-client-secret",
    )

    # 1. Send transactional email
    await client.email.send(
        recipient_email="user@example.com",
        template_name="welcome-email",
        recipient_name="Jane Doe",
        subject="Welcome to ClarOS!",
        template_data={"Name": "Jane"},
    )

    # 2. Setup scoped Slack bot and auto-reply
    support_bot = client.slack.bot("ABC-bot")

    @support_bot.on_message
    async def handle_support(event: InboundMessageEvent):
        print(f"New support ticket from {event.source.user_id}: {event.message.text}")
        await event.reply(message="Support ticket received! An agent will assist you shortly.")

    # 3. Start listening to inbound SSE stream
    await client.listen()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 3. FastAPI Route Protection with `ClarOSGuard`

```python
from fastapi import FastAPI, Depends
from claros_sdk import ClarOSGuard, ClarOSAuthContext, ClarOSClient

app = FastAPI()

client = ClarOSClient(base_url="http://localhost:8080")
guard = ClarOSGuard(client)

@app.get("/api/v1/protected")
async def protected_endpoint(auth: ClarOSAuthContext = Depends(guard)):
    return {
        "user_id": auth.user_id,
        "tenant_id": auth.tenant_id,
        "role": auth.role,
        "permissions": auth.permissions,
        "license_tier": auth.license_tier,
    }
```
