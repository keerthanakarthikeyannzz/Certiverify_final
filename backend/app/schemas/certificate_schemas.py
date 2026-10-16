from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CertificateResponse(BaseModel):
    id: str
    original_filename: str
    file_type: str
    file_size_bytes: int
    sha256_hash: str
    group_id: Optional[str] = None
    uploaded_at: datetime
    is_history_hidden: Optional[bool] = False

    class Config:
        from_attributes = True


class CertificateUploadBatchResponse(BaseModel):
    group_id: str
    certificates: list[CertificateResponse]


class CertificateListItem(CertificateResponse):
    document_type: Optional[str] = None
    trust_score: Optional[float] = None
    prediction_label: Optional[str] = None


class CertificateGroupLinkRequest(BaseModel):
    certificate_ids: list[str] = Field(min_length=2)


class CertificateHistoryResponse(BaseModel):
    certificate_id: str
    filename: str
    file_type: str
    document_type: Optional[str] = None
    trust_score: Optional[float] = None
    prediction: Optional[str] = None
    status: str = "COMPLETED"
    timestamp: datetime
    report_reference: Optional[str] = None

    class Config:
        from_attributes = True

