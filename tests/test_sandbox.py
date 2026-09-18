from __future__ import annotations

import httpx
import pytest

from claros_sdk import ClarOSClient
from claros_sdk.exceptions import ClarOSSandboxError
from claros_sdk.sandbox.models import ExecuteResponse


@pytest.mark.asyncio
async def test_sandbox_execute_sync_success():
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        assert request.url.path == "/api/v1/sandbox/execute"
        assert request.method == "POST"
        assert request.headers.get("X-Tenant-ID") == "tenant-abc"
        assert request.headers.get("X-Workspace-ID") == "ws-123"
        assert request.headers.get("X-User-ID") == "user-456"

        return httpx.Response(
            200,
            json={
                "message": "Execution finished",
                "success": True,
                "payload": {
                    "execution_id": "exec-001",
                    "status": "completed",
                    "stdout": "Hello world\n",
                    "stderr": "",
                    "exit_code": 0,
                    "duration_ms": 120,
                },
            },
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(
        base_url="https://api.claros.ai",
        httpx_client=httpx_client,
        tenant_id="tenant-abc",
        workspace_id="ws-123",
        user_id="user-456",
    ) as client:
        res = await client.sandbox.execute(
            code="print('Hello world')",
            language="python",
        )

        assert isinstance(res, ExecuteResponse)
        assert res.execution_id == "exec-001"
        assert res.status == "completed"
        assert res.stdout == "Hello world\n"
        assert res.exit_code == 0
        assert res.duration_ms == 120
        assert res.is_success is True
        assert len(captured_requests) == 1


@pytest.mark.asyncio
async def test_sandbox_execute_tenant_override():
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        assert request.headers.get("X-Tenant-ID") == "tenant-custom"
        assert request.headers.get("X-Workspace-ID") == "ws-custom"
        return httpx.Response(
            200,
            json={
                "message": "OK",
                "success": True,
                "payload": {
                    "execution_id": "exec-002",
                    "status": "completed",
                    "stdout": "custom tenant ok",
                    "stderr": "",
                    "exit_code": 0,
                    "duration_ms": 50,
                },
            },
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(
        base_url="https://api.claros.ai",
        httpx_client=httpx_client,
        tenant_id="tenant-original",
    ) as client:
        res = await client.sandbox.execute(
            code="echo custom",
            language="bash",
            tenant_id="tenant-custom",
            workspace_id="ws-custom",
        )

        assert res.is_success is True
        assert captured_requests[0].headers.get("X-Tenant-ID") == "tenant-custom"


@pytest.mark.asyncio
async def test_sandbox_execute_nonzero_exit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": "Command exited with error",
                "success": True,
                "payload": {
                    "execution_id": "exec-003",
                    "status": "failed",
                    "stdout": "",
                    "stderr": "SyntaxError: invalid syntax",
                    "exit_code": 1,
                    "duration_ms": 40,
                },
            },
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="https://api.claros.ai", httpx_client=httpx_client) as client:
        res = await client.sandbox.execute(code="syntax error!!", language="python")
        assert res.is_success is False
        assert res.status == "failed"
        assert res.exit_code == 1
        assert "SyntaxError" in res.stderr


@pytest.mark.asyncio
async def test_sandbox_execute_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"message": "Invalid execution request", "success": False},
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="https://api.claros.ai", httpx_client=httpx_client) as client:
        with pytest.raises(ClarOSSandboxError) as exc_info:
            await client.sandbox.execute(code="something", language="python")
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_sandbox_stateful_session_and_cleanup():
    deleted_sessions: list[str] = []
    executed_sessions: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/sandbox/execute":
            import json
            body = json.loads(request.content)
            session_id = body.get("session_id")
            executed_sessions.append(session_id)
            return httpx.Response(
                200,
                json={
                    "message": "OK",
                    "success": True,
                    "payload": {
                        "execution_id": "exec-session-1",
                        "status": "completed",
                        "stdout": "step done",
                        "exit_code": 0,
                    },
                },
            )
        elif request.method == "DELETE" and request.url.path.startswith("/api/v1/sandbox/sessions/"):
            session_id = request.url.path.split("/")[-1]
            deleted_sessions.append(session_id)
            return httpx.Response(
                200,
                json={"message": "Session purged", "success": True, "payload": "OK"},
            )
        return httpx.Response(404)

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="https://api.claros.ai", httpx_client=httpx_client) as client:
        # Context managed session
        async with client.sandbox.session("test-sess-100") as session:
            assert session.session_id == "test-sess-100"
            res1 = await session.execute("x = 10")
            assert res1.stdout == "step done"
            res2 = await session.execute("print(x)")
            assert res2.stdout == "step done"

        # Verified both executions used the same session ID
        assert executed_sessions == ["test-sess-100", "test-sess-100"]
        # Verified context manager deleted the session on exit
        assert deleted_sessions == ["test-sess-100"]

        # Further calls on closed session raise error
        with pytest.raises(Exception):
            await session.execute("print(x)")
