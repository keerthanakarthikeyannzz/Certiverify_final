from datetime import datetime
from pydantic import BaseModel


class ComparisonFieldDetail(BaseModel):
    values: list
    status: str  # matching | mismatched | missing


class DocumentComparisonResponse(BaseModel):
    id: str
    group_id: str
    matching_fields: list[str]
    mismatched_fields: list[str]
    missing_fields: list[str]
    consistency_percentage: float
    details: dict[str, ComparisonFieldDetail] = {}
    created_at: datetime

    class Config:
        from_attributes = True
