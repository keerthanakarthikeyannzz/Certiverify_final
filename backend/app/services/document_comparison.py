"""
MODULE 5 - DOCUMENT COMPARISON (stored-group engine)

Cross-checks OCR data across a group of related documents (e.g. Degree +
Marksheet + Resume uploaded together, linked by Certificate.group_id).

Improvements over original:
- rapidfuzz replaces difflib.SequenceMatcher (faster, better OCR-noise handling)
- Three-level match status:
    "matching"  — similarity >= 82 %
    "partial"   — similarity 60–81 % (minor OCR noise / abbreviation)
    "mismatched"— similarity < 60 %
    "missing"   — fewer than 2 documents have the field
- consistency_percentage counts partial matches as 0.5
- comparison_score (0–100) returned for dashboard display
"""
import re

from app.models.models import OCRData

try:
    from rapidfuzz import fuzz as _rfuzz
    def _similarity(a: str, b: str) -> float:
        """Return 0-1 similarity using rapidfuzz token_sort_ratio."""
        return _rfuzz.token_sort_ratio(a.strip().lower(), b.strip().lower()) / 100.0
except ImportError:
    from difflib import SequenceMatcher
    def _similarity(a: str, b: str) -> float:  # type: ignore[misc]
        return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


TEXT_FIELDS = ["student_name", "register_number", "university_name", "course", "department"]
NUMERIC_FIELDS = ["cgpa", "percentage"]
DERIVED_FIELDS = ["graduation_year"]  # derived from date_of_issue

MATCH_THRESHOLD   = 0.82
PARTIAL_THRESHOLD = 0.60
NUMERIC_TOLERANCE = {"cgpa": 0.05, "percentage": 0.5}


class ComparisonResult:
    def __init__(
        self,
        matching: list[str],
        partial: list[str],
        mismatched: list[str],
        missing: list[str],
        consistency_pct: float,
        details: dict,
    ):
        self.matching_fields    = matching
        self.partial_fields     = partial
        self.mismatched_fields  = mismatched
        self.missing_fields     = missing
        self.consistency_percentage = consistency_pct
        self.comparison_score   = round(consistency_pct)
        self.details            = details  # field -> {values, status, similarity}


def _extract_year(date_str: str | None) -> str | None:
    if not date_str:
        return None
    match = re.search(r"(19|20)\d{2}", date_str)
    return match.group(0) if match else None


def _evaluate_text_field(values: list[str]) -> tuple[str, float]:
    """
    Returns (status, max_similarity).
    status ∈ {"matching", "partial", "mismatched", "missing"}
    """
    if len(values) < 2:
        return "missing", 0.0
    base = values[0]
    min_sim = 1.0
    for other in values[1:]:
        sim = _similarity(base, other)
        min_sim = min(min_sim, sim)
    if min_sim >= MATCH_THRESHOLD:
        return "matching", min_sim
    if min_sim >= PARTIAL_THRESHOLD:
        return "partial", min_sim
    return "mismatched", min_sim


def _evaluate_numeric_field(field: str, values: list[float]) -> str:
    if len(values) < 2:
        return "missing"
    base = values[0]
    for other in values[1:]:
        if abs(base - other) > NUMERIC_TOLERANCE.get(field, 0.0):
            return "mismatched"
    return "matching"


def _bucket(
    field: str, status: str,
    matching: list[str], partial: list[str],
    mismatched: list[str], missing: list[str],
) -> None:
    if status == "matching":
        matching.append(field)
    elif status == "partial":
        partial.append(field)
    elif status == "mismatched":
        mismatched.append(field)
    else:
        missing.append(field)


def compare_documents(ocr_rows: list[OCRData]) -> ComparisonResult:
    if len(ocr_rows) < 2:
        raise ValueError("Document comparison requires at least 2 documents with OCR data.")

    matching, partial, mismatched, missing = [], [], [], []
    details: dict = {}

    for field in TEXT_FIELDS:
        values = [getattr(row, field) for row in ocr_rows if getattr(row, field)]
        status, sim = _evaluate_text_field(values)
        details[field] = {"values": values, "status": status, "similarity": round(sim * 100)}
        _bucket(field, status, matching, partial, mismatched, missing)

    for field in NUMERIC_FIELDS:
        values = [getattr(row, field) for row in ocr_rows if getattr(row, field) is not None]
        status = _evaluate_numeric_field(field, values)
        details[field] = {"values": values, "status": status, "similarity": None}
        _bucket(field, status, matching, partial, mismatched, missing)

    # Derived: graduation year from date_of_issue
    years = [_extract_year(row.date_of_issue) for row in ocr_rows]
    years = [y for y in years if y]
    status, sim = _evaluate_text_field(years)
    details["graduation_year"] = {"values": years, "status": status, "similarity": round(sim * 100)}
    _bucket("graduation_year", status, matching, partial, mismatched, missing)

    # Score: matching=1, partial=0.5, mismatched=0
    total_comparable = len(matching) + len(partial) + len(mismatched)
    score_sum = len(matching) + 0.5 * len(partial)
    consistency_pct = round((score_sum / total_comparable) * 100, 2) if total_comparable else 0.0

    return ComparisonResult(matching, partial, mismatched, missing, consistency_pct, details)
