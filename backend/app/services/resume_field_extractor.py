"""
RESUME FIELD EXTRACTOR
======================
Extracts all structured fields from cleaned Resume OCR text.
Returns null for any unextractable field. Never guesses values.

Output contract (spec Step 5):
{
    "document_type": "Resume",
    "confidence": 0-100,
    "fields": {
        "name": str | None,
        "email": str | None,
        "phone": str | None,
        "linkedin": str | None,
        "github": str | None,
        "address": str | None,
        "objective": str | None,
        "education": [{"degree":"","institution":"","year":"","cgpa":""}],
        "skills": {"technical":[], "soft":[], "tools":[]},
        "projects": [{"title":"","description":"","technologies":[]}],
        "internships": [{"company":"","duration":"","description":""}],
        "experience": [{"company":"","designation":"","duration":""}],
        "certifications": [],
        "achievements": [],
        "languages": []
    },
    "field_confidences": { field: 0.0-1.0 }
}

Steps 6, 7, 8 of the spec are implemented:
 - Step 6: Per-field confidence scores in field_confidences dict
 - Step 7: All detection events logged at INFO level
 - Step 8: Unextracted fields return None / [] — never guessed
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("certiverify.resume_field_extractor")


# ---------------------------------------------------------------------------
# Resume detection keywords (Step 4 of spec)
# ---------------------------------------------------------------------------

_RESUME_KEYWORDS: list[tuple[str, int]] = [
    ("curriculum vitae",    5),
    ("resume",              5),
    ("cv",                  4),
    ("career objective",    4),
    ("professional summary",4),
    ("profile",             3),
    ("objective",           3),
    ("projects",            3),
    ("internship",          3),
    ("certifications",      3),
    ("achievements",        3),
    ("github",              3),
    ("linkedin",            3),
    ("skills",              2),
    ("education",           2),
    ("experience",          2),
    ("languages",           2),
    ("email",               1),
    ("phone",               1),
    ("address",             1),
]

_MAX_RESUME_SCORE = sum(w for _, w in _RESUME_KEYWORDS)


def _compute_resume_confidence(text: str) -> int:
    """Return 0-100 resume document confidence based on keyword scoring."""
    text_l = text.lower()
    score = sum(w for kw, w in _RESUME_KEYWORDS if kw in text_l)
    matched = [kw for kw, _ in _RESUME_KEYWORDS if kw in text_l]
    logger.info("[Resume] Detected Resume using keywords: %s", matched)
    pct = min(100, int((score / _MAX_RESUME_SCORE) * 100))
    logger.info("[Resume] Detected Document Type: Resume (%d%%)", pct)
    return pct


# ---------------------------------------------------------------------------
# All known resume section headings
# ---------------------------------------------------------------------------

_ALL_HEADINGS = [
    "education", "academic background", "academic qualifications",
    "skills", "technical skills", "core competencies", "key skills",
    "experience", "work experience", "professional experience", "employment history",
    "projects", "project work", "academic projects", "personal projects",
    "internship", "internships", "training",
    "certifications", "certificates", "professional certifications",
    "achievements", "awards", "honors", "accomplishments",
    "languages", "language proficiency",
    "objective", "career objective", "professional objective",
    "profile", "summary", "professional summary", "about me",
    "address", "contact",
    "references",
    "hobbies", "interests",
    "publications", "research",
]

# Compile a single pattern that matches any heading at the start of a line
_HEADING_RE = re.compile(
    r"^(" + "|".join(re.escape(h) for h in sorted(_ALL_HEADINGS, key=len, reverse=True)) + r")\s*[:\-]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Section slicer (heading-boundary approach — more robust than DOTALL regex)
# ---------------------------------------------------------------------------

def _slice_sections(text: str) -> dict[str, str]:
    """
    Find all section headings in the document, then slice text between them.
    Returns {normalized_heading: section_body_text}.
    """
    sections: dict[str, str] = {}
    lines = text.splitlines()
    heading_positions = []  # [(line_index, normalized_heading)]

    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line.strip())
        if m:
            heading_positions.append((i, m.group(1).lower().strip()))

    if not heading_positions:
        logger.info("[Resume] No section headings found (flat document)")
        return {}

    logger.info("[Resume] Matched keywords / headings found: %s",
                [h for _, h in heading_positions])

    for idx, (start_line, heading) in enumerate(heading_positions):
        end_line = (heading_positions[idx + 1][0]
                    if idx + 1 < len(heading_positions) else len(lines))
        body = "\n".join(lines[start_line + 1: end_line]).strip()
        # Merge same-named sections (some resumes have repeated headings)
        if heading in sections:
            sections[heading] = sections[heading] + "\n" + body
        else:
            sections[heading] = body

    return sections


def _get_section(sections: dict, *heading_aliases: str) -> Optional[str]:
    """Return first non-empty section body matching any of the given heading aliases."""
    for alias in heading_aliases:
        body = sections.get(alias.lower(), "")
        if body.strip():
            return body.strip()
    return None


# ---------------------------------------------------------------------------
# Known skill categorisation lists
# ---------------------------------------------------------------------------

_TECH_SKILLS = {
    "python", "java", "c", "c++", "c#", "javascript", "typescript", "html", "css",
    "react", "angular", "vue", "node", "nodejs", "express", "django", "flask",
    "spring", "springboot", "sql", "mysql", "postgresql", "sqlite", "mongodb",
    "redis", "rest api", "graphql", "tensorflow", "pytorch", "keras", "scikit",
    "pandas", "numpy", "opencv", "machine learning", "deep learning", "nlp",
    "linux", "bash", "shell", "docker", "kubernetes", "aws", "azure", "gcp",
    "git", "github", "gitlab", "jenkins", "ci/cd", "terraform", "ansible",
    "r", "matlab", "scala", "swift", "kotlin", "flutter", "dart",
    "android", "ios", "php", "laravel", "ruby", "rails", "go", "rust",
    "solidity", "blockchain", "hadoop", "spark", "kafka", "elasticsearch",
    "excel", "tableau", "power bi", "sap", "autocad",
}

_SOFT_SKILLS = {
    "communication", "teamwork", "leadership", "problem solving", "problem-solving",
    "critical thinking", "time management", "adaptability", "creativity",
    "collaboration", "interpersonal", "analytical", "decision making",
    "presentation", "negotiation", "conflict resolution", "project management",
    "multitasking", "attention to detail", "self-motivated", "flexible",
}

_TOOLS_KEYWORDS = {
    "vs code", "vscode", "intellij", "pycharm", "eclipse", "android studio",
    "figma", "canva", "photoshop", "illustrator", "xcode", "postman",
    "jira", "trello", "notion", "slack", "jupyter", "colab",
    "latex", "word", "powerpoint",
}


def _categorise_skills(section_text: str) -> dict:
    """Split skills section into technical, soft, and tools lists."""
    # Extract individual skill tokens from comma/newline/bullet-separated text
    raw_items = re.split(r"[,\n•\-|/]", section_text)
    raw_items = [item.strip().rstrip(".,;") for item in raw_items if item.strip()]

    technical, soft, tools = [], [], []
    text_l = section_text.lower()

    for item in raw_items:
        if not item or len(item) < 2:
            continue
        item_l = item.lower()
        if item_l in _TOOLS_KEYWORDS or any(t in item_l for t in _TOOLS_KEYWORDS):
            tools.append(item)
        elif item_l in _TECH_SKILLS or any(t in item_l for t in _TECH_SKILLS):
            technical.append(item)
        elif item_l in _SOFT_SKILLS or any(s in item_l for s in _SOFT_SKILLS):
            soft.append(item)
        else:
            # Default uncategorised items to technical (most likely)
            technical.append(item)

    logger.info("[Resume] Skills extracted | technical=%d soft=%d tools=%d",
                len(technical), len(soft), len(tools))
    return {"technical": technical, "soft": soft, "tools": tools}


# ---------------------------------------------------------------------------
# Individual field extractors
# ---------------------------------------------------------------------------

def _extract_name(text: str) -> tuple[Optional[str], float]:
    """
    Extract candidate name from top 10 lines.
    Accepts:
    - Title Case: "Keerthana Karthikeyan"
    - ALL CAPS: "KEERTHANA K"
    - With initials: "K. Anitha"
    Skips email, phone, URL, and known heading lines.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    _SKIP_RE = re.compile(
        r"(@|http|www\.|github|linkedin|phone|email|mobile|address"
        r"|resume|curriculum|cv\b|objective|profile|summary|\d{6,})",
        re.IGNORECASE
    )

    def is_valid_name(ln: str) -> bool:
        if not ln or len(ln) < 3 or len(ln) > 60:
            return False
        if _SKIP_RE.search(ln):
            return False
        if re.search(r"\d", ln):
            return False
        # Title Case (at least 2 words)
        if re.match(r"^[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,5}$", ln):
            return True
        # ALL CAPS (at least 2 parts)
        if re.match(r"^[A-Z][A-Z\s.'-]{2,}[A-Z]$", ln) and len(ln.split()) >= 2:
            return True
        # With initials: "K. Anitha" or "Anitha K."
        if re.match(r"^[A-Z]\.\s+[A-Z][a-z]+|^[A-Z][a-z]+\s+[A-Z]\.$", ln):
            return True
        return False

    for ln in lines[:10]:
        if is_valid_name(ln):
            logger.info("[Resume] Name extracted: %s", ln)
            return ln, 0.92

    logger.info("[Resume] Name: not found")
    return None, 0.0


