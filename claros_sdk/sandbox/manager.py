from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Literal

from claros_sdk.exceptions import (
    ClarOSAPIError,
    ClarOSSandboxError,
    ClarOSSandboxTimeoutError,
)
from claros_sdk.sandbox.models import (
    AsyncExecuteResponse,
    ExecuteRequest,
    ExecuteResponse,
    StreamEvent,
)
from claros_sdk.sandbox.session import SandboxSession
from claros_sdk.sandbox.tools import AgentTool, build_sandbox_tools

if TYPE_CHECKING:
    from claros_sdk.client import ClarOSClient

logger = logging.getLogger(__name__)


class SandboxManager:
    """Manages isolated code execution in ClarOS Sandboxes."""

    def __init__(self, client: ClarOSClient) -> None:
        self._client = client

    async def execute(
        self,
        code: str,
        language: Literal["python", "bash", "sh"] = "python",
        session_id: str | None = None,
        timeout_seconds: int | None = None,
        network_enabled: bool | None = None,
        env: dict[str, str] | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> ExecuteResponse:
        """
        Execute code synchronously in an isolated sandbox.

        Automatically propagates tenant headers and auth tokens from ClarOSClient.
        """
        request_model = ExecuteRequest(
            code=code,
            language=language,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
            network_enabled=network_enabled,
            env=env,
        )
        payload = request_model.model_dump(exclude_none=True)
        headers = self._client.get_tenant_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )

        try:
            data = await self._client.post(
                path="/api/v1/sandbox/execute",
                json=payload,
                headers=headers,
            )
        except ClarOSAPIError as exc:
            if exc.status_code == 408 or "timeout" in exc.message.lower():
                raise ClarOSSandboxTimeoutError(
                    status_code=exc.status_code,
                    message=exc.message,
                    payload=exc.payload,
                ) from exc
            raise ClarOSSandboxError(
                status_code=exc.status_code,
                message=exc.message,
                payload=exc.payload,
            ) from exc
        except Exception as exc:
            raise ClarOSSandboxError(
                status_code=500,
                message=f"Sandbox execution request failed: {exc}",
            ) from exc

        return ExecuteResponse.from_api_response(data)

    async def execute_async(
        self,
        code: str,
        language: Literal["python", "bash", "sh"] = "python",
        session_id: str | None = None,
        timeout_seconds: int | None = None,
        network_enabled: bool | None = None,
        env: dict[str, str] | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> AsyncExecuteResponse:
        """
        Enqueue code for background execution in an isolated sandbox.

        Returns AsyncExecuteResponse with an execution_id for status tracking.
        """
        request_model = ExecuteRequest(
            code=code,
            language=language,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
            network_enabled=network_enabled,
            env=env,
        )
        payload = request_model.model_dump(exclude_none=True)
        headers = self._client.get_tenant_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )

        try:
            data = await self._client.post(
                path="/api/v1/sandbox/async",
                json=payload,
                headers=headers,
            )
        except ClarOSAPIError as exc:
            raise ClarOSSandboxError(
                status_code=exc.status_code,
                message=exc.message,
                payload=exc.payload,
            ) from exc
        except Exception as exc:
            raise ClarOSSandboxError(
                status_code=500,
                message=f"Sandbox async execution request failed: {exc}",
            ) from exc

        return AsyncExecuteResponse.from_api_response(data)

    async def get_execution(
        self,
        execution_id: str,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> ExecuteResponse:
        """Fetch current status and output buffer of an asynchronous execution."""
        headers = self._client.get_tenant_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )
        try:
            data = await self._client.get(
                path=f"/api/v1/sandbox/{execution_id}",
                headers=headers,
            )
        except ClarOSAPIError as exc:
            raise ClarOSSandboxError(
                status_code=exc.status_code,
                message=exc.message,
                payload=exc.payload,
            ) from exc
        except Exception as exc:
            raise ClarOSSandboxError(
                status_code=500,
                message=f"Failed to fetch execution {execution_id}: {exc}",
            ) from exc

        return ExecuteResponse.from_api_response(data)

    async def stream(
        self,
        execution_id: str,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream stdout/stderr from an execution in real-time via Server-Sent Events."""
        url = f"{self._client.base_url}/api/v1/sandbox/{execution_id}/stream"
        headers = self._client.get_tenant_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )
        headers["Accept"] = "text/event-stream"
        headers["Cache-Control"] = "no-cache"
        auth_header = await self._client._get_auth_header()
        if auth_header:
            headers["Authorization"] = auth_header

        try:
            async with self._client._client.stream(
                "GET", url, headers=headers, timeout=None
            ) as response:
                if response.status_code != 200:
                    raise ClarOSSandboxError(
                        status_code=response.status_code,
                        message=f"Stream request rejected with HTTP {response.status_code}",
                    )

                current_event = "message"
                current_id: str | None = None
                current_data_lines: list[str] = []

                async for line in response.aiter_lines():
                    if line.startswith(":"):
                        continue
                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                    elif line.startswith("id:"):
                        current_id = line[3:].strip()
                    elif line.startswith("data:"):
                        data_val = line[6:] if line.startswith("data: ") else line[5:]
                        current_data_lines.append(data_val)
                    elif line == "":
                        if current_data_lines:
                            raw_data = "\n".join(current_data_lines)
                            stream_type: Literal["stdout", "stderr", "system", "status"] | None = None
                            if current_event in ("stdout", "stderr", "system", "status"):
                                stream_type = current_event  # type: ignore[assignment]
                            elif raw_data.startswith("{") and raw_data.endswith("}"):
                                try:
                                    parsed = json.loads(raw_data)
                                    if isinstance(parsed, dict):
                                        if "stream" in parsed:
                                            stream_type = parsed["stream"]
                                        if "stdout" in parsed:
                                            stream_type = "stdout"
                                            raw_data = str(parsed["stdout"])
                                        elif "stderr" in parsed:
                                            stream_type = "stderr"
                                            raw_data = str(parsed["stderr"])
                                        elif "text" in parsed:
                                            raw_data = str(parsed["text"])
                                except Exception:
                                    pass

                            yield StreamEvent(
                                event=current_event,
                                data=raw_data,
                                id=current_id,
                                stream=stream_type,
                            )
                            # Terminal event from backend signals stream completion; close immediately
                            if current_event in ("status", "complete", "exit"):
                                break
                        current_event = "message"
                        current_id = None
                        current_data_lines = []

                if current_data_lines:
                    raw_data = "\n".join(current_data_lines)
                    stream_type = None
                    if current_event in ("stdout", "stderr", "system", "status"):
                        stream_type = current_event  # type: ignore[assignment]
                    yield StreamEvent(
                        event=current_event,
                        data=raw_data,
                        id=current_id,
                        stream=stream_type,
                    )
        except ClarOSSandboxError:
            raise
        except Exception as exc:
            raise ClarOSSandboxError(
                status_code=500,
                message=f"Sandbox SSE streaming failed: {exc}",
            ) from exc

    async def run(
        self,
        code: str,
        language: Literal["python", "bash", "sh"] = "python",
        session_id: str | None = None,
        timeout_seconds: int | None = None,
        network_enabled: bool | None = None,
        env: dict[str, str] | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
        on_chunk: Callable[[str, str], Any] | None = None,
        poll_interval: float = 0.5,
    ) -> ExecuteResponse:
        """
        High-level runner: Dispatches execution asynchronously, streams stdout/stderr
        chunks in real-time via SSE, waits until execution completes, and returns the final ExecuteResponse.
        """
        async_res = await self.execute_async(
            code=code,
            language=language,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
            network_enabled=network_enabled,
            env=env,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        terminal_status: str | None = None
        start_time = time.time()

        try:
            async for event in self.stream(
                execution_id=async_res.execution_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
            ):
                # Filter out terminal lifecycle events from user-facing chunk stream
                if event.event in ("status", "complete", "exit", "system"):
                    if event.event == "status" and event.data.strip() in (
                        "completed",
                        "failed",
                        "timeout",
                        "killed",
                    ):
                        terminal_status = event.data.strip()
                        break
                    elif event.event in ("complete", "exit"):
                        terminal_status = "completed"
                        break
                    continue

                stream_name = event.stream or ("stderr" if event.event == "stderr" else "stdout")
                if stream_name == "stderr":
                    stderr_chunks.append(event.data)
                else:
                    stdout_chunks.append(event.data)

                if on_chunk:
                    res = on_chunk(stream_name, event.data)
                    if asyncio.iscoroutine(res):
                        await res
        except Exception as exc:
            logger.debug(
                "SSE stream completed or closed for execution %s: %s",
                async_res.execution_id,
                exc,
            )

        # If SSE stream provided terminal status, execution is finished
        if terminal_status:
            duration_ms = int((time.time() - start_time) * 1000)
            exit_code = 0 if terminal_status == "completed" else 1
            try:
                exec_res = await self.get_execution(
                    execution_id=async_res.execution_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                )
                if exec_res.status in ("completed", "failed", "timeout", "killed"):
                    if not exec_res.stdout and stdout_chunks:
                        exec_res.stdout = "\n".join(stdout_chunks)
                    if not exec_res.stderr and stderr_chunks:
                        exec_res.stderr = "\n".join(stderr_chunks)
                    return exec_res
                elif exec_res.duration_ms:
                    duration_ms = exec_res.duration_ms
            except Exception:
                pass

            return ExecuteResponse(
                execution_id=async_res.execution_id,
                status=terminal_status,  # type: ignore[arg-type]
                stdout="\n".join(stdout_chunks),
                stderr="\n".join(stderr_chunks),
                exit_code=exit_code,
                duration_ms=duration_ms,
            )

        # Fallback polling loop if stream closed without terminal status event
        max_duration = float(timeout_seconds or 60)
        last_response: ExecuteResponse | None = None

        while (time.time() - start_time) < max_duration:
            try:
                exec_res = await self.get_execution(
                    execution_id=async_res.execution_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                )
                last_response = exec_res
                if exec_res.status in ("completed", "failed", "timeout", "killed"):
                    if not exec_res.stdout and stdout_chunks:
                        exec_res.stdout = "\n".join(stdout_chunks)
                    if not exec_res.stderr and stderr_chunks:
                        exec_res.stderr = "\n".join(stderr_chunks)
                    return exec_res
            except Exception as exc:
                logger.debug(
                    "Polling execution %s status failed: %s",
                    async_res.execution_id,
                    exc,
                )

            await asyncio.sleep(poll_interval)

        if last_response is not None:
            return last_response

        raise ClarOSSandboxTimeoutError(
            status_code=408,
            message=f"Sandbox execution '{async_res.execution_id}' did not complete within {max_duration}s",
            payload={"execution_id": async_res.execution_id},
        )

    def session(
        self,
        session_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> SandboxSession:
        """Create or reference a stateful multi-step sandbox session."""
        return SandboxSession(
            manager=self,
            session_id=session_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )

    async def terminate_session(
        self,
        session_id: str,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> bool:
        """Immediately terminate a stateful session and purge its resources."""
        url = f"{self._client.base_url}/api/v1/sandbox/sessions/{session_id}"
        headers = self._client.get_tenant_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )
        auth_header = await self._client._get_auth_header()
        if auth_header:
            headers["Authorization"] = auth_header

        try:
            response = await self._client._client.delete(url, headers=headers)
        except Exception as exc:
            raise ClarOSSandboxError(
                status_code=500,
                message=f"Failed to terminate session '{session_id}': {exc}",
            ) from exc

        if response.status_code in (200, 204, 404):
            return True

        raise ClarOSSandboxError(
            status_code=response.status_code,
            message=f"Terminate session rejected with HTTP {response.status_code}: {response.text}",
        )

    def get_tools(self) -> list[AgentTool]:
        """
        Return structured AI agent tools configured for this sandbox manager.
        """
        return build_sandbox_tools(self)
