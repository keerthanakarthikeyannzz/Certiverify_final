from datetime import datetime
from typing import Any
from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: str
    organization_id: str | None = None
    actor_user_id: str | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    timestamp: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    metadata_json: dict[str, Any] | None = None

    class Config:
        from_attributes = True