def _extract_email(text: str) -> tuple[Optional[str], float]:
    """RFC-compliant email regex with OCR artifact repair already done by engine."""
    m = re.search(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        text
    )
    if m:
        logger.info("[Resume] Email extracted: %s", m.group(0))
        return m.group(0).strip(), 0.98
    logger.info("[Resume] Email: not found")
    return None, 0.0


def _extract_phone(text: str) -> tuple[Optional[str], float]:
    """Indian mobile number: optional +91 prefix + 10 digits starting 6-9."""
    m = re.search(
        r"(?:\+91[\s\-]?|0)?([6-9]\d{9})\b",
        text
    )
    if m:
        phone = m.group(0).strip()
        logger.info("[Resume] Phone extracted: %s", phone)
        return phone, 0.96
    logger.info("[Resume] Phone: not found")
    return None, 0.0


def _extract_linkedin(text: str) -> tuple[Optional[str], float]:
    """Extract LinkedIn profile URL."""
    m = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-._~]+", text, re.IGNORECASE)
    if m:
        logger.info("[Resume] LinkedIn extracted: %s", m.group(0))
        return m.group(0).strip(), 0.97
    logger.info("[Resume] LinkedIn: not found")
    return None, 0.0


def _extract_github(text: str) -> tuple[Optional[str], float]:
    """Extract GitHub profile URL."""
    m = re.search(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9\-._~]+", text, re.IGNORECASE)
    if m:
        logger.info("[Resume] GitHub extracted: %s", m.group(0))
        return m.group(0).strip(), 0.97
    logger.info("[Resume] GitHub: not found")
    return None, 0.0


