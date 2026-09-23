from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from claros_sdk.sandbox.manager import SandboxManager


class ExecuteCodeArgs(BaseModel):
    """Arguments for executing code synchronously in a sandbox."""

    model_config = ConfigDict(extra="allow")

    code: str = Field(..., description="The code block or shell commands to execute")
    language: Literal["python", "bash", "sh"] = Field(
        default="python",
        description="Programming language/runtime ('python', 'bash', 'sh')",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional stateful session ID to preserve environment state across executions",
    )
    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        le=3600,
        description="Maximum execution time in seconds",
    )
    network_enabled: bool | None = Field(
        default=None,
        description="Whether network/internet access is enabled in the sandbox",
    )
    env: dict[str, str] | None = Field(
        default=None,
        description="Environment variables to pass into the sandbox",
    )


class ExecuteCodeAsyncArgs(ExecuteCodeArgs):
    """Arguments for enqueuing code for background execution in a sandbox."""


class GetExecutionStatusArgs(BaseModel):
    """Arguments for fetching status of an asynchronous execution."""

    model_config = ConfigDict(extra="allow")

    execution_id: str = Field(
        ...,
        description="UUID of the asynchronous execution",
    )


class TerminateSessionArgs(BaseModel):
    """Arguments for terminating a stateful sandbox session."""

    model_config = ConfigDict(extra="allow")

    session_id: str = Field(
        ...,
        description="Identifier of the stateful sandbox session to destroy",
    )


@dataclass
class AgentTool:
    """
    Callable tool descriptor formatted for AI agent runtimes.

    Supports:
    - Standard tool registration: tool(name, kind, tool.function, tool.args_schema)
    - OpenAI / Anthropic format: tool.to_openai_tool()
    - Multi-signature invocation: handler(ctx, args), handler(args), handler(**kwargs)
    """

    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[..., Awaitable[Any]]
    parameters: dict[str, Any] | None = None

    @property
    def function(self) -> Callable[..., Awaitable[Any]]:
        """Underlying callable function for agent registry."""
        return self.handler

    @property
    def args_schema(self) -> type[BaseModel]:
        """Pydantic model class for agent framework schema validation."""
        return self.args_model

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI / Anthropic compatible tool calling format."""
        params = self.parameters or self.args_model.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
        }

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self.handler(*args, **kwargs)


def _extract_args(args_cls: type[BaseModel], *pos_args: Any, **kwargs: Any) -> dict[str, Any]:
    """
    Extract keyword arguments from various agent invocation signatures:
    - handler(ctx, args) -> agent_fabric pattern with TurnContext
    - handler(args)      -> standard single argument with Pydantic model or dict
    - handler(**kwargs)  -> standard direct keyword call
    """
    if len(pos_args) == 2:
        target = pos_args[1]
    elif len(pos_args) == 1:
        target = pos_args[0]
    else:
        target = kwargs

    if isinstance(target, BaseModel):
        return target.model_dump(exclude_none=True)
    if isinstance(target, dict):
        return target
    try:
        return args_cls.model_validate(target).model_dump(exclude_none=True)
    except Exception:
        return kwargs


def build_sandbox_tools(manager: SandboxManager) -> list[AgentTool]:
    """Construct collection of ready-to-use AI agent tools for sandbox operations."""

    async def _execute_code(*pos_args: Any, **kwargs: Any) -> dict[str, Any]:
        params = _extract_args(ExecuteCodeArgs, *pos_args, **kwargs)
        res = await manager.execute(**params)
        return res.model_dump()

    async def _execute_code_async(*pos_args: Any, **kwargs: Any) -> dict[str, Any]:
        params = _extract_args(ExecuteCodeAsyncArgs, *pos_args, **kwargs)
        res = await manager.execute_async(**params)
        return res.model_dump()

    async def _get_execution_status(*pos_args: Any, **kwargs: Any) -> dict[str, Any]:
        params = _extract_args(GetExecutionStatusArgs, *pos_args, **kwargs)
        res = await manager.get_execution(**params)
        return res.model_dump()

    async def _terminate_session(*pos_args: Any, **kwargs: Any) -> dict[str, Any]:
        params = _extract_args(TerminateSessionArgs, *pos_args, **kwargs)
        session_id = params.get("session_id", "")
        success = await manager.terminate_session(session_id=session_id)
        return {"session_id": session_id, "success": success}

    return [
        AgentTool(
            name="execute_code",
            description="Execute code (Python, Bash, or Shell) in an isolated sandbox and immediately receive output, exit code, and duration.",
            args_model=ExecuteCodeArgs,
            handler=_execute_code,
            parameters=ExecuteCodeArgs.model_json_schema(),
        ),
        AgentTool(
            name="execute_code_async",
            description="Enqueue code for background execution in an isolated sandbox. Returns execution_id for status tracking and output streaming.",
            args_model=ExecuteCodeAsyncArgs,
            handler=_execute_code_async,
            parameters=ExecuteCodeAsyncArgs.model_json_schema(),
        ),
        AgentTool(
            name="get_execution_status",
            description="Fetch current status and accumulated output for an asynchronous execution job.",
            args_model=GetExecutionStatusArgs,
            handler=_get_execution_status,
            parameters=GetExecutionStatusArgs.model_json_schema(),
        ),
        AgentTool(
            name="terminate_session",
            description="Purge and terminate a stateful sandbox session and release its container resources.",
            args_model=TerminateSessionArgs,
            handler=_terminate_session,
            parameters=TerminateSessionArgs.model_json_schema(),
        ),
    ]
