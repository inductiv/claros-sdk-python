from __future__ import annotations

from pydantic import BaseModel, Field


class TokenVerifyPayload(BaseModel):
    """Payload returned by ClarOS token verification service."""

    valid: bool
    user_id: str
    session_id: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class TokenVerifyResponse(BaseModel):
    """Top-level response envelope from ClarOS token verification service."""

    success: bool
    message: str
    payload: TokenVerifyPayload


class TenantAuthContextPayload(BaseModel):
    """Payload returned by ClarOS tenant authorization service."""

    allowed: bool
    user_id: str
    tenant_id: str
    tenant_slug: str
    role: str
    permissions: list[str] = Field(default_factory=list)
    license_tier: str
    headers: dict[str, str] = Field(default_factory=dict)


class TenantAuthContextResponse(BaseModel):
    """Top-level response envelope from ClarOS tenant authorization service."""

    success: bool
    message: str
    payload: TenantAuthContextPayload


class ClarOSAuthContext(BaseModel):
    """Resolved authorization context model returned after authentication."""

    user_id: str
    tenant_id: str
    tenant_slug: str
    role: str
    permissions: list[str] = Field(default_factory=list)
    license_tier: str
    headers: dict[str, str] = Field(default_factory=dict)
