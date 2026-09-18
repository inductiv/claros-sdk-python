"""ClarOS Sandbox execution module for AI agents."""

from __future__ import annotations

__all__ = [
    "AgentTool",
    "AsyncExecuteResponse",
    "ExecuteCodeArgs",
    "ExecuteCodeAsyncArgs",
    "ExecuteRequest",
    "ExecuteResponse",
    "GetExecutionStatusArgs",
    "SandboxManager",
    "SandboxSession",
    "StreamEvent",
    "TerminateSessionArgs",
]


def __getattr__(name: str):
    if name == "SandboxManager":
        from claros_sdk.sandbox.manager import SandboxManager

        return SandboxManager
    if name == "SandboxSession":
        from claros_sdk.sandbox.session import SandboxSession

        return SandboxSession
    if name in (
        "AgentTool",
        "ExecuteCodeArgs",
        "ExecuteCodeAsyncArgs",
        "GetExecutionStatusArgs",
        "TerminateSessionArgs",
    ):
        from claros_sdk.sandbox import tools

        return getattr(tools, name)
    if name in ("ExecuteRequest", "ExecuteResponse", "AsyncExecuteResponse", "StreamEvent"):
        from claros_sdk.sandbox import models

        return getattr(models, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