def _extract_address(text: str, sections: dict) -> tuple[Optional[str], float]:
    """Extract address from address section or labeled line."""
    body = _get_section(sections, "address", "contact")
    if body:
        addr = re.sub(r"\s+", " ", body.splitlines()[0]).strip()
        if len(addr) > 5:
            logger.info("[Resume] Address extracted (section): %s", addr)
            return addr, 0.85

    m = re.search(
        r"(?:address|location)\s*[:\-]?\s*(.{5,100})",
        text, re.IGNORECASE
    )
    if m:
        addr = m.group(1).strip()
        logger.info("[Resume] Address extracted (inline label): %s", addr)
        return addr, 0.80

    logger.info("[Resume] Address: not found")
    return None, 0.0


def _extract_objective(sections: dict) -> tuple[Optional[str], float]:
    """Extract career objective / profile summary."""
    body = _get_section(
        sections,
        "objective", "career objective", "professional objective",
        "profile", "summary", "professional summary", "about me"
    )
    if body:
        obj = re.sub(r"\s+", " ", body).strip()
        if len(obj) > 10:
            logger.info("[Resume] Objective extracted | len=%d", len(obj))
            return obj, 0.88
    logger.info("[Resume] Objective: not found")
    return None, 0.0


def _extract_education(sections: dict) -> tuple[list, float]:
    """
    Extract education as structured list: [{degree, institution, year, cgpa}].
    Each block typically has:
      - Degree name (B.E, B.Tech, M.Sc, etc.)
      - Institution name
      - Year (4-digit or range)
      - CGPA / Percentage
    """
    body = _get_section(sections, "education", "academic background", "academic qualifications")
    if not body:
        logger.info("[Resume] Education: not found")
        return [], 0.0

    entries = []
    # Split on blank lines or lines starting with degree keywords
    blocks = re.split(r"\n{2,}|\n(?=[A-Z])", body)

    _DEGREE_RE = re.compile(
        r"\b(?:B\.?E|B\.?Tech|B\.?Sc|B\.?C(?:om|A)|B\.?A|BBA|BCA"
        r"|M\.?E|M\.?Tech|M\.?Sc|M\.?C(?:om|A)|MBA|MCA|MA|MS"
        r"|PhD|Ph\.?D|Diploma|HSC|SSLC|10th|12th|Secondary|Higher\s+Secondary"
        r"|Bachelor|Master|Doctor)\b",
        re.IGNORECASE
    )
    _YEAR_RE = re.compile(r"\b((?:19|20)\d{2}(?:\s*[-\u2013]\s*(?:(?:19|20)\d{2}|present))?)\b",
                          re.IGNORECASE)
    _CGPA_RE = re.compile(
        r"(?:cgpa|gpa|grade\s*point)[:\s]*([0-9]{1}\.[0-9]{1,2})"
        r"|([0-9]{2,3}(?:\.[0-9]{1,2})?)\s*%",
        re.IGNORECASE
    )

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()

        degree_found = _DEGREE_RE.search(block)
        year_found = _YEAR_RE.search(block)
        cgpa_found = _CGPA_RE.search(block)

        degree = degree_found.group(0) if degree_found else None
        year = year_found.group(0).strip() if year_found else None
        cgpa_m = cgpa_found
        cgpa = None
        if cgpa_m:
            cgpa = cgpa_m.group(1) or cgpa_m.group(2)

        # Institution: longest line that doesn't look like a degree or year
        institution = None
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            if _DEGREE_RE.search(ln) and len(ln) < 30:
                continue
            if _YEAR_RE.search(ln) and len(ln) < 15:
                continue
            if len(ln) > 5 and not re.match(r"^\d+$", ln):
                institution = ln
                break

        if degree or institution:
            entries.append({
                "degree":      degree,
                "institution": institution,
                "year":        year,
                "cgpa":        cgpa,
            })

    logger.info("[Resume] Education extracted: %d entries", len(entries))
    return entries, 0.85 if entries else 0.0


