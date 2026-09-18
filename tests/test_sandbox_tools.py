from __future__ import annotations

import httpx
import pytest

from claros_sdk import ClarOSClient
from claros_sdk.sandbox.tools import AgentTool


@pytest.mark.asyncio
async def test_sandbox_agent_tools_schema():
    client = ClarOSClient(base_url="https://api.claros.ai")
    tools = client.sandbox.get_tools()

    assert len(tools) == 4
    tool_names = [t.name for t in tools]
    assert "execute_code" in tool_names
    assert "execute_code_async" in tool_names
    assert "get_execution_status" in tool_names
    assert "terminate_session" in tool_names

    # Verify OpenAI tool formatting
    for tool in tools:
        assert isinstance(tool, AgentTool)
        schema = tool.to_openai_tool()
        assert schema["type"] == "function"
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]
        assert schema["function"]["parameters"]["type"] == "object"


@pytest.mark.asyncio
async def test_sandbox_agent_tools_execution():
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        if request.url.path == "/api/v1/sandbox/execute":
            return httpx.Response(
                200,
                json={
                    "message": "Execution finished",
                    "success": True,
                    "payload": {
                        "execution_id": "exec-tool-1",
                        "status": "completed",
                        "stdout": "42\n",
                        "exit_code": 0,
                    },
                },
            )
        elif request.method == "DELETE" and request.url.path.startswith("/api/v1/sandbox/sessions/"):
            return httpx.Response(
                200,
                json={"message": "Deleted", "success": True, "payload": "OK"},
            )
        return httpx.Response(404)

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="https://api.claros.ai", httpx_client=httpx_client) as client:
        tools = {t.name: t for t in client.sandbox.get_tools()}

        # Call execute_code tool handler
        exec_res = await tools["execute_code"](code="print(42)", language="python")
        assert exec_res["stdout"] == "42\n"
        assert exec_res["exit_code"] == 0
        assert exec_res["status"] == "completed"

        # Call terminate_session tool handler
        term_res = await tools["terminate_session"](session_id="sess-del-1")
        assert term_res["success"] is True


@pytest.mark.asyncio
async def test_agent_fabric_tool_calling_pattern():
    """Verify tool functions can be registered and called with (ctx, args) or (args)."""
    from claros_sdk.sandbox.tools import ExecuteCodeArgs, TerminateSessionArgs

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": "Execution finished",
                "success": True,
                "payload": {
                    "execution_id": "exec-fabric-1",
                    "status": "completed",
                    "stdout": "result from fabric",
                    "exit_code": 0,
                },
            },
        )

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with ClarOSClient(base_url="https://api.claros.ai", httpx_client=httpx_client) as client:
        tools = {t.name: t for t in client.sandbox.get_tools()}
        exec_tool = tools["execute_code"]

        # 1. Properties match what agent_fabric needs:
        assert exec_tool.name == "execute_code"
        assert exec_tool.args_schema is ExecuteCodeArgs
        assert exec_tool.args_model is ExecuteCodeArgs
        assert callable(exec_tool.function)

        # Mock TurnContext object
        class MockTurnContext:
            pass

        ctx = MockTurnContext()

        # 2. Call with (ctx, args) - agent_fabric style:
        args_obj = ExecuteCodeArgs(code="print('fabric')", language="python")
        res_ctx = await exec_tool.function(ctx, args_obj)
        assert res_ctx["stdout"] == "result from fabric"

        # 3. Call with (args) directly:
        res_direct = await exec_tool.function(args_obj)
        assert res_direct["stdout"] == "result from fabric"
