import json

import httpx
import pytest
from claros_sdk import (
    ClarOSClient,
    ClarOSGuard,
    extract_bearer_token,
)


def create_mock_transport():
    call_counts = {"token": 0, "email": 0, "slack": 0, "verify": 0, "context": 0}
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

        # Send email
        res = await client.send_email(
            recipient_email="john@example.com",
            recipient_name="John Doe",
            subject="Test Subject",
            template_name="welcome-email",
            template_data={"Name": "John Doe", "TenantName": "Acme Corp"},
        )
        assert res["status"] == "sent"
        assert call_counts["email"] == 1
        last_req = last_requests["/api/v1/comm/email"]
        assert last_req.headers["Authorization"] == "Bearer mock-test-token-123"


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