def _extract_projects(sections: dict) -> tuple[list, float]:
    """
    Extract projects as structured list: [{title, description, technologies}].
    Each project block: title line -> description lines -> tech stack.
    """
    body = _get_section(sections, "projects", "project work", "academic projects", "personal projects")
    if not body:
        logger.info("[Resume] Projects: not found")
        return [], 0.0

    entries = []
    # Split into blocks (blank line or numbered bullet: "1.", "2." or "-" at start)
    blocks = re.split(r"\n{2,}|\n(?=\d+\.\s|\*\s|-\s[A-Z])", body)

    _TECH_RE = re.compile(
        r"(?:tech(?:nologies|nology)?|stack|built\s+with|tools?\s+used?|using)\s*[:\-]?\s*(.{5,200})",
        re.IGNORECASE
    )

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 10:
            continue
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        title = re.sub(r"^[\d*•\-\.\)]+\s*", "", lines[0]).strip()
        desc_lines = lines[1:] if len(lines) > 1 else []

        # Extract tech from explicit tech line
        tech_match = _TECH_RE.search(block)
        technologies = []
        if tech_match:
            raw_tech = tech_match.group(1)
            technologies = [t.strip() for t in re.split(r"[,/|]", raw_tech) if t.strip()]
            # Remove the tech line from description
            desc_lines = [ln for ln in desc_lines
                          if not _TECH_RE.search(ln)]

        description = " ".join(desc_lines).strip() if desc_lines else None

        if title:
            entries.append({
                "title":        title,
                "description":  description,
                "technologies": technologies,
            })

    logger.info("[Resume] Projects extracted: %d entries", len(entries))
    return entries, 0.82 if entries else 0.0


