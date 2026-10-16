"""
OCR TEXT CLEANER — shared normalization service
================================================

Sits between OCR extraction and document classification / field extraction
in the main pipeline:

    OCR Extraction (raw_text)
           ↓
    clean_ocr_text()   ← THIS MODULE
           ↓
    Document Classifier
           ↓
    Document-Specific Field Extraction

Design goals
------------
1. Preserve semantic content  — names, numbers, dates must survive unchanged.
2. Remove OCR noise           — stray symbols, repeated punctuation, garbled chars.
3. Fix common OCR artifacts   — broken hyphens, mis-read email characters.
4. Normalize whitespace       — excess spaces/blank lines slow down regex matching.
5. Unicode normalization      — NFKC collapses ligatures (ﬁ→fi) and half-width chars.
6. Keep structure             — newlines are preserved so section-based extractors work.

The private `_clean_ocr_text()` functions in aadhaar_ocr_engine,
marksheet_ocr_engine, and resume_ocr_engine are NOT replaced — they may
contain document-specific logic and are internal to those specialist engines.
This module is for the main OCR pipeline only.
"""
from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger("certiverify.ocr_text_cleaner")

# ---------------------------------------------------------------------------
# Compiled patterns  (module-level for zero re-compilation cost per request)
# ---------------------------------------------------------------------------

# Characters that are almost always OCR noise in certificate / ID documents.
# We keep: letters, digits, common punctuation (.,:-/'), newlines, spaces.
# We strip: stray pipes, backslashes, carets, tilde, backtick, bell, zero-width.
_NOISE_CHARS = re.compile(
    r"["
    r"\|"          # pipe   — OCR reads table borders as |
    r"\\"          # backslash
    r"\^"          # caret
    r"~"           # tilde
    r"`"           # backtick
    r"©®™°"        # copyright / trademark / degree (non-content)
    r"•·§¶†‡"      # bullets / section marks
    r"\x00-\x08"   # control chars (NULL … BS)
    r"\x0b\x0c"    # vertical tab, form feed
    r"\x0e-\x1f"   # other control chars
    r"\x7f"        # DEL
    r"\u200b-\u200f"  # zero-width spaces, LTR/RTL marks
    r"\ufeff"      # BOM
    r"]"
)

# Repeated punctuation that forms divider lines: ----, ====, ...., ~~~~
_REPEATED_PUNCT = re.compile(r"[.\-_=~+*#]{3,}")

# Runs of 3+ blank lines → collapse to 2 (preserve paragraph structure)
_MULTI_BLANK = re.compile(r"\n{3,}")

# Repeated spaces → single space (done per-line after noise removal)
_MULTI_SPACE = re.compile(r" {2,}")

# ---------------------------------------------------------------------------
# OCR artifact fixes (applied to the full text before line-by-line cleaning)
# ---------------------------------------------------------------------------

_ARTIFACT_FIXES: list[tuple[re.Pattern, str]] = [
    # Email address repairs: (a) / [at] / [dot] are common OCR misreads
    (re.compile(r"\(a\)",     re.IGNORECASE), "@"),
    (re.compile(r"\[at\]",   re.IGNORECASE), "@"),
    (re.compile(r"\s+@\s+"),                 "@"),
    (re.compile(r"\[dot\]",  re.IGNORECASE), "."),
    (re.compile(r"\(dot\)",  re.IGNORECASE), "."),
    # Hyphenated words broken across lines: "certifi-\ncate" → "certificate"
    (re.compile(r"(\w)-\n(\w)"),             r"\1\2"),
    # Stray colon after noise removal
    (re.compile(r"\s+:\s+"),                 ": "),
    # Fix "0" misread as "O" in known numeric contexts (e.g. "2O24" → "2024")
    # Only in 4-digit year-like patterns to avoid over-correcting names
    (re.compile(r"\b(19|2O|20)(\d)(O|\d)(\d)\b"), lambda m: m.group(0).replace("O", "0")),
    # Fix "l" misread as "1" at the start of a register/roll number value.
    # Matches "Reg No : l23456" → "Reg No : 123456"
    # Two-group capture avoids variable-width lookbehind (not in Python re).
    (re.compile(r"(reg(?:ister)?\s*no\.?\s*:?\s*)l(\d{4,})", re.IGNORECASE), r"\g<1>1\2"),
]

