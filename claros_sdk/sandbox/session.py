from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Literal

from claros_sdk.exceptions import ClarOSError
from claros_sdk.sandbox.models import AsyncExecuteResponse, ExecuteResponse

if TYPE_CHECKING:
    from collections.abc import Callable
    from claros_sdk.sandbox.manager import SandboxManager


class SandboxSession:
    """Represents a stateful execution session with container resource persistence."""

    def __init__(
        self,
        manager: SandboxManager,
        session_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        self._manager = manager
        self.session_id = session_id or str(uuid.uuid4())
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.is_closed = False

    def _check_active(self) -> None:
        if self.is_closed:
            raise ClarOSError(f"SandboxSession '{self.session_id}' has already been terminated.")

    async def execute(
        self,
        code: str,
        language: Literal["python", "bash", "sh"] = "python",
        timeout_seconds: int | None = None,
        network_enabled: bool | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResponse:
        """Execute code within this stateful session."""
        self._check_active()
        return await self._manager.execute(
            code=code,
            language=language,
            session_id=self.session_id,
            timeout_seconds=timeout_seconds,
            network_enabled=network_enabled,
            env=env,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            user_id=self.user_id,
        )

    async def execute_async(
        self,
        code: str,
        language: Literal["python", "bash", "sh"] = "python",
        timeout_seconds: int | None = None,
        network_enabled: bool | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncExecuteResponse:
        """Enqueue asynchronous code execution within this stateful session."""
        self._check_active()
        return await self._manager.execute_async(
            code=code,
            language=language,
            session_id=self.session_id,
            timeout_seconds=timeout_seconds,
            network_enabled=network_enabled,
            env=env,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            user_id=self.user_id,
        )

    async def run(
        self,
        code: str,
        language: Literal["python", "bash", "sh"] = "python",
        timeout_seconds: int | None = None,
        network_enabled: bool | None = None,
        env: dict[str, str] | None = None,
        on_chunk: Callable[[str, str], Any] | None = None,
    ) -> ExecuteResponse:
        """High-level runner executing within this stateful session."""
        self._check_active()
        return await self._manager.run(
            code=code,
            language=language,
            session_id=self.session_id,
            timeout_seconds=timeout_seconds,
            network_enabled=network_enabled,
            env=env,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            user_id=self.user_id,
            on_chunk=on_chunk,
        )

    async def terminate(self) -> bool:
        """Purge and release resources associated with this session."""
        if self.is_closed:
            return True
        success = await self._manager.terminate_session(
            session_id=self.session_id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            user_id=self.user_id,
        )
        self.is_closed = True
        return success

    async def __aenter__(self) -> SandboxSession:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.terminate()
