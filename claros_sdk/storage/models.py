from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StorageAsset(BaseModel):
    """Metadata record for a tenant storage asset."""

    model_config = ConfigDict(extra="allow")

    id: str
    tenant_id: str
    user_id: str | None = None
    category: str = "general"
    file_name: str
    content_type: str = "application/octet-stream"
    file_size_bytes: int = 0
    bucket_name: str = ""
    file_key: str = ""
    checksum: str | None = None
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> StorageAsset:
        payload = data.get("payload", data) if isinstance(data, dict) else data
        return cls.model_validate(payload)


class PresignedURLResponse(BaseModel):
    """Time-limited pre-signed download URL response."""

    model_config = ConfigDict(extra="allow")

    id: str
    download_url: str
    expires_at: datetime | str | None = None
    expires_in: int = 0

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> PresignedURLResponse:
        payload = data.get("payload", data) if isinstance(data, dict) else data
        return cls.model_validate(payload)


class StoragePaginationMeta(BaseModel):
    """Pagination metadata returned on list files responses."""

    model_config = ConfigDict(extra="allow")

    total: int = 0
    has_next: bool = False
    page: int = 1
    limit: int = 20


class StorageAssetListResponse(BaseModel):
    """Paginated list of tenant storage assets."""

    model_config = ConfigDict(extra="allow")

    items: list[StorageAsset] = Field(default_factory=list)
    meta: StoragePaginationMeta = Field(default_factory=StoragePaginationMeta)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> StorageAssetListResponse:
        raw_items = data.get("payload", []) if isinstance(data, dict) else []
        raw_meta = data.get("meta", {}) if isinstance(data, dict) else {}
        return cls(
            items=[StorageAsset.model_validate(item) for item in (raw_items or [])],
            meta=StoragePaginationMeta.model_validate(raw_meta or {}),
        )
