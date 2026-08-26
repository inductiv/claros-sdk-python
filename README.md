# ClarOS Python SDK

Python SDK for machine-to-machine (M2M) communication, scoped bot routing, inbound Server-Sent Events (SSE) streaming, user authentication, and tenant authorization via the ClarOS platform services.

---

## 1. Outbound (Sending Messages from Client)

When sending messages, you can pass `message` and optional `title`, `channel`, and `config_key`.

### A. Fallback to Default (Default Webhook)

If no bot or channel is specified:

```python
await client.slack.send(
    title="Alert",
    message="🚨 Deployment completed",
)
```

### B. Explicitly Selecting a Bot

#### Option 1: Inline Parameter

```python
# Sends as ABC-bot
await client.slack.send(
    config_key="ABC-bot",
    channel="C0123456789",
    title="Support Alert",
    message="Hello from Customer Support Bot!",
)

# Sends as XYZ-bot
await client.slack.send(
    config_key="XYZ-bot",
    channel="C0987654321",
    message="Hello from Financial/Billing Bot!",
)
```

#### Option 2: Scoped Bot Client (Clean SDK Syntax)

```python
support_bot = client.slack.bot("ABC-bot")
billing_bot = client.slack.bot("XYZ-bot")

await support_bot.send(channel="C123", message="Support ticket opened")
await billing_bot.send(channel="C456", title="Invoice", message="Invoice generated")
```

---

## 2. Inbound (Receiving Messages from Slack/Discord)

### A. Global Listener

```python
@client.slack.on_message
async def on_slack_message(event: InboundMessageEvent):
    print(f"Received on bot: {event.config_key}")

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

    support_bot = client.slack.bot("ABC-bot")

    @support_bot.on_message
    async def handle_support(event: InboundMessageEvent):
        print(f"New support ticket from {event.source.user_id}: {event.message.text}")
        await event.reply(message="Support ticket received! An agent will assist you shortly.")

    # Start listening to inbound SSE stream
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
