"""
Diagnosis script for QR verification subsystem.
Checks imports, tests QR detection on sample_certificate.pdf across multiple DPIs,
and tests end-to-end QR detection and verification on a generated test PDF.
"""
import os
import sys
import io
import traceback

# Ensure backend root is on sys.path
backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

print("=" * 60)
print("1. CHECKING IMPORTS")
print("=" * 60)

modules = ["cv2", "pyzbar.pyzbar", "fitz", "qrcode"]
imported_modules = {}

for mod in modules:
    try:
        if mod == "pyzbar.pyzbar":
            from pyzbar import pyzbar
            imported_modules[mod] = pyzbar
        elif mod == "cv2":
            import cv2
            imported_modules[mod] = cv2
        elif mod == "fitz":
            import fitz
            imported_modules[mod] = fitz
        elif mod == "qrcode":
            import qrcode
            imported_modules[mod] = qrcode
        print(f"[{mod}]: OK")
    except Exception as e:
        imported_modules[mod] = None
        print(f"[{mod}]: ERROR - {type(e).__name__}: {e}")

print("\n" + "=" * 60)
print("2. TESTING SAMPLE_CERTIFICATE.PDF AT 150, 200, 300 DPI")
print("=" * 60)

# Locate sample_certificate.pdf
candidate_paths = [
    os.path.abspath(os.path.join(backend_root, "..", "sample_certificate.pdf")),
    os.path.abspath(os.path.join(backend_root, "sample_certificate.pdf")),
    os.path.abspath("sample_certificate.pdf"),
]
sample_pdf_path = None
for p in candidate_paths:
    if os.path.exists(p):
        sample_pdf_path = p
        break

if not sample_pdf_path:
    print("ERROR: sample_certificate.pdf not found in candidate paths:", candidate_paths)
else:
    print(f"Found sample certificate at: {sample_pdf_path}")
    fitz_mod = imported_modules.get("fitz")
    cv2_mod = imported_modules.get("cv2")
    pyzbar_mod = imported_modules.get("pyzbar.pyzbar")

    if not fitz_mod or not cv2_mod:
        print("Cannot render pages: fitz or cv2 missing.")
    else:
        import numpy as np
        doc = fitz_mod.open(sample_pdf_path)
        page1 = doc[0]

        for dpi in [150, 200, 300]:
            zoom = dpi / 72.0
            mat = fitz_mod.Matrix(zoom, zoom)
            pix = page1.get_pixmap(matrix=mat)

            # Convert pixmap to OpenCV image
            if pix.n == 4:
                img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 4)
                gray = cv2_mod.cvtColor(img_data, cv2_mod.COLOR_RGBA2GRAY)
            elif pix.n == 3:
                img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                gray = cv2_mod.cvtColor(img_data, cv2_mod.COLOR_RGB2GRAY)
            else:
                gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)

            # Test cv2.QRCodeDetector
            cv2_text = None
            try:
                detector = cv2_mod.QRCodeDetector()
                data, _, _ = detector.detectAndDecode(gray)
                if data and data.strip():
                    cv2_text = data.strip()
            except Exception as e:
                cv2_text = f"Error: {e}"

            # Test pyzbar
            pyzbar_text = None
            if pyzbar_mod:
                try:
                    decoded = pyzbar_mod.decode(gray)
                    if decoded:
                        pyzbar_text = decoded[0].data.decode("utf-8", errors="ignore").strip()
                except Exception as e:
                    pyzbar_text = f"Error: {e}"
            else:
                pyzbar_text = "pyzbar not available"

            print(f"DPI {dpi}:")
            print(f"  - cv2.QRCodeDetector: {cv2_text if cv2_text else 'None (no QR detected)'}")
            print(f"  - pyzbar:            {pyzbar_text if pyzbar_text else 'None (no QR detected)'}")

        # Also test sample_certificate through load_image_as_array and detect_qr_code
        try:
            from app.services.image_preprocessing import load_image_as_array
            from app.services.ocr_field_extractor import detect_qr_code
            from app.services.qr_verification import verify_qr

            with open(sample_pdf_path, "rb") as f:
                sample_bytes = f.read()
            sample_img = load_image_as_array(sample_bytes, "pdf")
            sample_qr_text, sample_qr_conf = detect_qr_code(sample_img)
            print(f"\nsample_certificate.pdf via detect_qr_code: text='{sample_qr_text}', confidence={sample_qr_conf}")
            sample_qr_res = verify_qr(sample_qr_text, qr_confidence=sample_qr_conf)
            print("sample_certificate.pdf via verify_qr:")
            print(f"  - status:                  {sample_qr_res.status}")
            print(f"  - present:                 {sample_qr_res.present}")
            print(f"  - valid:                   {sample_qr_res.valid}")
            print(f"  - qr_type:                 {sample_qr_res.qr_type}")
            print(f"  - qr_confidence:           {sample_qr_res.qr_confidence}")
            print(f"  - decoded:                 {sample_qr_res.decoded}")
            print(f"  - warning:                 {sample_qr_res.warning}")
            print(f"  - reason:                  {sample_qr_res.reason}")
            print(f"  - cross_validation_status: {sample_qr_res.cross_validation_status}")
        except Exception as e:
            print(f"Error testing sample_certificate via pipeline: {e}")