def _extract_internships(sections: dict) -> tuple[list, float]:
    """Extract internships: [{company, duration, description}]."""
    body = _get_section(sections, "internship", "internships", "training")
    if not body:
        logger.info("[Resume] Internships: not found")
        return [], 0.0

    _DUR_RE = re.compile(
        r"(\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
        r"[\s,]*(?:20\d{2})?[\s\-\u2013to]+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
        r"[a-z]*[\s,]*(?:20\d{2})?|\d+\s*(?:months?|weeks?))",
        re.IGNORECASE
    )

    entries = []
    blocks = re.split(r"\n{2,}|\n(?=[A-Z])", body)
    for block in blocks:
        block = block.strip()
        if not block or len(block) < 5:
            continue
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]

        company = lines[0] if lines else None
        dur_m = _DUR_RE.search(block)
        duration = dur_m.group(0).strip() if dur_m else None
        desc_lines = [ln for ln in lines[1:] if not (dur_m and dur_m.group(0) in ln)]
        description = " ".join(desc_lines).strip() if desc_lines else None

        if company:
            entries.append({"company": company, "duration": duration, "description": description})

    logger.info("[Resume] Internships extracted: %d entries", len(entries))
    return entries, 0.82 if entries else 0.0


def _extract_experience(sections: dict) -> tuple[list, float]:
    """Extract experience: [{company, designation, duration}]."""
    body = _get_section(
        sections,
        "experience", "work experience", "professional experience", "employment history"
    )
    if not body:
        logger.info("[Resume] Experience: not found")
        return [], 0.0

    _DUR_RE = re.compile(
        r"(\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
        r"[\s,]*(?:20\d{2})?[\s\-\u2013to]+(?:jan|feb|mar|apr|may|jun|jul|aug|sep"
        r"|oct|nov|dec|present)[a-z]*[\s,]*(?:20\d{2})?|\d+\s*(?:months?|years?))",
        re.IGNORECASE
    )
    _DESIG_RE = re.compile(
        r"\b(?:engineer|developer|analyst|manager|intern|designer|architect"
        r"|consultant|lead|associate|executive|officer|head|director|scientist"
        r"|researcher|specialist)\b",
        re.IGNORECASE
    )

    entries = []
    blocks = re.split(r"\n{2,}|\n(?=[A-Z])", body)
    for block in blocks:
        block = block.strip()
        if not block or len(block) < 5:
            continue
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]

        company = lines[0] if lines else None
        dur_m = _DUR_RE.search(block)
        duration = dur_m.group(0).strip() if dur_m else None
        desig_m = _DESIG_RE.search(block)
        designation = None
        if desig_m:
            # Grab the full line that contains the designation keyword
            for ln in lines[1:]:
                if _DESIG_RE.search(ln):
                    designation = ln.strip()
                    break

        if company:
            entries.append({"company": company, "designation": designation, "duration": duration})

    logger.info("[Resume] Experience extracted: %d entries", len(entries))
    return entries, 0.82 if entries else 0.0


