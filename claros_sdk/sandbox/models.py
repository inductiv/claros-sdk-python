from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ExecuteRequest(BaseModel):
    """Request payload for sandbox code execution."""

    model_config = ConfigDict(extra="allow")

    code: str = Field(..., min_length=1, description="Code block or shell script to execute")
    language: Literal["python", "bash", "sh"] = Field(
        default="python", description="Execution language/environment"
    )
    session_id: str | None = Field(
        default=None, description="Optional stateful session identifier"
    )
    timeout_seconds: int | None = Field(
        default=None, ge=1, le=3600, description="Max execution duration in seconds"
    )
    network_enabled: bool | None = Field(
        default=None, description="Whether outbound network connectivity is permitted"
    )
    env: dict[str, str] | None = Field(
        default=None, description="Custom environment variables injected into sandbox"
    )


class ExecuteResponse(BaseModel):
    """Completed execution outcome from sandbox service."""

    model_config = ConfigDict(extra="allow")

    execution_id: str | None = Field(
        default=None, description="Unique execution UUID"
    )
    status: Literal["completed", "failed", "timeout", "killed"] | str = Field(
        default="completed", description="Execution lifecycle outcome"
    )
    stdout: str = Field(default="", description="Captured standard output")
    stderr: str = Field(default="", description="Captured standard error")
    exit_code: int = Field(default=0, description="Process exit status code")
    duration_ms: int = Field(default=0, description="Execution duration in milliseconds")

    @property
    def is_success(self) -> bool:
        """True if process exited with code 0 and status is completed."""
        return self.exit_code == 0 and self.status == "completed"

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> ExecuteResponse:
        """Parse payload whether enveloped in standard ClarOS API response or flat."""
        payload = data.get("payload", data) if isinstance(data, dict) else data
        if not isinstance(payload, dict):
            raise ValueError(f"Expected dict payload, got {type(payload)}")
        return cls.model_validate(payload)


class AsyncExecuteResponse(BaseModel):
    """Acknowledgement returned when code execution is enqueued asynchronously."""

    model_config = ConfigDict(extra="allow")

    execution_id: str = Field(..., description="UUID assigned to queued execution")
    message: str = Field(default="", description="Acknowledgement message")
    status: str = Field(default="accepted", description="Execution queue status")

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> AsyncExecuteResponse:
        """Parse payload whether enveloped in standard ClarOS API response or flat."""
        message = data.get("message", "") if isinstance(data, dict) else ""
        payload = data.get("payload", data) if isinstance(data, dict) else data
        if isinstance(payload, dict):
            exec_id = payload.get("execution_id", payload.get("id", ""))
            return cls(
                execution_id=exec_id,
                message=message or payload.get("message", ""),
                status=payload.get("status", "accepted"),
            )
        raise ValueError(f"Expected dict payload for AsyncExecuteResponse, got {type(payload)}")


class StreamEvent(BaseModel):
    """Frame emitted over Server-Sent Events stream."""

    model_config = ConfigDict(extra="allow")

    event: str = Field(default="message", description="SSE event name")
    data: str = Field(..., description="Stream data payload")
    id: str | None = Field(default=None, description="SSE event ID")
    stream: Literal["stdout", "stderr", "system", "status"] | None = Field(
        default=None, description="Stream source if discernible"
    )
