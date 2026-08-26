# ClarOS Python SDK

Python SDK for machine-to-machine (M2M) communication, user authentication, tenant authorization, and inbound real-time event streaming via the ClarOS platform services.

---

## Features

- **FastAPI Route Protection (`ClarOSGuard`)**: Single-line FastAPI dependency for authenticating user tokens and resolving tenant authorization context statelessly.
- **Single-Call Authentication (`authenticate`)**: Authenticates user tokens and resolves tenant context (`user_id`, `tenant_id`, `role`, `permissions`, `license_tier`) in a single unified API method.
- **Automatic OAuth2 M2M Authentication**: Obtains and caches access tokens using the `client_credentials` grant flow (`POST /api/v1/auth/oauth/token`). Supports both standard and wrapped JSON token payloads.
- **Modular Communication Channels**: Send messages and notifications through channel-specific adapters (`client.slack.send()`, `client.email.send()`, `client.discord.send()`) with scoped bot routing (`client.slack.bot()`).
- **Inbound Real-time Event Streaming (SSE)**: Maintain real-time inbound connection to `/api/v1/comm/inbound/stream` with auto-reconnection, event deduplication, and contextual auto-reply (`event.reply()`).
- **Async API**: Built on `httpx.AsyncClient` for high-performance non-blocking I/O.

---

## Installation

```bash
uv add "claros-sdk @ git+https://github.com/inductiv/claros-sdk-python.git"
```

---

## Quick Start

### 1. FastAPI Route Protection with `ClarOSGuard`

Use `ClarOSGuard` to protect FastAPI endpoints with a single line of dependency injection (no M2M credentials required for guard/user auth):

```python
from fastapi import FastAPI, Depends
from claros_sdk import ClarOSGuard, ClarOSAuthContext, ClarOSClient

app = FastAPI()

# M2M credentials (client_id/client_secret) are not required when using ClarOSGuard
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

---

### 2. User Authentication & Authorization (`authenticate`)

Authenticate a user token and resolve tenant context programmatically:

```python
from claros_sdk import ClarOSClient

# client_id and client_secret are optional when verifying user tokens
client = ClarOSClient(base_url="http://localhost:8080")

# Single method call to verify token and resolve tenant context
auth_context = await client.authenticate(
    token="user.jwt.token",
    tenant_id="optional-tenant-uuid",
    workspace_id="optional-workspace-uuid",
)

print(f"User: {auth_context.user_id}")
print(f"Tenant: {auth_context.tenant_id} ({auth_context.tenant_slug})")
print(f"Role: {auth_context.role}")
print(f"Permissions: {auth_context.permissions}")
print(f"Headers Map: {auth_context.headers}")
```

---

### 3. Machine-to-Machine (M2M) & Communication

`client_id` and `client_secret` are **only required** when acquiring M2M OAuth access tokens or using communication APIs:

```python
client = ClarOSClient(
    base_url="http://localhost:8080",
    client_id="sa_client_123",
    client_secret="secret_xyz",
)

# 1. Send transactional email (`template_name` and `recipient_email` are required)
email_res = await client.email.send(
    recipient_email="john.doe@example.com",
    template_name="monthly-kpi-report",
    recipient_name="John Doe",
    subject="Monthly Financial Overview - August 2026",
    template_data={"Greeting": "Hi John,", "MRR": "$124,500"},
)

# 2. Send Slack message (default webhook or channel)
await client.slack.send(
    channel="C0123456789",
    title="Deployment Notice",
    message="Deployment completed successfully.",
)

# 3. Send scoped bot message
support_bot = client.slack.bot("ABC-bot")
await support_bot.send(
    channel="C123456",
    title="Support Ticket",
    message="Ticket #102 opened.",
)
```

---

### 4. Inbound Real-time Event Streaming (SSE)

Receive real-time inbound messages from Slack/Discord over SSE stream (`/api/v1/comm/inbound/stream`):

```python
import asyncio
from claros_sdk import ClarOSClient, InboundMessageEvent

async def main():
    client = ClarOSClient(
        base_url="http://localhost:8080",
        client_id="sa_client_123",
        client_secret="secret_xyz",
    )

    # 1. Global Slack Listener
    @client.slack.on_message
    async def on_slack(event: InboundMessageEvent):
        print(f"Slack message from {event.source.user_id}: {event.message.text}")
        # Contextual auto-reply uses the same bot config_key and channel
        await event.reply(message="Received your message!")

    # 2. Scoped Bot Listener (listens ONLY to ABC-bot events)
    @client.slack.bot("ABC-bot").on_message
    async def on_support(event: InboundMessageEvent):
        print(f"Support bot message: {event.message.text}")

    # 3. Start listening to inbound SSE stream
    await client.listen()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## API Reference

