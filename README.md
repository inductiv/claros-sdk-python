# ClarOS Python SDK

[![Release](https://github.com/inductiv/claros-sdk-python/actions/workflows/release.yml/badge.svg)](https://github.com/inductiv/claros-sdk-python/actions/workflows/release.yml)
[![Latest Tag](https://img.shields.io/github/v/tag/inductiv/claros-sdk-python?sort=semver&label=latest%20tag)](https://github.com/inductiv/claros-sdk-python/tags)
[![GitHub Release](https://img.shields.io/github/v/release/inductiv/claros-sdk-python?sort=semver&label=release)](https://github.com/inductiv/claros-sdk-python/releases)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

Python SDK for machine-to-machine (M2M) communication, user authentication, tenant authorization, user-tenant resolution, and inbound real-time event streaming via the ClarOS platform services.

---

## Features

- **FastAPI Route Protection (`ClarOSGuard`)**: Single-line FastAPI dependency for authenticating user tokens and resolving tenant authorization context statelessly.
- **Single-Call Authentication (`authenticate`)**: Authenticates user tokens and resolves tenant context (`user_id`, `tenant_id`, `role`, `permissions`, `license_tier`) in a single unified API method.
- **User & Tenant Resolution (`resolve_user_tenant`)**: Query and retrieve user profile and all associated tenants by email address (`GET /api/v1/platform/users/email`).
- **Automatic OAuth2 M2M Authentication**: Obtains and caches access tokens using the `client_credentials` grant flow (`POST /api/v1/auth/oauth/token`). Supports both standard and wrapped JSON token payloads.
- **Modular Communication Channels**: Send messages and notifications through channel-specific adapters (`client.slack.send()`, `client.email.send()`, `client.discord.send()`) with scoped bot routing (`client.slack.bot()`).
- **Inbound Real-time Event Streaming (SSE)**: Maintain real-time inbound connection to `/api/v1/comm/inbound/stream` with auto-reconnection, event deduplication, and contextual auto-reply (`event.reply()`).
- **Third-Party Connectors (`client.connectors`)**: Fetch credentials and instantiate official third-party SDK clients (Google, Stripe) with in-memory token caching, automatic expiration tracking, and optional dependency extras.
- **AI Agent Sandbox Code Execution (`client.sandbox`)**: Isolated code execution in Python, Bash, and Shell. Supports synchronous execution, asynchronous runs with real-time SSE streaming, stateful multi-step sessions, and standard AI agent tool schemas.
- **Async API**: Built on `httpx.AsyncClient` for high-performance non-blocking I/O.

---

## Installation

### Via `uv add`

```bash
# Specific release tag (recommended)
uv add "git+https://github.com/inductiv/claros-sdk-python.git@vX.Y.Z"

# With all connectors (Google, Stripe, etc.)
uv add "claros-sdk[all] @ git+https://github.com/inductiv/claros-sdk-python.git@vX.Y.Z"

# Individual connector extras:
# uv add "claros-sdk[google] @ git+https://github.com/inductiv/claros-sdk-python.git@vX.Y.Z"
# uv add "claros-sdk[stripe] @ git+https://github.com/inductiv/claros-sdk-python.git@vX.Y.Z"
# uv add "claros-sdk[clickhouse] @ git+https://github.com/inductiv/claros-sdk-python.git@vX.Y.Z"

# Private repo via SSH
uv add "git+ssh://git@github.com/inductiv/claros-sdk-python.git@vX.Y.Z"

# Or latest from main branch
uv add "claros-sdk[all] @ git+https://github.com/inductiv/claros-sdk-python.git"
```

### In `pyproject.toml`

Pinning a release tag using `uv`:

```toml
[project]
dependencies = [
    "claros-sdk[all]>=X.Y.Z",
]

[tool.uv.sources]
claros-sdk = { git = "https://github.com/inductiv/claros-sdk-python.git", tag = "vX.Y.Z" }
```

Replace `X.Y.Z` with [![Latest Tag](https://img.shields.io/github/v/tag/inductiv/claros-sdk-python?sort=semver&label=latest%20tag)](https://github.com/inductiv/claros-sdk-python/tags)

Then synchronize dependencies:

```bash
uv sync
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

### 3. User & Tenant Resolution (`resolve_user_tenant`)

Lookup user details and all associated tenants by user email:

```python
client = ClarOSClient(
    base_url="https://claros-api.inductiv.dev",
    client_id="sa_client_123",
    client_secret="secret_xyz",
)

user_tenant = await client.resolve_user_tenant("finn@user.com")

print(f"User: {user_tenant.payload.first_name} {user_tenant.payload.last_name}")
print(f"Email: {user_tenant.payload.email}")

for tenant in user_tenant.payload.tenants:
    print(f"Tenant: {tenant.name} ({tenant.slug}) - ID: {tenant.id}")
    print(f"Attributes: {tenant.attributes}")
```

---

### 4. Machine-to-Machine (M2M) & Outbound Communication

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

### 5. Inbound Real-time Event Streaming (SSE)

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

### 6. Third-Party Connectors (`google`, `stripe`, `clickhouse`)

Use `client.connectors` to dynamically resolve connection credentials from ClarOS and build official third-party SDK client instances automatically:

```python
from claros_sdk import ClarOSClient

client = ClarOSClient(
    base_url="http://localhost:8080",
    client_id="sa_client_123",
    client_secret="secret_xyz",
)

# 1. Google Connector (requires 'google-api-python-client' and 'google-auth')
# uv add "claros-sdk[google]"
sheets = await client.connectors.google("sheets")
# Returns official googleapiclient Resource with OAuth2 Bearer token applied:
result = sheets.spreadsheets().values().get(
    spreadsheetId="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    range="Sheet1!A1:C10",
).execute()
print("Google Sheets rows:", result.get("values", []))

# Access other Google services
drive = await client.connectors.google("my_drive_conn", service="drive")
results = drive.files().list().execute()
files = results.get('files', [])

print('Here are your top 10 files:')
for file in files:
    print(f"Name: {file['name']} | ID: {file['id']} | Type: {file['mimeType']}")

# 2. Stripe Connector (requires 'stripe')
# uv add "claros-sdk[stripe]"
stripe_client = await client.connectors.stripe("stripe")
# Returns official stripe.StripeClient instance with ApiKey applied:
customers = stripe_client.customers.list(limit=5)
for customer in customers.data:
    print(customer.id, customer.email)

# 3. ClickHouse Connector (requires 'clickhouse-connect')
# uv add "claros-sdk[clickhouse]"
ch_client = await client.connectors.clickhouse("clickhouse")
# Returns official clickhouse_connect client instance with credentials applied:
query_res = ch_client.query("SELECT 1")
print(query_res.result_rows)
```

---

### 7. AI Agent Sandbox Code Execution (`client.sandbox`)

Safely run isolated code blocks (Python, Bash, Shell) with automatic tenant context resolution, real-time output streaming, stateful sessions, and agent tool bindings:

```python
from claros_sdk import ClarOSClient

async with ClarOSClient(base_url="https://api.claros.ai", tenant_id="tenant-123") as client:
    # 1. Synchronous Execution
    res = await client.sandbox.execute(
        code="print('Hello from ClarOS sandbox!')",
        language="python",
    )
    print(f"Stdout: {res.stdout.strip()} (Exit code: {res.exit_code})")

    # 2. Asynchronous Execution with Real-Time SSE Streaming
    res = await client.sandbox.run(
        code="for i in {1..3}; do echo step $i; sleep 1; done",
        language="bash",
        on_chunk=lambda stream, chunk: print(f"[{stream.upper()}] {chunk}", end=""),
    )

    # 3. Stateful Multi-Step Sessions
    async with client.sandbox.session() as session:
        await session.execute("x = 42")
        calc = await session.execute("print(x * 2)")
        print(f"Result: {calc.stdout.strip()}")  # 84

    # 4. Export OpenAI / Anthropic Tool Schemas
    tools = client.sandbox.get_tools()
    openai_schemas = [t.to_openai_tool() for t in tools]
```

#### Integrating with AI Agent Frameworks (e.g. Agent Fabric)

The sandbox tools conform to agent function calling standards that take a Pydantic `BaseModel` args schema and an async handler.

##### Option A: Bulk Registration from Tool Registry

```python
from agent_fabric import ToolKind, ToolRegistry, tool
from claros_sdk import ClarOSClient

client = ClarOSClient(base_url="https://api.claros.ai", tenant_id="tenant-123")
tools = client.sandbox.get_tools()

registry = ToolRegistry.from_specs([
    tool(
        t.name,
        ToolKind.ACTION,
        t.function,     # Async handler supporting (ctx, args) or (args)
        t.args_schema,  # Pydantic BaseModel class
        description=t.description,
    )
    for t in tools
])
```

##### Option B: Explicit Tool Registration

```python
from agent_fabric import ToolKind, ToolRegistry, tool
from claros_sdk import ClarOSClient
from claros_sdk.sandbox import (
    ExecuteCodeArgs,
    ExecuteCodeAsyncArgs,
    GetExecutionStatusArgs,
    TerminateSessionArgs,
)

client = ClarOSClient(base_url="https://api.claros.ai", tenant_id="tenant-123")
tools = {t.name: t for t in client.sandbox.get_tools()}

registry = ToolRegistry.from_specs([
    tool(
        "execute_code",
        ToolKind.ACTION,
        tools["execute_code"].function,
        ExecuteCodeArgs,
        description="Execute code (Python, Bash, Shell) in an isolated sandbox with tenant scoping.",
    ),
    tool(
        "execute_code_async",
        ToolKind.ACTION,
        tools["execute_code_async"].function,
        ExecuteCodeAsyncArgs,
        description="Enqueue background code execution and receive execution_id for output streaming.",
    ),
    tool(
        "get_execution_status",
        ToolKind.QUERY,
        tools["get_execution_status"].function,
        GetExecutionStatusArgs,
        description="Fetch status and output buffer of an asynchronous execution.",
    ),
    tool(
        "terminate_session",
        ToolKind.ACTION,
        tools["terminate_session"].function,
        TerminateSessionArgs,
        description="Terminate a stateful sandbox session and release its resources.",
    ),
])
```

##### Invocation Calling Conventions

Every tool handler (`tool.function`) automatically unpacks input parameters across standard calling conventions without manual conversion:

1. **Agent Fabric style (`takes_ctx=True`)**: `await tool.function(ctx, args)`
2. **Direct Pydantic style (`takes_ctx=False`)**: `await tool.function(args)`
3. **Keyword style**: `await tool.function(code="print(1)", language="python")`

Tenant headers (`X-Tenant-ID`, `X-Workspace-ID`, `X-User-ID`, `Authorization`) are automatically injected from the `ClarOSClient` instance.

---

## API Reference

### Client Class

#### `ClarOSClient(base_url="https://api.claros.ai", client_id=None, client_secret=None, timeout=10.0, httpx_client=None)`

- **Parameters:**
  - `base_url` (`str`): Base URL of the ClarOS service.
  - `client_id` (`str | None`, optional): OAuth2 M2M Client ID. _Required only for M2M operations or calling `get_token()`._
  - `client_secret` (`str | None`, optional): OAuth2 M2M Client Secret. _Required only for M2M operations or calling `get_token()`._
  - `timeout` (`float`, default `10.0`): HTTP request timeout in seconds.
  - `httpx_client` (`httpx.AsyncClient | None`, optional): Custom async HTTP client.

#### Third-Party Connectors:

- **`client.connectors` (`ConnectorsManager`)**:
  - `google(key, service=None, version=None, force_refresh=False, **kwargs)` -> Official `googleapiclient` Resource with credentials applied.
  - `stripe(key, force_refresh=False, **kwargs)` -> Official `stripe.StripeClient` with ApiKey applied.
  - `get_token(key, force_refresh=False)` -> `ConnectorTokenData` (cached in-memory, auto-refreshed when expired).
  - `clear_cache(key=None)` -> Clears in-memory token cache.

#### User & Tenant Methods:

- **`resolve_user_tenant(email)`** -> `UserTenantResponse`  
  Fetches user details and associated tenant list by email address (`GET /api/v1/platform/users/email`).
- **`authenticate(token, tenant_id=None, workspace_id=None)`** -> `ClarOSAuthContext`  
  Verifies token validity and resolves tenant authorization context in a single call.
- **`verify_token(token)`** -> `TokenVerifyResponse`  
  Verifies access token authenticity and extracts `user_id`.
- **`resolve_tenant_auth_context(token, user_id, tenant_id=None, workspace_id=None)`** -> `TenantAuthContextResponse`  
  Resolves tenant permissions, role, and context headers.
- **`get_token(force_refresh=False)`** -> `str`  
  Fetches or returns cached M2M OAuth2 access token. _(Requires `client_id` and `client_secret`)_

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

#### AI Agent Sandbox Execution:

- **`client.sandbox` (`SandboxManager`)**:
  - `execute(code, language="python", session_id=None, timeout_seconds=None, network_enabled=None, env=None, ...)` -> `ExecuteResponse` (synchronous execution).
  - `execute_async(code, language="python", ...)` -> `AsyncExecuteResponse` (enqueue background execution).
  - `get_execution(execution_id)` -> `ExecuteResponse` (poll status and output buffer).
  - `stream(execution_id)` -> `AsyncIterator[StreamEvent]` (stream SSE output chunks in real time).
  - `run(code, language="python", on_chunk=None, ...)` -> `ExecuteResponse` (convenience runner: dispatches async, streams SSE chunks, and returns completed response).
  - `session(session_id=None)` -> `SandboxSession` (stateful interactive sandbox session with `async with` context manager).
  - `terminate_session(session_id)` -> `bool` (purge stateful session container resources).
  - `get_tools()` -> `list[AgentTool]` (return AI agent tools with JSON Schemas and execution handlers).

#### Inbound SSE Streaming:

- **`listen()`**: Connects and continuously streams inbound SSE events.
- **`start_stream()`**: Connects to the inbound SSE event stream in a background task.
- **`stop_stream()`**: Gracefully stops the active SSE connection.
- **`dispatcher` (`EventEmitter`)**: Custom event dispatcher (`on`, `off`, `emit`).

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
- **`ExecuteRequest`**:
  - `code`: `str`, `language`: `Literal["python", "bash", "sh"]`, `session_id`: `str | None`, `timeout_seconds`: `int | None`, `network_enabled`: `bool | None`, `env`: `dict[str, str] | None`
- **`ExecuteResponse`**:
  - `execution_id`: `str | None`, `status`: `str`, `stdout`: `str`, `stderr`: `str`, `exit_code`: `int`, `duration_ms`: `int`, `is_success`: `bool`
- **`AsyncExecuteResponse`**:
  - `execution_id`: `str`, `message`: `str`, `status`: `str`
- **`StreamEvent`**:
  - `event`: `str`, `data`: `str`, `id`: `str | None`, `stream`: `Literal["stdout", "stderr", "system"] | None`
- **`AgentTool`**:
  - `name`: `str`, `description`: `str`, `parameters`: `dict[str, Any]`, `handler`: callable, `to_openai_tool()`: convert to OpenAI schema format
- **`UserTenantResponse`**:
  - `success`: `bool`
  - `message`: `str`
  - `payload`: `UserTenantPayload` (`id`, `external_id`, `email`, `username`, `first_name`, `last_name`, `status`, `attributes`, `tenants`)
- **`TenantDetail`**:
  - `id`: `str`
  - `name`: `str`
  - `slug`: `str`
  - `status`: `str`
  - `is_system`: `bool`
  - `attributes`: `Any` (Arbitrary type metadata/dict)
  - `parent_tenant_id`: `str | None`
  - `instance_id`: `str | None`
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
- **`ClarOSSandboxError`**: Raised on sandbox execution or session failures.
- **`ClarOSSandboxTimeoutError`**: Raised when a sandbox execution exceeds its timeout.
