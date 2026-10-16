from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DocumentTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    certificate_id: str
    predicted_type: str
    confidence_score: float
    model_used: str
    created_at: datetime


class DocumentTypeSignals(BaseModel):
    aspect_ratio: float = 1.0
    has_circular_seal: bool = False
    has_qr_code: bool = False
    edge_density: float = 0.0
    reasoning: str | None = None


class ClassifyResponse(DocumentTypeResponse):
    signals: DocumentTypeSignals | dict | None = None