### Client Class

#### `ClarOSClient(base_url="https://api.claros.ai", client_id=None, client_secret=None, timeout=10.0, httpx_client=None)`

- **Parameters:**
  - `base_url` (`str`): Base URL of the ClarOS service.
  - `client_id` (`str | None`, optional): OAuth2 M2M Client ID. *Required only for M2M operations or calling `get_token()`.*
  - `client_secret` (`str | None`, optional): OAuth2 M2M Client Secret. *Required only for M2M operations or calling `get_token()`.*
  - `timeout` (`float`, default `10.0`): HTTP request timeout in seconds.
  - `httpx_client` (`httpx.AsyncClient | None`, optional): Custom async HTTP client.

#### Authentication & Authorization Methods:
- **`authenticate(token, tenant_id=None, workspace_id=None)`** -> `ClarOSAuthContext`  
  Verifies token validity and resolves tenant authorization context in a single call.
- **`verify_token(token)`** -> `TokenVerifyResponse`  
  Verifies access token authenticity and extracts `user_id`.
- **`resolve_tenant_auth_context(token, user_id, tenant_id=None, workspace_id=None)`** -> `TenantAuthContextResponse`  
  Resolves tenant permissions, role, and context headers.
- **`get_token(force_refresh=False)`** -> `str`  
  Fetches or returns cached M2M OAuth2 access token. *(Requires `client_id` and `client_secret`)*

#### Modular Communication Channels:
- **`client.slack` (`SlackChannel`)**:
  - `send(message="", channel=None, title=None, config_key=None, **kwargs)` -> `dict`
  - `bot(config_key)` -> `SlackBot` (scoped bot client)
  - `on_message(handler)` -> Registers a listener for all inbound Slack events
- **`client.email` (`EmailChannel`)**:
  - `send(recipient_email, template_name, recipient_name=None, subject="", template_data=None, **kwargs)` -> `dict`
- **`client.discord` (`DiscordChannel`)**:
  - `send(message="", channel=None, title=None, config_key=None, **kwargs)` -> `dict`
  - `bot(config_key)` -> `DiscordBot` (scoped bot client)
  - `on_message(handler)` -> Registers a listener for all inbound Discord events
- **`client.channel(channel_type)` (`BaseChannel`)**:
  - Dynamically get or instantiate any communication channel adapter.

#### Inbound SSE Streaming:
- **`listen()`**: Connects and continuously streams inbound SSE events.
- **`start_stream()`**: Connects to the inbound SSE event stream in a background task.
- **`stop_stream()`**: Gracefully stops the active SSE connection.
- **`dispatcher` (`EventEmitter`)**: Custom event dispatcher (`on`, `off`, `emit`).

#### Backward-Compatible Aliases:
- **`send_email(...)`** -> Delegates to `client.email.send(...)`
- **`send_slack(...)`** -> Delegates to `client.slack.send(...)`

---

### Models & Dependencies

- **`ClarOSGuard(client_factory)`**:  
  FastAPI dependency callable (`await guard(request)`). Extracts `Authorization: Bearer <token>` or `access_token` cookie along with `X-Tenant-ID` / `X-Workspace-ID` request headers. Sets `request.state.auth_headers` and `request.state.claros_auth_context`.
- **`ClarOSAuthContext`**:
  - `user_id`: `str`
  - `tenant_id`: `str`
  - `tenant_slug`: `str`
  - `role`: `str`
  - `permissions`: `list[str]`
  - `license_tier`: `str`
  - `headers`: `dict[str, str]` (dictionary of `X-*` authorization headers)
- **`InboundMessageEvent`**:
  - `event_id`: `str`
  - `tenant_id`: `str`
  - `config_key`: `str`
  - `channel_type`: `str`
  - `received_at`: `str`
  - `source`: `InboundEventSource` (`workspace_id`, `channel_id`, `user_id`, `message_id`)
  - `message`: `InboundEventMessage` (`text`, `event_type`, `metadata`)
  - `reply(message, title=None, **kwargs)`: Contextual auto-reply using the event's bot and channel.

---

### Exceptions

- **`ClarOSError`**: Base SDK exception.
- **`ClarOSAuthError`**: Raised on token verification failure or unauthorized access.
- **`ClarOSAPIError`**: Raised on remote service API errors (5xx/4xx responses).
