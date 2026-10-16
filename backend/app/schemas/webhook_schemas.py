from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, HttpUrl, Field


class WebhookCreateRequest(BaseModel):
    endpoint_url: str = Field(..., description="Target URL for receiving webhook POST requests")
    subscribed_events: List[str] = Field(..., description="List of events e.g. ['verification.completed', 'fraud.alert']")


class WebhookUpdateRequest(BaseModel):
    endpoint_url: Optional[str] = None
    subscribed_events: Optional[List[str]] = None
    active: Optional[bool] = None


class WebhookResponse(BaseModel):
    id: str
    organization_id: str
    endpoint_url: str
    subscribed_events: List[str]
    active: bool
    created_at: datetime
    updated_at: datetime
    # Note: secret is returned ONLY once upon creation or re-generation, not in list or standard get responses!
    secret: Optional[str] = None


class WebhookDeliveryResponse(BaseModel):
    id: str
    webhook_endpoint_id: str
    event_type: str
    payload: Dict[str, Any]
    status: str
    attempt_count: int
    response_status: Optional[int]
    response_body: Optional[str]
    next_retry_at: Optional[datetime]
    created_at: datetime
    delivered_at: Optional[datetime]
