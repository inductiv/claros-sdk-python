# ClarOS Python SDK

Python SDK for machine-to-machine (M2M) communication, user authentication, and tenant authorization via the ClarOS platform services.

---

## Features

- **FastAPI Route Protection (`ClarOSGuard`)**: Single-line FastAPI dependency for authenticating user tokens and resolving tenant authorization context statelessly.
- **Single-Call Authentication (`authenticate`)**: Authenticates user tokens and resolves tenant context (`user_id`, `tenant_id`, `role`, `permissions`, `license_tier`) in a single unified API method.
- **Automatic OAuth2 M2M Authentication**: Obtains and caches access tokens using the `client_credentials` grant flow (`POST /api/v1/auth/oauth/token`). Supports both standard and wrapped JSON token payloads.
- **Email Communication (`send_email`)**: Send templated transactional emails via Go `html/template` / `templ` compatible data dictionaries (`POST /api/v1/comm/email`).
- **Slack Communication (`send_slack`)**: Send formatted notifications and alerts to Slack channels (`POST /api/v1/comm/slack`).
- **Async API**: Built on `httpx.AsyncClient` for high-performance non-blocking I/O.

---

## Installation

```bash
uv add "claros-sdk @ git+https://github.com/inductiv/claros-sdk-python.git
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

### 3. Machine-to-Machine (M2M) & Communication (`send_email`, `send_slack`)

`client_id` and `client_secret` are **only required** when acquiring M2M OAuth access tokens or using M2M APIs (`send_email`, `send_slack`):

```python
client = ClarOSClient(
    base_url="http://localhost:8080",
    client_id="sa_client_123",
    client_secret="secret_xyz",
)

# Send transactional email (automatically fetches M2M token via client_id/client_secret)
response = await client.send_email(
    recipient_email="john.doe@example.com",
    recipient_name="John Doe",
    subject="Monthly Financial Overview - August 2026",
    template_name="monthly-kpi-report",
    template_data={"Greeting": "Hi John,"},
)
```

---

## API Reference

### Client Class

#### `ClarOSClient(base_url, client_id=None, client_secret=None, timeout=10.0, httpx_client=None)`

- **Parameters:**
  - `base_url` (`str`): Base URL of the ClarOS service.
  - `client_id` (`str | None`, optional): OAuth2 M2M Client ID. *Required only for M2M operations or calling `get_token()`.*
  - `client_secret` (`str | None`, optional): OAuth2 M2M Client Secret. *Required only for M2M operations or calling `get_token()`.*
  - `timeout` (`float`, default `10.0`): HTTP request timeout in seconds.
  - `httpx_client` (`httpx.AsyncClient | None`, optional): Custom async HTTP client.

- **`authenticate(token, tenant_id=None, workspace_id=None)`** -> `ClarOSAuthContext`  
  Verifies token validity and resolves tenant authorization context.
- **`verify_token(token)`** -> `TokenVerifyResponse`  
  Verifies access token authenticity and extracts `user_id`.
- **`resolve_tenant_auth_context(token, user_id, tenant_id=None, workspace_id=None)`** -> `TenantAuthContextResponse`  
  Resolves tenant permissions, role, and context headers.
- **`get_token()`** -> `str`  
  Fetches or returns cached M2M OAuth2 access token. *(Requires `client_id` and `client_secret`)*
- **`send_email(...)`** -> `dict`  
  Sends a templated email message. *(Requires `client_id` and `client_secret`)*
- **`send_slack(...)`** -> `dict`  
  Sends a Slack message. *(Requires `client_id` and `client_secret`)*

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

---

### Exceptions

- **`ClarOSError`**: Base SDK exception.
- **`ClarOSAuthError`**: Raised on token verification failure or unauthorized access.
- **`ClarOSAPIError`**: Raised on remote service API errors (5xx/4xx responses).``