# Lines that are pure noise (single non-alphanumeric character, or only
# repeated punctuation after cleaning) are dropped entirely.
_PURE_NOISE_LINE = re.compile(r"^[^a-zA-Z0-9]{0,2}$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_ocr_text(raw: str) -> str:
    """
    Clean and normalize raw OCR text for downstream field extraction.

    Operations (in order):
    1. Unicode NFKC normalization  — collapses ligatures, half-width chars
    2. OCR artifact fixes          — email symbols, broken hyphens, year "O→0"
    3. Noise character removal     — stray pipes, control chars, symbols
    4. Per-line cleanup:
       a. Repeated punctuation collapsed
       b. Multiple spaces collapsed
       c. Pure-noise lines dropped (≤2 non-alphanumeric chars)
    5. Collapse 3+ blank lines → 2

    Returns
    -------
    str
        Cleaned text with structure (newlines) preserved.
    """
    if not raw or not raw.strip():
        return raw

    t_len_before = len(raw)

    # 1. Unicode NFKC — collapses ligatures (ﬁ→fi), full-width (Ａ→A), etc.
    text = unicodedata.normalize("NFKC", raw)

    # 2. OCR artifact fixes (whole-text patterns)
    for pattern, replacement in _ARTIFACT_FIXES:
        if callable(replacement):
            text = pattern.sub(replacement, text)  # type: ignore[arg-type]
        else:
            text = pattern.sub(replacement, text)

    # 3. Noise character removal (whole text, preserving newlines)
    text = _NOISE_CHARS.sub(" ", text)

    # 4. Per-line cleanup
    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        # 4a. Repeated punctuation → single space
        line = _REPEATED_PUNCT.sub(" ", line)
        # 4b. Multiple spaces → single space
        line = _MULTI_SPACE.sub(" ", line).strip()
        # 4c. Drop pure-noise lines (e.g. "|", "~", "  ", "-")
        if _PURE_NOISE_LINE.match(line):
            continue
        cleaned.append(line)

    # 5. Collapse 3+ blank lines → 2
    text = "\n".join(cleaned)
    text = _MULTI_BLANK.sub("\n\n", text)
    text = text.strip()

    logger.debug(
        "OCR text cleaned | chars before=%d | chars after=%d | removed=%d",
        t_len_before, len(text), t_len_before - len(text),
    )
    return text


def clean_ocr_text_lowercase(raw: str) -> str:
    """
    Convenience wrapper: clean + lowercase.
    Used by the document classifier which always works case-insensitively.
    """
    return clean_ocr_text(raw).lower()


# ---------------------------------------------------------------------------
# Enhanced normalization (new — does NOT modify clean_ocr_text)
# ---------------------------------------------------------------------------

# Common OCR character confusions in specific contexts
_OCR_CHAR_FIXES: list[tuple[re.Pattern, str]] = [
    # "rn" misread as "m" in common words — only fix obvious ones
    (re.compile(r"\bgovem(?=ment)", re.IGNORECASE), "govern"),
    (re.compile(r"\bexarni(?=nation)", re.IGNORECASE), "exami"),
    # "cl" misread as "d" — "dertificate" → "certificate"
    (re.compile(r"\bdertificate\b", re.IGNORECASE), "certificate"),
    # "ll" misread as "U" — "coUege" → "college"
    (re.compile(r"\bcoUege\b", re.IGNORECASE), "college"),
    # Common word fixes
    (re.compile(r"\bexarnination\b", re.IGNORECASE), "examination"),
    (re.compile(r"\bsecondaiy\b", re.IGNORECASE), "secondary"),
    (re.compile(r"\buniverslty\b", re.IGNORECASE), "university"),
    (re.compile(r"\bpermanent\s+register\s+nurnber\b", re.IGNORECASE), "permanent register number"),
    (re.compile(r"\bregistar\b", re.IGNORECASE), "registrar"),
    (re.compile(r"\bcertifioate\b", re.IGNORECASE), "certificate"),
]

# Broken line reconstruction: words split across lines
_BROKEN_LINE = re.compile(r"(\w{2,})-\s*\n\s*([a-z])")


def normalize_ocr_text(raw: str) -> dict[str, str]:
    """
    Produce both raw_text and normalized_text from OCR output.

    The raw text is cleaned (noise removed, whitespace normalized) but
    character values are preserved. The normalized text additionally
    applies OCR character corrections and broken-line reconstruction.

    Returns
    -------
    dict with keys:
        "raw_text"        : cleaned but character-faithful text
        "normalized_text" : cleaned + OCR corrections applied
    """
    if not raw or not raw.strip():
        return {"raw_text": raw or "", "normalized_text": raw or ""}

    # Step 1: Basic cleaning (same as clean_ocr_text)
    cleaned = clean_ocr_text(raw)

    # Step 2: Additional normalization for the normalized copy
    normalized = cleaned

    # 2a. Broken-line reconstruction: "certifi-\ncate" → "certificate"
    normalized = _BROKEN_LINE.sub(r"\1\2", normalized)

    # 2b. Common OCR character corrections
    for pattern, replacement in _OCR_CHAR_FIXES:
        normalized = pattern.sub(replacement, normalized)

    # 2c. Collapse duplicate consecutive lines (OCR sometimes reads same line twice)
    norm_lines = normalized.splitlines()
    deduped: list[str] = []
    for line in norm_lines:
        stripped = line.strip()
        if deduped and stripped and stripped == deduped[-1].strip():
            continue  # Skip exact duplicate of previous line
        deduped.append(line)
    normalized = "\n".join(deduped)

    logger.debug(
        "normalize_ocr_text | raw_len=%d cleaned_len=%d normalized_len=%d",
        len(raw), len(cleaned), len(normalized),
    )

    return {"raw_text": cleaned, "normalized_text": normalized}
