import json

import httpx
import pytest
from claros_sdk import (
    ClarOSClient,
    ClarOSGuard,
    UserTenantResponse,
    extract_bearer_token,
)


def create_mock_transport():
    call_counts = {"token": 0, "email": 0, "slack": 0, "verify": 0, "context": 0, "resolve_user": 0}
    last_requests = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url_path = request.url.path
        last_requests[url_path] = request

        if url_path == "/api/v1/auth/oauth/token":
            call_counts["token"] += 1
            body = json.loads(request.content)
            if body.get("client_id") == "bad_id":
                return httpx.Response(401, text="Unauthorized client credentials")
            return httpx.Response(
                200,
                json={"access_token": "mock-test-token-123", "expires_in": 3600, "token_type": "Bearer"},
            )
        elif url_path == "/api/v1/comm/email":
            call_counts["email"] += 1
            return httpx.Response(200, json={"status": "sent", "message_id": "msg-999"})
        elif url_path == "/api/v1/comm/slack":
            call_counts["slack"] += 1
            return httpx.Response(200, json={"status": "delivered"})
        elif url_path == "/api/v1/platform/users/email":
            call_counts["resolve_user"] += 1
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "message": "User fetched successfully",
                    "payload": {
                        "id": "8d98e87d-f2af-47b3-9d7f-b78bd52b2755",
                        "external_id": "70ada5b9-8427-4cfe-833b-f7ae173db292",
                        "email": "finn@user.com",
                        "username": "finn@user.com",
                        "first_name": "Finn",
                        "last_name": "User",
                        "attributes": {"role_title": "Engineer"},
                        "status": "active",
                        "tenants": [
                            {
                                "id": "73895137-17f6-45c3-8d87-b1766ed26506",
                                "name": "Greensprout Pte. Ltd.",
                                "slug": "greensprout",
                                "status": "active",
                                "created_at": "2026-08-14T16:07:37.359597Z",
                                "updated_at": "2026-08-14T16:07:37.359597Z",
                                "is_system": False,
                                "attributes": {
                                    "tagline": "Get Healthy",
                                    "ai_agent": {
                                        "id": "b474ccab-67b4-4284-9a25-090a4bdb1669",
                                        "key": "finn_agent",
                                    },
                                },
                                "parent_tenant_id": "9d3acd79-3b94-44f5-9c0a-500fa8c43b58",
                                "instance_id": None,
                            }
                        ],
                        "created_at": "2026-08-14T16:12:03.220771Z",
                        "updated_at": "2026-08-27T05:34:48.149199Z",
                    },
                },
            )
        elif url_path == "/api/v1/auth/verify":
            call_counts["verify"] += 1
            auth_header = request.headers.get("Authorization", "")
            if "invalid" in auth_header:
                return httpx.Response(401, json={"success": False, "message": "Invalid token"})
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "message": "Token verified",
                    "payload": {
                        "valid": True,
                        "user_id": "user-uuid-1234",
                        "session_id": "sess-5678",
                        "headers": {"X-User-ID": "user-uuid-1234"},
                    },
                },
            )
        elif url_path == "/api/v1/platform/authorize/context":
            call_counts["context"] += 1
            user_id = request.headers.get("X-User-ID")
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "message": "Context authorized",
                    "payload": {
                        "allowed": True,
                        "user_id": user_id or "user-uuid-1234",
                        "tenant_id": "tenant-uuid-9999",
                        "tenant_slug": "acme-corp",
                        "role": "admin",
                        "permissions": ["read", "write"],
                        "license_tier": "enterprise",
                        "headers": {"X-Tenant-ID": "tenant-uuid-9999"},
                    },
                },
            )

        return httpx.Response(404, json={"error": "Not Found"})

    return httpx.MockTransport(handler), call_counts, last_requests


@pytest.mark.asyncio
async def test_claros_client_token_and_email():
    transport, call_counts, last_requests = create_mock_transport()
    httpx_client = httpx.AsyncClient(transport=transport)

    async with ClarOSClient(
        base_url="http://localhost:8080",
        client_id="sa_9d7c461b",
        client_secret="secret_test",
        httpx_client=httpx_client,
    ) as client:
        token = await client.get_token()
        assert token == "mock-test-token-123"
        assert client.is_token_valid is True
        assert call_counts["token"] == 1

        # Second call to get_token should use cached token
        cached_token = await client.get_token()
        assert cached_token == "mock-test-token-123"
        assert call_counts["token"] == 1

        # Send email via client.email.send
        res = await client.email.send(
            recipient_email="john@example.com",
            template_name="welcome-email",
            recipient_name="John Doe",
            subject="Test Subject",
            template_data={"Name": "John Doe", "TenantName": "Acme Corp"},
        )
        assert res["status"] == "sent"
        assert call_counts["email"] == 1
        last_req = last_requests["/api/v1/comm/email"]
        assert last_req.headers["Authorization"] == "Bearer mock-test-token-123"