print("\n" + "=" * 60)
print("3. SYNTHETIC QR TEST PDF THROUGH APP QR VERIFICATION")
print("=" * 60)

qrcode_mod = imported_modules.get("qrcode")
fitz_mod = imported_modules.get("fitz")

if not qrcode_mod or not fitz_mod:
    print("Cannot run test C: qrcode or fitz is missing.")
else:
    test_url = "https://example.com/verify/TEST123"
    print(f"Generating test QR code for URL: {test_url}")

    # Generate QR image as PNG bytes
    qr = qrcode_mod.QRCode(box_size=10, border=2)
    qr.add_data(test_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    img_byte_arr = io.BytesIO()
    qr_img.save(img_byte_arr, format="PNG")
    qr_png_bytes = img_byte_arr.getvalue()

    # Create A4 PDF with QR code placed in top-right corner
    test_pdf = fitz_mod.open()
    test_page = test_pdf.new_page(width=595, height=842)
    test_page.insert_text(fitz_mod.Point(50, 100), "TEST CERTIFICATE WITH EMBEDDED QR", fontsize=16)
    # Insert QR in corner: Rect(x0, y0, x1, y1)
    test_page.insert_image(fitz_mod.Rect(420, 50, 540, 170), stream=qr_png_bytes)
    
    pdf_bytes = test_pdf.tobytes()
    print(f"Generated synthetic test PDF ({len(pdf_bytes)} bytes).")

    # Step C1: Detect QR using the system's detect_qr_code function
    try:
        from app.services.image_preprocessing import load_image_as_array
        from app.services.ocr_field_extractor import detect_qr_code
        from app.services.qr_verification import verify_qr

        img_arr = load_image_as_array(pdf_bytes, "pdf")
        detected_text, confidence = detect_qr_code(img_arr)
        print(f"detect_qr_code output: text='{detected_text}', confidence={confidence}")

        # Step C2: Run through verify_qr service
        qr_result = verify_qr(detected_text, expected_certificate_number="TEST123", qr_confidence=confidence)
        print("verify_qr result (synthetic test certificate with QR):")
        print(f"  - status:                  {qr_result.status}")
        print(f"  - present:                 {qr_result.present}")
        print(f"  - valid:                   {qr_result.valid}")
        print(f"  - qr_type:                 {qr_result.qr_type}")
        print(f"  - qr_confidence:           {qr_result.qr_confidence}")
        print(f"  - decoded:                 {qr_result.decoded}")
        print(f"  - warning:                 {qr_result.warning}")
        print(f"  - reason:                  {qr_result.reason}")
        print(f"  - cross_validation_status: {qr_result.cross_validation_status}")

        print("\n" + "-" * 60)
        print("4. DOCUMENT WITH NO QR CODE (GENUINE ABSENCE TEST)")
        print("-" * 60)
        no_qr_res = verify_qr(None)
        print("verify_qr result (no QR code):")
        print(f"  - status:                  {no_qr_res.status}")
        print(f"  - present:                 {no_qr_res.present}")
        print(f"  - valid:                   {no_qr_res.valid}")
        print(f"  - qr_type:                 {no_qr_res.qr_type}")
        print(f"  - warning:                 {no_qr_res.warning}")
        print(f"  - reason:                  {no_qr_res.reason}")
        print(f"  - cross_validation_status: {no_qr_res.cross_validation_status}")

        print("\n" + "-" * 60)
        print("5. VERIFICATION FAILURE REASON TESTS (DOMAIN, EXPIRY, MISMATCH)")
        print("-" * 60)
        import json
        # Domain allowlist failure
        import app.services.qr_verification as qrv
        orig_get_domains = qrv._get_trusted_domains
        qrv._get_trusted_domains = lambda: ["trusted-university.edu"]
        try:
            domain_fail_res = verify_qr("https://untrusted-site.com/verify/123")
            print(f"Untrusted Domain -> status: '{domain_fail_res.status}', reason: '{domain_fail_res.reason}'")
        finally:
            qrv._get_trusted_domains = orig_get_domains

        # Expired token failure
        expired_payload = json.dumps({"certificate_id": "CERT-1", "verification_token": "T", "expiry": "2020-01-01"})
        expired_res = verify_qr(expired_payload, expected_certificate_number="CERT-1")
        print(f"Expired Token    -> status: '{expired_res.status}', reason: '{expired_res.reason}'")

        # Certificate ID mismatch failure
        mismatch_payload = json.dumps({"certificate_id": "WRONG-ID", "verification_token": "T", "expiry": "2030-01-01"})
        mismatch_res = verify_qr(mismatch_payload, expected_certificate_number="CERT-1")
        print(f"Cert Mismatch    -> status: '{mismatch_res.status}', reason: '{mismatch_res.reason}'")

    except Exception as e:
        print("Error running synthetic PDF through verification pipeline:")
        traceback.print_exc()

print("=" * 60)