def _extract_list_section(sections: dict, *aliases: str) -> tuple[list, float]:
    """Generic extractor for list sections (certifications, achievements, languages)."""
    body = _get_section(sections, *aliases)
    if not body:
        return [], 0.0
    items = [
        re.sub(r"^[•\-\*\d.]+\s*", "", ln).strip()
        for ln in body.splitlines()
        if ln.strip() and len(ln.strip()) > 1
    ]
    items = [i for i in items if i]
    logger.info("[Resume] %s extracted: %d items", aliases[0], len(items))
    return items, 0.85 if items else 0.0


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def extract_resume_fields(raw_text: str) -> dict:
    """
    Extract all structured Resume fields from OCR text.

    Parameters
    ----------
    raw_text : Cleaned merged OCR text from ResumeOCRResult.raw_text

    Returns
    -------
    dict with keys: document_type, confidence, fields, field_confidences
    """
    logger.info("[Resume] === Field Extraction START ===")

    # Resume document confidence
    doc_confidence = _compute_resume_confidence(raw_text)

    # Parse all sections first (heading-boundary approach)
    sections = _slice_sections(raw_text)

    # Extract each field
    name,       name_conf    = _extract_name(raw_text)
    email,      email_conf   = _extract_email(raw_text)
    phone,      phone_conf   = _extract_phone(raw_text)
    linkedin,   li_conf      = _extract_linkedin(raw_text)
    github,     gh_conf      = _extract_github(raw_text)
    address,    addr_conf    = _extract_address(raw_text, sections)
    objective,  obj_conf     = _extract_objective(sections)
    education,  edu_conf     = _extract_education(sections)
    projects,   proj_conf    = _extract_projects(sections)
    internships,int_conf     = _extract_internships(sections)
    experience, exp_conf     = _extract_experience(sections)
    certifications, cert_conf = _extract_list_section(
        sections, "certifications", "certificates", "professional certifications"
    )
    achievements, ach_conf   = _extract_list_section(
        sections, "achievements", "awards", "honors", "accomplishments"
    )
    languages,  lang_conf    = _extract_list_section(
        sections, "languages", "language proficiency"
    )

    # Skills: categorised
    skills_body = _get_section(
        sections, "skills", "technical skills", "core competencies", "key skills"
    )
    skills_data = _categorise_skills(skills_body) if skills_body else {"technical": [], "soft": [], "tools": []}
    skills_conf = 0.85 if any(skills_data[k] for k in skills_data) else 0.0

    fields = {
        "name":           name,
        "email":          email,
        "phone":          phone,
        "linkedin":       linkedin,
        "github":         github,
        "address":        address,
        "objective":      objective,
        "education":      education,
        "skills":         skills_data,
        "projects":       projects,
        "internships":    internships,
        "experience":     experience,
        "certifications": certifications,
        "achievements":   achievements,
        "languages":      languages,
    }

    field_confidences = {
        "name":           name_conf,
        "email":          email_conf,
        "phone":          phone_conf,
        "linkedin":       li_conf,
        "github":         gh_conf,
        "address":        addr_conf,
        "objective":      obj_conf,
        "education":      edu_conf,
        "skills":         skills_conf,
        "projects":       proj_conf,
        "internships":    int_conf,
        "experience":     exp_conf,
        "certifications": cert_conf,
        "achievements":   ach_conf,
        "languages":      lang_conf,
    }

    # Step 7 logging
    extracted = {k for k, v in fields.items()
                 if v is not None and v != [] and v != {"technical": [], "soft": [], "tools": []}}
    missing = [k for k in fields if k not in extracted]
    logger.info("[Resume] Extracted Fields: %s", sorted(extracted))
    logger.info("[Resume] Missing Fields: %s", missing)

    result = {
        "document_type": "Resume",
        "confidence":    doc_confidence,
        "fields":        fields,
        "field_confidences": field_confidences,
    }

    logger.info("[Resume] === Field Extraction COMPLETE | confidence=%d%% ===", doc_confidence)
    return result
