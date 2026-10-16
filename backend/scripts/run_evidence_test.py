import urllib.request
import json
import random
import os

def test_real_certificate():
    email = f"ev_real_{random.randint(1000,9999)}@example.com"
    password = "StrongPassword123!"

    # 1. Register & Login
    reg_data = json.dumps({
        "full_name": "Real Cert Tester",
        "email": email,
        "password": password,
        "role": "student"
    }).encode("utf-8")
    
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/auth/register",
        data=reg_data,
        headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req)

    login_data = json.dumps({
        "email": email,
        "password": password
    }).encode("utf-8")
    
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/auth/login",
        data=login_data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        token = json.loads(resp.read().decode("utf-8"))["access_token"]

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload real certificate
    sample_pdf_path = os.path.join(os.path.dirname(__file__), "sample_certificate.pdf")
    if not os.path.exists(sample_pdf_path):
        sample_pdf_path = os.path.join(os.path.dirname(__file__), "..", "sample_certificate.pdf")

    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    with open(sample_pdf_path, 'rb') as f:
        file_bytes = f.read()

    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="files"; filename="sample_certificate.pdf"\r\n'
        f'Content-Type: application/pdf\r\n\r\n'
    ).encode('utf-8') + file_bytes + f'\r\n--{boundary}--\r\n'.encode('utf-8')

    upload_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }

    req = urllib.request.Request("http://127.0.0.1:8000/api/v1/certificates/upload", data=body, headers=upload_headers)
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        cert = res["certificates"][0]
        cert_id = cert["id"]
        print("REAL CERT UPLOADED | ID:", cert_id)

    # 3. Query all evidence endpoints for real cert BEFORE running verification
    print("\n--- BEFORE Running Verification/OCR ---")
    for name, endpoint in [
        ("Certificate", f"http://127.0.0.1:8000/api/v1/certificates/{cert_id}"),
        ("OCR Data", f"http://127.0.0.1:8000/api/v1/certificates/{cert_id}/ocr-data"),
        ("Verification", f"http://127.0.0.1:8000/api/v1/certificates/{cert_id}/verification"),
        ("Verification Result", f"http://127.0.0.1:8000/api/v1/certificates/{cert_id}/verification-result"),
    ]:
        try:
            r = urllib.request.Request(endpoint, headers=headers)
            with urllib.request.urlopen(r) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                print(f"[OK] {name} -> 200 OK | Data keys: {list(data.keys())}")
        except urllib.error.HTTPError as e:
            print(f"[FAIL] {name} -> Code: {e.code} | Detail: {json.loads(e.read().decode('utf-8'))}")

    # 4. Run /verify-all to populate verification result
    print("\n--- Running /verify-all ---")
    req = urllib.request.Request(f"http://127.0.0.1:8000/api/v1/certificates/{cert_id}/verify-all", data=b"", headers=headers)
    with urllib.request.urlopen(req) as resp:
        v_all = json.loads(resp.read().decode("utf-8"))
        print("verify-all 200 OK | Keys:", list(v_all.keys()))

    # 5. Query endpoints AFTER verify-all
    print("\n--- AFTER Running Verification ---")
    for name, endpoint in [
        ("Certificate", f"http://127.0.0.1:8000/api/v1/certificates/{cert_id}"),
        ("OCR Data", f"http://127.0.0.1:8000/api/v1/certificates/{cert_id}/ocr-data"),
        ("Verification", f"http://127.0.0.1:8000/api/v1/certificates/{cert_id}/verification"),
        ("Verification Result", f"http://127.0.0.1:8000/api/v1/certificates/{cert_id}/verification-result"),
    ]:
        try:
            r = urllib.request.Request(endpoint, headers=headers)
            with urllib.request.urlopen(r) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                print(f"✔ {name} -> 200 OK | Data keys: {list(data.keys())}")
        except urllib.error.HTTPError as e:
            print(f"✖ {name} -> Code: {e.code} | Detail: {json.loads(e.read().decode('utf-8'))}")

if __name__ == "__main__":
    test_real_certificate()
