from __future__ import annotations

import httpx
import pytest

from claros_sdk import ClarOSClient
from claros_sdk.sandbox.models import AsyncExecuteResponse, ExecuteResponse, StreamEvent


@pytest.mark.asyncio
async def test_sandbox_execute_async_and_get():
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        if request.url.path == "/api/v1/sandbox/async" and request.method == "POST":
            return httpx.Response(
                202,
                json={
                    "message": "Execution accepted",
                    "success": True,
                    "payload": {"execution_id": "exec-async-123"},
                },
            )
        elif (
            request.url.path == "/api/v1/sandbox/exec-async-123"
            and request.method == "GET"
        ):
            return httpx.Response(
                200,
                json={
                    "message": "Execution status fetched",
                    "success": True,
                    "payload": {
                        "execution_id": "exec-async-123",
                        "status": "completed",
                        "stdout": "async result",
                        "stderr": "",
                        "exit_code": 0,
                        "duration_ms": 350,
                    },
                },
            )
        return httpx.Response(404)

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="https://api.claros.ai", httpx_client=httpx_client) as client:
        # Enqueue async job
        async_res = await client.sandbox.execute_async(
            code="print('async test')",
            language="python",
        )
        assert isinstance(async_res, AsyncExecuteResponse)
        assert async_res.execution_id == "exec-async-123"

        # Fetch status
        status_res = await client.sandbox.get_execution("exec-async-123")
        assert isinstance(status_res, ExecuteResponse)
        assert status_res.execution_id == "exec-async-123"
        assert status_res.stdout == "async result"
        assert status_res.exit_code == 0


@pytest.mark.asyncio
async def test_sandbox_stream_sse():
    sse_body = (
        b"event: message\n"
        b"data: chunk 1\n\n"
        b"event: stderr\n"
        b"data: warning message\n\n"
        b"event: message\n"
        b"data: chunk 2\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/sandbox/exec-stream-1/stream"
        assert request.headers.get("Accept") == "text/event-stream"
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=sse_body,
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="https://api.claros.ai", httpx_client=httpx_client) as client:
        events: list[StreamEvent] = []
        async for event in client.sandbox.stream("exec-stream-1"):
            events.append(event)

        assert len(events) == 3
        assert events[0].event == "message"
        assert events[0].data == "chunk 1"
        assert events[1].event == "stderr"
        assert events[1].data == "warning message"
        assert events[2].data == "chunk 2"


@pytest.mark.asyncio
async def test_sandbox_run_high_level():
    sse_body = (
        b"event: stdout\n"
        b"data: Line 1\n\n"
        b"event: stdout\n"
        b"data: Line 2\n\n"
        b"event: complete\n"
        b"data: {\"exit_code\": 0, \"status\": \"completed\", \"duration_ms\": 500}\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/sandbox/async":
            return httpx.Response(
                202,
                json={
                    "message": "Accepted",
                    "success": True,
                    "payload": {"execution_id": "exec-run-456"},
                },
            )
        elif request.url.path == "/api/v1/sandbox/exec-run-456/stream":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=sse_body,
            )
        elif request.url.path == "/api/v1/sandbox/exec-run-456":
            return httpx.Response(
                200,
                json={
                    "message": "OK",
                    "success": True,
                    "payload": {
                        "execution_id": "exec-run-456",
                        "status": "completed",
                        "stdout": "Line 1\nLine 2\n",
                        "stderr": "",
                        "exit_code": 0,
                        "duration_ms": 500,
                    },
                },
            )
        return httpx.Response(404)

    captured_chunks: list[tuple[str, str]] = []

    def on_chunk(stream_name: str, text: str) -> None:
        captured_chunks.append((stream_name, text))

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="https://api.claros.ai", httpx_client=httpx_client) as client:
        res = await client.sandbox.run(
            code="echo Line 1\necho Line 2",
            language="bash",
            on_chunk=on_chunk,
        )

        assert isinstance(res, ExecuteResponse)
        assert res.execution_id == "exec-run-456"
        assert res.exit_code == 0
        assert res.status == "completed"
        assert "Line 1" in res.stdout
        assert "Line 2" in res.stdout
        assert len(captured_chunks) >= 2


@pytest.mark.asyncio
async def test_sandbox_run_polls_until_complete():
    poll_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        if request.url.path == "/api/v1/sandbox/async":
            return httpx.Response(
                202,
                json={
                    "message": "Accepted",
                    "success": True,
                    "payload": {"execution_id": "exec-poll-789"},
                },
            )
        elif request.url.path == "/api/v1/sandbox/exec-poll-789/stream":
            # Stream disconnects immediately or empty
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=b"",
            )
        elif request.url.path == "/api/v1/sandbox/exec-poll-789":
            poll_count += 1
            if poll_count == 1:
                return httpx.Response(
                    200,
                    json={
                        "message": "Pending",
                        "success": True,
                        "payload": {
                            "execution_id": "exec-poll-789",
                            "status": "pending",
                            "stdout": "",
                            "stderr": "",
                            "exit_code": 0,
                            "duration_ms": 0,
                        },
                    },
                )
            return httpx.Response(
                200,
                json={
                    "message": "OK",
                    "success": True,
                    "payload": {
                        "execution_id": "exec-poll-789",
                        "status": "completed",
                        "stdout": "Hello from ClarOS sandbox!",
                        "stderr": "",
                        "exit_code": 0,
                        "duration_ms": 120,
                    },
                },
            )
        return httpx.Response(404)

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="https://api.claros.ai", httpx_client=httpx_client) as client:
        res = await client.sandbox.run(
            code="print('Hello from ClarOS sandbox!')",
            language="python",
            poll_interval=0.01,
        )

        assert isinstance(res, ExecuteResponse)
        assert res.execution_id == "exec-poll-789"
        assert res.status == "completed"
        assert res.stdout == "Hello from ClarOS sandbox!"
        assert poll_count == 2


@pytest.mark.asyncio
async def test_sandbox_run_sse_status_event_autoclose():
    sse_body = (
        b"event: stdout\n"
        b"data: Hello from ClarOS sandbox!\n\n"
        b"event: status\n"
        b"data: completed\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/sandbox/async":
            return httpx.Response(
                202,
                json={
                    "message": "Accepted",
                    "success": True,
                    "payload": {"execution_id": "exec-auto-close-1"},
                },
            )
        elif request.url.path == "/api/v1/sandbox/exec-auto-close-1/stream":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=sse_body,
            )
        elif request.url.path == "/api/v1/sandbox/exec-auto-close-1":
            return httpx.Response(
                200,
                json={
                    "message": "OK",
                    "success": True,
                    "payload": {
                        "execution_id": "exec-auto-close-1",
                        "status": "completed",
                        "stdout": "Hello from ClarOS sandbox!",
                        "stderr": "",
                        "exit_code": 0,
                        "duration_ms": 150,
                    },
                },
            )
        return httpx.Response(404)

    captured_chunks: list[tuple[str, str]] = []

    def on_chunk(stream_name: str, text: str) -> None:
        captured_chunks.append((stream_name, text))

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="https://api.claros.ai", httpx_client=httpx_client) as client:
        res = await client.sandbox.run(
            code="print('Hello from ClarOS sandbox!')",
            language="python",
            on_chunk=on_chunk,
        )

        assert res.status == "completed"
        assert res.stdout == "Hello from ClarOS sandbox!"
        # on_chunk must only receive real stdout, never 'completed' status
        assert len(captured_chunks) == 1
        assert captured_chunks[0] == ("stdout", "Hello from ClarOS sandbox!")


