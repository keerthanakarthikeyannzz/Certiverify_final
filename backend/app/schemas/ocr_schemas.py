from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class OCRDataResponse(BaseModel):
    id: str
    certificate_id: str

    student_name: Optional[str] = None
    university_name: Optional[str] = None
    register_number: Optional[str] = None
    roll_number: Optional[str] = None
    certificate_number: Optional[str] = None
    department: Optional[str] = None
    course: Optional[str] = None
    cgpa: Optional[float] = None
    percentage: Optional[float] = None
    date_of_issue: Optional[str] = None
    qr_code_data: Optional[str] = None
    has_signature: bool
    has_seal: bool
    raw_text: Optional[str] = None

    ocr_accuracy: float
    ocr_engine: str
    field_confidences: dict
    created_at: datetime

    class Config:
        from_attributes = True


class OCRDataUpdateRequest(BaseModel):
    """Powers the structured editable table — the user can correct any misread field."""
    student_name: Optional[str] = None
    university_name: Optional[str] = None
    register_number: Optional[str] = None
    roll_number: Optional[str] = None
    certificate_number: Optional[str] = None
    department: Optional[str] = None
    course: Optional[str] = None
    cgpa: Optional[float] = None
    percentage: Optional[float] = None
    date_of_issue: Optional[str] = None


class FieldValidationItem(BaseModel):
    field: str
    label: str
    extracted_value: Optional[str] = None
    confidence: float  # 0-100 or 0-1
    status: str       # VALID | INVALID | MISSING | LOW_CONFIDENCE | NOT_APPLICABLE
    reason: str


class DocumentValidationResponse(BaseModel):
    certificate_id: str
    document_type: str
    classification_confidence: float
    expected_fields: list[str]
    field_validations: list[FieldValidationItem]

