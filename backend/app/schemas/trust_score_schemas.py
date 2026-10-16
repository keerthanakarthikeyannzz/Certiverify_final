from datetime import datetime
from pydantic import BaseModel


class TrustScoreResponse(BaseModel):
    id: str
    certificate_id: str
    score: float
    breakdown: dict
    created_at: datetime

    class Config:
        from_attributes = True
