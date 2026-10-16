import io
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

print("=== DIAGNOSE TAMPERING SERVICE ===")

# 1.a Import checks
print("\n--- 1. Library Imports ---")
libraries = [
    ("cv2", "import cv2"),
    ("numpy", "import numpy as np"),
    ("PIL", "from PIL import Image, ImageChops, ImageEnhance"),
    ("scipy", "import scipy"),
    ("skimage", "import skimage"),
    ("fitz (PyMuPDF)", "import fitz"),
]

for name, imp_stmt in libraries:
    try:
        exec(imp_stmt)
        print(f"[{name}]: OK")
    except Exception as e:
        print(f"[{name}]: ERROR: {e}")

# 1.b Run real tampering function on:
# (1) sample_certificate.pdf
# (2) PNG of page 1 rendered at 200 dpi
print("\n--- 2. Tampering Function Execution ---")

from app.services.image_preprocessing import load_image_as_array, preprocess_pipeline
from app.services.tampering_detection import analyze_tampering, TamperingResult

pdf_path = os.path.join(os.path.dirname(__file__), "..", "..", "sample_certificate.pdf")
if not os.path.exists(pdf_path):
    pdf_path = "sample_certificate.pdf"

print(f"Checking PDF path: {pdf_path} (exists={os.path.exists(pdf_path)})")
with open(pdf_path, "rb") as f:
    pdf_bytes = f.read()

# Test 1: sample_certificate.pdf
print("\n--- Test (1): sample_certificate.pdf ---")
t0 = time.time()
try:
    pdf_image = load_image_as_array(pdf_bytes, "pdf")
    pdf_processed = preprocess_pipeline(pdf_image)
    pdf_result = analyze_tampering(pdf_bytes, "pdf", pdf_processed)
    elapsed_pdf = time.time() - t0
    print(f"Result on PDF (took {elapsed_pdf:.3f}s):")
    print(f"  Status: {pdf_result.status}")
    print(f"  Score: {pdf_result.score}")
    print(f"  Risk Level: {pdf_result.risk_level}")
    print(f"  Confidence: {pdf_result.confidence}")
    print(f"  Flags ({len(pdf_result.flags)}): {pdf_result.flags}")
    print(f"  Findings count: {len(pdf_result.findings)}")
    print(f"  Image Quality: {pdf_result.image_quality}")
    print(f"  ELA: {pdf_result.ela}")
    print(f"  Copy Paste: {pdf_result.copy_paste}")
    print(f"  Metadata: {pdf_result.metadata_detail}")
except Exception as e:
    elapsed_pdf = time.time() - t0
    import traceback
    print(f"FAILED on PDF after {elapsed_pdf:.3f}s: {e}")
    traceback.print_exc()

# Test 2: PNG of page 1 rendered at 200 dpi
print("\n--- Test (2): PNG of page 1 rendered at 200 dpi ---")
t0 = time.time()
try:
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    zoom = 200 / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    png_bytes = pix.tobytes("png")
    doc.close()

    png_image = load_image_as_array(png_bytes, "png")
    png_processed = preprocess_pipeline(png_image)
    png_result = analyze_tampering(png_bytes, "png", png_processed)
    elapsed_png = time.time() - t0
    print(f"Result on PNG (took {elapsed_png:.3f}s):")
    print(f"  Status: {png_result.status}")
    print(f"  Score: {png_result.score}")
    print(f"  Risk Level: {png_result.risk_level}")
    print(f"  Confidence: {png_result.confidence}")
    print(f"  Flags ({len(png_result.flags)}): {png_result.flags}")
    print(f"  Findings count: {len(png_result.findings)}")
    print(f"  Image Quality: {png_result.image_quality}")
    print(f"  ELA: {png_result.ela}")
    print(f"  Copy Paste: {png_result.copy_paste}")
    print(f"  Metadata: {png_result.metadata_detail}")
except Exception as e:
    elapsed_png = time.time() - t0
    import traceback
    print(f"FAILED on PNG after {elapsed_png:.3f}s: {e}")
    traceback.print_exc()
