import os
import sys
import time
import shutil
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def main():
    print("=== OCR DIAGNOSTIC SCRIPT ===")
    
    # -------------------------------------------------------------
    # a. Import easyocr, torch, torchvision, cv2, fitz, pytesseract
    # -------------------------------------------------------------
    print("\n--- a. Module Imports ---")
    modules = ["easyocr", "torch", "torchvision", "cv2", "fitz", "pytesseract"]
    imported_modules = {}
    for mod_name in modules:
        try:
            mod = __import__(mod_name)
            imported_modules[mod_name] = mod
            print(f"import {mod_name}: OK (version: {getattr(mod, '__version__', 'unknown')})")
        except Exception as e:
            imported_modules[mod_name] = None
            print(f"import {mod_name}: ERROR: {type(e).__name__}: {e}")

    # -------------------------------------------------------------
    # b. Whether Tesseract executable is found
    # -------------------------------------------------------------
    print("\n--- b. Tesseract Executable ---")
    pytesseract_mod = imported_modules.get("pytesseract")
    tess_path = shutil.which("tesseract")
    
    # Common Windows default installation paths
    windows_default_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    if not tess_path:
        for p in windows_default_paths:
            if os.path.exists(p):
                tess_path = p
                break

    if pytesseract_mod is not None:
        if tess_path:
            pytesseract_mod.pytesseract.tesseract_cmd = tess_path
        try:
            ver = pytesseract_mod.get_tesseract_version()
            print(f"Tesseract executable: OK (path: {pytesseract_mod.pytesseract.tesseract_cmd}, version: {ver})")
        except Exception as e:
            print(f"Tesseract executable: ERROR: {type(e).__name__}: {e} (which tesseract: {tess_path})")
    else:
        if tess_path:
            print(f"Tesseract executable: Found binary at {tess_path}, but pytesseract is not imported.")
        else:
            print("Tesseract executable: ERROR: tesseract not found on PATH and pytesseract not installed.")

    # -------------------------------------------------------------
    # c. Whether easyocr.Reader loads for ['en'] and for ['ta','en']
    # -------------------------------------------------------------
    print("\n--- c. EasyOCR Reader Loading ---")
    easyocr_mod = imported_modules.get("easyocr")
    if easyocr_mod is None:
        print("easyocr.Reader(['en']): ERROR: easyocr is not installed")
        print("easyocr.Reader(['ta', 'en']): ERROR: easyocr is not installed")
    else:
        # Test ['en']
        t0 = time.time()
        try:
            reader_en = easyocr_mod.Reader(["en"], gpu=False, verbose=False)
            print(f"easyocr.Reader(['en']): OK (loaded in {time.time() - t0:.2f}s)")
        except Exception as e:
            print(f"easyocr.Reader(['en']): ERROR: {type(e).__name__}: {e}")

        # Test ['ta', 'en']
        t0 = time.time()
        try:
            reader_ta_en = easyocr_mod.Reader(["ta", "en"], gpu=False, verbose=False)
            print(f"easyocr.Reader(['ta', 'en']): OK (loaded in {time.time() - t0:.2f}s)")
        except Exception as e:
            print(f"easyocr.Reader(['ta', 'en']): ERROR: {type(e).__name__}: {e}")

    # -------------------------------------------------------------
    # d. Render page 1 of sample_certificate.pdf to image-only PDF,
    #    run app/services/ocr_engine.py OCR, print first 300 chars & time
    # -------------------------------------------------------------
    print("\n--- d. Image-Only PDF OCR Execution ---")
    fitz_mod = imported_modules.get("fitz")
    if fitz_mod is None:
        print("Cannot render PDF because fitz (PyMuPDF) is not imported.")
        return

    # Find sample_certificate.pdf
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "sample_certificate.pdf"),
        os.path.join(os.path.dirname(__file__), "..", "sample_certificate.pdf"),
        "sample_certificate.pdf",
    ]
    sample_pdf = None
    for p in possible_paths:
        if os.path.exists(p):
            sample_pdf = os.path.abspath(p)
            break

    if not sample_pdf:
        print("ERROR: sample_certificate.pdf not found.")
        return

    print(f"Using sample PDF: {sample_pdf}")
    try:
        doc = fitz_mod.open(sample_pdf)
        page = doc[0]
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        doc.close()

        # Build an image-only PDF with NO text layer
        image_pdf = fitz_mod.open()
        img_page = image_pdf.new_page(width=pix.width, height=pix.height)
        img_page.insert_image(img_page.rect, stream=img_bytes)
        image_pdf_bytes = image_pdf.tobytes()
        image_pdf.close()
        print(f"Created image-only PDF ({len(image_pdf_bytes)} bytes, {pix.width}x{pix.height})")

        # Now run the API OCR extraction pipeline
        from app.services.image_preprocessing import load_image_as_array, preprocess_for_ocr
        from app.services.ocr_engine import extract_text_and_bboxes_fused

        t_ocr_start = time.time()
        raw_image = load_image_as_array(image_pdf_bytes, "pdf")
        color_processed, binary_gray = preprocess_for_ocr(raw_image, is_digital=True)
        ocr_result, bboxes = extract_text_and_bboxes_fused(color_processed, binary_gray)
        elapsed_time = time.time() - t_ocr_start

        raw_text = ocr_result.raw_text
        print(f"OCR Execution Time: {elapsed_time:.2f}s")
        print(f"Engines Used: {ocr_result.engines_used}")
        print(f"Accuracy: {ocr_result.accuracy}")
        print(f"Total Text Length: {len(raw_text)}")
        print("\nFirst 300 characters of OCR text:")
        print("-" * 50)
        print(repr(raw_text[:300]))
        print("-" * 50)
        print(raw_text[:300])

    except Exception as e:
        elapsed_time = time.time() - t_ocr_start if 't_ocr_start' in locals() else 0.0
        print(f"OCR Execution FAILED in {elapsed_time:.2f}s with error: {type(e).__name__}: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