@pytest.mark.asyncio
async def test_resolve_user_tenant():
    transport, call_counts, last_requests = create_mock_transport()
    httpx_client = httpx.AsyncClient(transport=transport)

    async with ClarOSClient(
        base_url="https://claros-api.inductiv.dev",
        client_id="sa_9d7c461b",
        client_secret="secret_test",
        httpx_client=httpx_client,
    ) as client:
        res = await client.resolve_user_tenant("finn@user.com")
        assert isinstance(res, UserTenantResponse)
        assert res.success is True
        assert res.message == "User fetched successfully"
        assert res.payload.email == "finn@user.com"
        assert res.payload.first_name == "Finn"
        assert res.payload.attributes == {"role_title": "Engineer"}
        assert len(res.payload.tenants) == 1

        tenant = res.payload.tenants[0]
        assert tenant.name == "Greensprout Pte. Ltd."
        assert tenant.slug == "greensprout"
        assert tenant.attributes["tagline"] == "Get Healthy"
        assert tenant.attributes["ai_agent"]["key"] == "finn_agent"

        last_req = last_requests["/api/v1/platform/users/email"]
        assert last_req.headers["Authorization"] == "Bearer mock-test-token-123"
        assert last_req.url.params["email"] == "finn@user.com"


@pytest.mark.asyncio
async def test_claros_client_wrapped_payload_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "message": "Token issued successfully",
                "payload": {
                    "access_token": "wrapped-jwt-token-789",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "m2m:read m2m:write",
                },
            },
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(
        base_url="http://localhost:8080",
        client_id="sa_9d7c461b",
        client_secret="secret_test",
        httpx_client=httpx_client,
    ) as client:
        token = await client.get_token()
        assert token == "wrapped-jwt-token-789"


@pytest.mark.asyncio
async def test_claros_client_authenticate():
    transport, call_counts, _ = create_mock_transport()
    httpx_client = httpx.AsyncClient(transport=transport)

    async with ClarOSClient(
        base_url="http://localhost:8080",
        client_id="sa_9d7c461b",
        client_secret="secret_test",
        httpx_client=httpx_client,
    ) as client:
        auth_ctx = await client.authenticate("Bearer valid-jwt-token-123")
        assert auth_ctx.user_id == "user-uuid-1234"
        assert auth_ctx.tenant_id == "tenant-uuid-9999"
        assert auth_ctx.role == "admin"
        assert call_counts["verify"] == 1
        assert call_counts["context"] == 1


@pytest.mark.asyncio
async def test_claros_guard_middleware_dependency():
    transport, _, _ = create_mock_transport()
    httpx_client = httpx.AsyncClient(transport=transport)

    client = ClarOSClient(
        base_url="http://localhost:8080",
        client_id="sa_9d7c461b",
        client_secret="secret_test",
        httpx_client=httpx_client,
    )

    guard = ClarOSGuard(client)

    class DummyState:
        pass

    class DummyRequest:
        def __init__(self):
            self.headers = {"Authorization": "Bearer token-abc", "X-Tenant-ID": "tenant-uuid-9999"}
            self.cookies = {}
            self.state = DummyState()

    req = DummyRequest()
    auth_ctx = await guard(req)

    assert auth_ctx.user_id == "user-uuid-1234"
    assert auth_ctx.tenant_id == "tenant-uuid-9999"
    assert req.state.auth_headers == {"X-Tenant-ID": "tenant-uuid-9999"}
    assert req.state.claros_auth_context == auth_ctx
    await client.close()


def test_extract_bearer_token():
    assert extract_bearer_token({"Authorization": "Bearer token123"}) == "token123"
    assert extract_bearer_token({"authorization": "Bearer token456"}) == "token456"
    assert extract_bearer_token({}, {"access_token": "cookie789"}) == "cookie789"
    assert extract_bearer_token({}) is None


@pytest.mark.asyncio
async def test_claros_client_without_m2m_credentials():
    from claros_sdk.exceptions import ClarOSAuthError

    transport, _, _ = create_mock_transport()
    httpx_client = httpx.AsyncClient(transport=transport)

    # Initialize client without client_id or client_secret
    client = ClarOSClient(
        base_url="http://localhost:8080",
        httpx_client=httpx_client,
    )

    # ClarOSGuard should work fine without M2M credentials
    guard = ClarOSGuard(client)

    class DummyState:
        pass

    class DummyRequest:
        def __init__(self):
            self.headers = {"Authorization": "Bearer token-abc"}
            self.cookies = {}
            self.state = DummyState()

    auth_ctx = await guard(DummyRequest())
    assert auth_ctx.user_id == "user-uuid-1234"

    # Attempting to fetch M2M token without credentials should raise ClarOSAuthError
    with pytest.raises(ClarOSAuthError, match="client_id and client_secret are required"):
        await client.get_token()

    await client.close()
