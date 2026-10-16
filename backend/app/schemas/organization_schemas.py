from datetime import datetime
from pydantic import BaseModel, Field


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    slug: str | None = None


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrganizationMemberResponse(BaseModel):
    id: str
    organization_id: str
    user_id: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True
