"""
Pydantic response schemas for Phase 3 Evidence API.
"""
from datetime import datetime
from pydantic import BaseModel, Field


class EvidenceItemResponse(BaseModel):
    id: str
    evidence_id: str
    organization_id: str | None = None
    certificate_id: str
    verification_job_id: str | None = None
    evidence_type: str
    source: str
    stage: str
    timestamp: datetime
    document_hash: str
    algorithm_engine: str
    algorithm_version: str | None = "1.0.0"
    confidence: float
    result: str
    explanation: str
    details: dict | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class EvidencePaginatedResponse(BaseModel):
    items: list[EvidenceItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
