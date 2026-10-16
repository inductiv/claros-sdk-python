from __future__ import annotations

from collections.abc import AsyncIterator
import mimetypes
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from claros_sdk.exceptions import ClarOSAPIError, ClarOSError
from claros_sdk.storage.models import (
    PresignedURLResponse,
    StorageAsset,
    StorageAssetListResponse,
)

if TYPE_CHECKING:
    from claros_sdk.client import ClarOSClient


class StorageManager:
    """Client wrapper for ClarOS multi-tenant file storage endpoints."""

    BASE_PATH = "/api/v1/platform/storage"

    def __init__(self, client: ClarOSClient) -> None:
        self._client = client

    async def _build_headers(
        self,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        headers = self._client.get_tenant_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )
        auth_header = await self._client._get_auth_header()
        if auth_header:
            headers["Authorization"] = auth_header
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _build_params(tenant_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        params = {k: v for k, v in kwargs.items() if v is not None}
        if tenant_id:
            params["tenant_id"] = tenant_id
        return params

    async def upload(
        self,
        file: bytes | str | Path | IO[bytes],
        file_name: str | None = None,
        category: str = "general",
        content_type: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> StorageAsset:
        """Upload a file via POST /api/v1/platform/storage/upload."""
        if isinstance(file, (str, Path)):
            path_obj = Path(file)
            file_name = file_name or path_obj.name
            file_bytes = path_obj.read_bytes()
        elif isinstance(file, bytes):
            file_name = file_name or "file"
            file_bytes = file
        else:
            file_name = file_name or getattr(file, "name", "file")
            file_bytes = file.read()

        if not content_type:
            guessed, _ = mimetypes.guess_type(file_name)
            content_type = guessed or "application/octet-stream"

        url = f"{self._client.base_url}{self.BASE_PATH}/upload"
        headers = await self._build_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )
        params = self._build_params(tenant_id=tenant_id)
        files = {"file": (file_name, file_bytes, content_type)}
        data = {"category": category} if category else {}

        try:
            response = await self._client._client.post(
                url, params=params, data=data, files=files, headers=headers
            )
        except Exception as exc:
            raise ClarOSError(f"Storage upload failed: {exc}") from exc

        if response.status_code not in (200, 201):
            raise ClarOSAPIError(response.status_code, response.text)

        return StorageAsset.from_api_response(response.json())

    async def list_files(
        self,
        page: int = 1,
        limit: int = 20,
        category: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> StorageAssetListResponse:
        """List tenant files via GET /api/v1/platform/storage/files."""
        headers = self._client.get_tenant_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )
        params = self._build_params(
            tenant_id=tenant_id, page=page, limit=limit, category=category
        )
        res = await self._client.get(
            f"{self.BASE_PATH}/files", params=params, headers=headers
        )
        return StorageAssetListResponse.from_api_response(res)

    async def get_metadata(
        self,
        file_id: str,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> StorageAsset:
        """Fetch file metadata via GET /api/v1/platform/storage/files/{id}/metadata."""
        headers = self._client.get_tenant_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )
        params = self._build_params(tenant_id=tenant_id)
        res = await self._client.get(
            f"{self.BASE_PATH}/files/{file_id}/metadata",
            params=params,
            headers=headers,
        )
        return StorageAsset.from_api_response(res)

    async def get_presigned_url(
        self,
        file_id: str,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> PresignedURLResponse:
        """Generate a pre-signed download URL via GET /api/v1/platform/storage/files/{id}?presign=true."""
        headers = self._client.get_tenant_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )
        params = self._build_params(tenant_id=tenant_id, presign="true")
        res = await self._client.get(
            f"{self.BASE_PATH}/files/{file_id}",
            params=params,
            headers=headers,
        )
        return PresignedURLResponse.from_api_response(res)

    async def download(
        self,
        file_id: str,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> bytes:
        """Download file bytes via GET /api/v1/platform/storage/files/{id}."""
        url = f"{self._client.base_url}{self.BASE_PATH}/files/{file_id}"
        headers = await self._build_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )
        params = self._build_params(tenant_id=tenant_id)

        try:
            response = await self._client._client.get(
                url, params=params, headers=headers
            )
        except Exception as exc:
            raise ClarOSError(f"Storage download failed for '{file_id}': {exc}") from exc

        if response.status_code != 200:
            payload: dict[str, Any] | None = None
            try:
                body = response.json()
                if isinstance(body, dict):
                    payload = body
            except Exception:
                pass
            raise ClarOSAPIError(response.status_code, response.text, payload=payload)

        return response.content

    async def stream(
        self,
        file_id: str,
        range_header: str | None = None,
        chunk_size: int = 65536,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream file binary chunks via GET /api/v1/platform/storage/files/{id}/stream."""
        url = f"{self._client.base_url}{self.BASE_PATH}/files/{file_id}/stream"
        extra = {"Range": range_header} if range_header else None
        headers = await self._build_headers(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            extra=extra,
        )
        params = self._build_params(tenant_id=tenant_id)

        try:
            async with self._client._client.stream(
                "GET", url, params=params, headers=headers, timeout=None
            ) as response:
                if response.status_code not in (200, 206):
                    text = (await response.aread()).decode("utf-8", errors="replace")
                    raise ClarOSAPIError(response.status_code, text)

                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    yield chunk
        except ClarOSAPIError:
            raise
        except Exception as exc:
            raise ClarOSError(f"Storage stream failed for '{file_id}': {exc}") from exc

    async def delete(
        self,
        file_id: str,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> bool:
        """Delete a file via DELETE /api/v1/platform/storage/files/{id}."""
        url = f"{self._client.base_url}{self.BASE_PATH}/files/{file_id}"
        headers = await self._build_headers(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )
        params = self._build_params(tenant_id=tenant_id)

        try:
            response = await self._client._client.delete(
                url, params=params, headers=headers
            )
        except Exception as exc:
            raise ClarOSError(f"Storage delete failed for '{file_id}': {exc}") from exc

        if response.status_code not in (200, 204):
            raise ClarOSAPIError(response.status_code, response.text)

        return True
