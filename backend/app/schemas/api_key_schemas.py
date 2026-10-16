from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Name or label for the API key")
    permissions: List[str] = Field(default_factory=list, description="List of permission scopes e.g. ['certificate:read', 'certificate:verify']")
    rate_limit: int = Field(default=100, ge=1, le=10000, description="Requests per minute allowed")
    expires_at: Optional[datetime] = Field(None, description="Optional expiration date")


class ApiKeyCreateResponse(BaseModel):
    id: str
    organization_id: str
    key_prefix: str
    raw_key: str
    name: str
    permissions: List[str]
    status: str
    rate_limit: int
    expires_at: Optional[datetime]
    created_at: datetime


class ApiKeyResponse(BaseModel):
    id: str
    organization_id: str
    key_prefix: str
    name: str
    permissions: List[str]
    status: str
    rate_limit: int
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    revoked_at: Optional[datetime]
