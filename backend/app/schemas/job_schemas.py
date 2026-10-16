from datetime import datetime
from typing import Any
from pydantic import BaseModel


class JobResponse(BaseModel):
    id: str
    job_id: str | None = None  # alias helper
    certificate_id: str
    organization_id: str | None = None
    status: str
    current_stage: str
    progress_percentage: int
    stage_states: dict[str, Any] | None = None
    error_details: str | None = None
    failed_stage: str | None = None
    retry_count: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class JobCreateResponse(BaseModel):
    job_id: str
    certificate_id: str
    status: str
    current_stage: str
    progress_percentage: int
    message: str = "Verification job enqueued successfully"
