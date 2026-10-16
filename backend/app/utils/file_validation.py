"""
Upload validation: extension whitelist, size limit, real magic-byte
MIME sniffing, structural PDF/image verification, and decompression bomb protection.
Never trust a client-supplied filename or Content-Type header alone.
"""
import io
import os
import re
from fastapi import UploadFile, HTTPException

from app.core.config import settings

FORBIDDEN_EXECUTABLE_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bat", ".cmd", ".sh", ".php",
    ".py", ".js", ".vbs", ".ps1", ".jar", ".war", ".cgi", ".pl", ".htpasswd"
}

MAGIC_BYTES = {
    "pdf": b"%PDF-",
    "jpeg": b"\xff\xd8\xff",
    "png": b"\x89PNG\r\n\x1a\n",
}

MAX_PDF_PAGES = 50
MAX_IMAGE_DIMENSION = 10000       # max 10,000 px width or height
MAX_IMAGE_PIXELS = 100_000_000    # max 100 megapixels (decompression bomb protection)


async def validate_certificate_file(file: UploadFile) -> None:
    filename = file.filename or ""

    # 1. Reject null bytes or path traversal in filename
    if "\x00" in filename or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename: Filename contains prohibited characters or path traversal sequences.",
        )

    # 2. Check for dangerous double extensions (e.g., sample.pdf.exe)
    parts = filename.lower().split(".")
    if len(parts) > 2:
        for p in parts[1:]:
            ext_check = f".{p}"
            if ext_check in FORBIDDEN_EXECUTABLE_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Security violation: Executable or script extension '{ext_check}' detected in filename.",
                )

    # 3. Validate primary extension against allowlist
    ext = os.path.splitext(filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. Allowed: {settings.ALLOWED_EXTENSIONS}",
        )

    # 4. Read byte contents for magic signature and size checks
    contents = await file.read()
    await file.seek(0)

    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_mb:.1f}MB). Max allowed is {settings.MAX_UPLOAD_MB}MB.",
        )

    # 5. Magic Byte Signature Verification & Mismatch Rejection
    detected_type = None
    if contents.startswith(MAGIC_BYTES["pdf"]):
        detected_type = "pdf"
    elif contents.startswith(MAGIC_BYTES["jpeg"]):
        detected_type = "jpeg"
    elif contents.startswith(MAGIC_BYTES["png"]):
        detected_type = "png"

    if detected_type is None:
        # Fallback check via python-magic if available
        try:
            import magic
            mime = magic.from_buffer(contents, mime=True)
            if mime == "application/pdf":
                detected_type = "pdf"
            elif mime == "image/jpeg":
                detected_type = "jpeg"
            elif mime == "image/png":
                detected_type = "png"
        except Exception:
            pass

    if detected_type is None:
        raise HTTPException(
            status_code=400,
            detail="File signature check failed: File header does not match any allowed format (PDF/JPEG/PNG).",
        )

    # 6. Reject Mismatched Extension vs Magic Signature
    expected_exts = {
        "pdf": [".pdf"],
        "jpeg": [".jpg", ".jpeg"],
        "png": [".png"],
    }
    if ext not in expected_exts[detected_type]:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext}' does not match actual file signature ('{detected_type}'). Upload rejected.",
        )

    # 7. PDF Structural & Page Count Validation
    if detected_type == "pdf":
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=contents, filetype="pdf")
            page_count = doc.page_count
            doc.close()
            if page_count > MAX_PDF_PAGES:
                raise HTTPException(
                    status_code=400,
                    detail=f"PDF page count ({page_count}) exceeds maximum allowed limit ({MAX_PDF_PAGES} pages).",
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Malformed or corrupted PDF document: {exc}",
            )

    # 8. Image Structural & Decompression Bomb Protection
    if detected_type in ("jpeg", "png"):
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(contents))
            w, h = img.size
            if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION or (w * h) > MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Image dimensions ({w}x{h}) exceed maximum safe processing limits (decompression bomb protection).",
                )
            img.verify()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Malformed or corrupted image file: {exc}",
            )

