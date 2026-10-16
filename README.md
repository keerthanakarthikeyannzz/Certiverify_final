# CertiVerify AI
### AI-Powered Fake Certificate Detection & Verification System

Final-year engineering project: OCR + AI document analysis + blockchain hash verification +
QR authentication + duplicate detection + AI Trust Score, classifying certificates as
**✅ Genuine / ⚠️ Suspicious / ❌ Fake**.

---

## Build status

| # | Module | Status |
|---|--------|--------|
| 1 | User Authentication (register, OTP email verification, JWT login, refresh, forgot/reset password, RBAC) | ✅ **Built & tested** |
| 2 | Certificate Upload (drag-drop, multi-file grouping, validation, magic-byte sniffing, pluggable local/S3/Cloudinary storage) | ✅ **Built & tested** |
| 3 | AI Document Type Identification (CLIP ViT zero-shot + OpenCV layout heuristics, rule-based fallback) | ✅ **Built & tested** |
| 4 | OCR Text Extraction (EasyOCR + Tesseract dual-engine, regex field extraction, editable table) | ✅ **Built & tested** |
| 5 | Document Comparison (fuzzy field matching, consistency %, matching/mismatched/missing breakdown) | ✅ **Built & tested** |
| 6 | AI Verification — QR Check, Blockchain Verification, Tampering Detection (ELA + OpenCV), Duplicate Detection — **all 4 sub-engines built & tested** | ✅ **Done** |
| 7 | AI Fraud Analysis (weighted combination of Modules 4-6, renormalized for missing signals, duplicate override floor) | ✅ **Built & tested** |
| 8 | Trust Score Engine (0–100, weighted combination of Modules 4-7, animated gauge) | ✅ **Built & tested** |
| 9 | Final Prediction (Genuine/Suspicious/Fake + confidence + explanation + verification summary) | ✅ **Built & tested** |
| 10 | Verification Report (PDF) & Dashboard | ⏳ Next |
| — | Frontend (Next.js/React/Tailwind, glassmorphism dark UI) | ✅ **Login, Register, OTP verify, Forgot/Reset password, Upload dashboard, editable OCR table, document comparison view, full 4-engine AI Verification panel, Fraud Analysis breakdown, animated Trust Score gauge, Final Prediction verdict card — full pipeline chains from one click** |
| — | Smart contract (Solidity hash registry) | ✅ **`CertificateRegistry.sol` written, ABI + deploy script provided** |
| — | Synthetic dataset generator | ⏳ Planned |

The full database schema for **all ten modules** is already defined in
`backend/app/models/models.py`, so every later module plugs into an existing,
consistent data model instead of being bolted on afterward.

### Module 3 design note

We don't have a labeled certificate dataset to fine-tune a supervised YOLO/ViT
model, so Module 3 uses **zero-shot classification with CLIP (a real ViT)**,
boosted by OpenCV layout heuristics (circular seal detection via Hough
circles, QR presence, aspect ratio, edge density) and a pure rule-based
fallback if `torch`/`transformers` aren't installed. Swap in a fine-tuned
checkpoint later by replacing `_classify_with_clip` in
`document_classifier.py` — the API/DB contract won't need to change once
`/dataset` has labeled synthetic or real certificates to train on.

### Module 4 design note

Same honesty principle: there's no labeled NER dataset for certificate
fields, so `ocr_field_extractor.py` uses regex/keyword patterns against the
combined EasyOCR + Tesseract output rather than pretending a trained model
exists. Each field carries its own confidence (0.85 for an explicit
"Label: value" match, 0.5 for a looser contextual guess, 0 if not found) so
the frontend's editable table can flag what needs human review — and any
manual correction the user saves is stored at confidence 1.0 and should be
preferred by Modules 5/7 downstream. Swap in a fine-tuned NER/LayoutLM model
later by replacing `extract_fields`; the return contract doesn't change.
Signature/seal detection are OpenCV heuristics (contour irregularity /
Hough circles), not trained detectors — treat borderline cases as
"needs review," not ground truth.

### Module 5 design note

Compares OCR data across every document sharing a `group_id` (set at
multi-file upload time in Module 2, or via `POST /certificates/link-group`
for documents added later). Text fields use fuzzy matching (`difflib`,
0.82 similarity threshold) so OCR noise like "Jon" vs "John" doesn't get
wrongly flagged as fraud; numeric fields (CGPA, percentage) use a small
absolute tolerance. "Graduation Year" is derived from each document's
`date_of_issue` rather than being its own OCR field, since that's the
actual signal available. A field only counts toward the consistency
percentage if at least 2 documents have a non-null value for it —
otherwise it's "missing," not penalized as a mismatch. All of this was
verified against real (not hypothetical) test runs during development,
including catching a floating-point boundary edge case in the CGPA
tolerance check.

### Module 6 design note (Part 1: QR Check + Blockchain Verification)

**QR Check** handles two real-world QR schemas: a structured JSON payload
(`certificate_id`, `verification_token`, `expiry`, `university_url`) or a
plain verification URL — since there's no universal QR standard across
universities. It validates structure, expiry, and cross-checks the QR's
certificate ID against the OCR-extracted certificate number, flagging a
mismatch as a real signal rather than silently trusting the QR. A missing
QR generates a warning, not an automatic fail, per spec. All logic was
run against real test cases during development (missing QR, valid
payload, ID mismatch, expired token, valid URL, garbage content) — see
`tests/test_verification.py`.

**Blockchain Verification** never stores certificates on-chain — only
their SHA-256 hash. `blockchain/contracts/CertificateRegistry.sol` is a
real Solidity contract (issuer-authorized hash registration, free public
verification lookups); `blockchain/scripts/deploy.py` compiles it with
`py-solc-x` and deploys to Ganache. The backend's `blockchain_service.py`
reads the same ABI to call `verifyCertificate` as a gas-free view call.
Critically, it **degrades to `status="unavailable"` rather than crashing**
if Ganache isn't running or `CONTRACT_ADDRESS` isn't configured — verified
directly against the real code during development, not assumed. Module 7's
fraud scoring will need to treat "unavailable" as neutral infrastructure
state, not evidence of fraud.

To actually use it: `cd blockchain && pip install -r requirements.txt`,
run Ganache, then `python scripts/deploy.py` — it prints the values to put
in `backend/.env` (`CONTRACT_ADDRESS`, and an issuer's
`CONTRACT_OWNER_PRIVATE_KEY` from Ganache's printed dev accounts).

### Module 6 design note (Part 2: Tampering Detection + Duplicate Detection)

**Tampering Detection** ensembles four real forensic techniques since no
labeled genuine/tampered certificate dataset exists to train a CNN:
Error Level Analysis (standard PIL diff+brightness-rescale technique,
weighted heaviest — the most reliable signal), copy-paste/clone detection
(ORB keypoints self-matched and clustered by translation vector — this
went through two development iterations after the naive "raw match count"
version proved genuinely noisy on documents with repeated simple design
elements like borders; the fix and the reasoning for it are documented
in the code), blur/sharpness via Laplacian variance, and metadata
inspection (PDF producer/creator fields, image EXIF Software tags,
creation/modification date mismatches — this is the most trustworthy
signal, so it's weighted heavily when it fires). The combined 0-100 score
is explicitly framed as "flag for human review," not a forensic verdict —
that framing carries into Module 8's Trust Score. An ELA heatmap image is
generated and stored alongside each analysis for reviewer inspection
(`GET /{certificate_id}/ela-heatmap`).

**Duplicate Detection** checks a certificate against every *other*
certificate in the system, not just the uploading user's own uploads —
duplicate-certificate fraud is usually someone else's certificate being
reused under a different account, so restricting the check to one user
would miss the actual fraud case. Checks SHA-256 hash (exact file reuse),
then certificate number, register number, and QR payload (in that order
of definitiveness), stopping at the first match found.

A `POST /{certificate_id}/verify-all` convenience endpoint runs all four
Module 6 engines in one call, matching the workflow diagram's single "AI
Verification Module" step — the frontend's "Run Full Verification" button
uses it.

### Module 7 design note (AI Fraud Analysis)

Combines OCR accuracy, document comparison consistency, and all four
Module 6 verification signals into one fraud probability (0-1). No new ML
model here — the honest position, consistent with every other module in
this project, is that a *trained* fraud classifier needs labeled
genuine/fraudulent examples we don't have. Instead: each factor
contributes a risk value in [0,1], nominal weights sum to 1.0 across 8
factors, and — critically — **factors with no data available are
excluded from the average and the remaining weights renormalize**,
rather than defaulting to a neutral 0.5. An unavailable blockchain (chain
not configured) isn't evidence of anything; silently defaulting it to 0.5
would manufacture fake signal.

Duplicate Detection gets a hard floor: if `is_duplicate` is true, the
final probability is floored at 0.85 regardless of how clean the other
seven factors look — reusing someone else's certificate is close to
conclusive fraud evidence on its own and shouldn't get diluted.

All of this was validated against 6+ real scenarios during development
(clean cert, all-bad cert, duplicate override, worst-case combination,
partial/unavailable data, and the empty case) — including catching two
initially-wrong test *expectations* (not code bugs) by actually running
the math and seeing the real numbers before asserting on them. See
`tests/test_fraud_analysis.py`.

### Module 8 design note (Trust Score Engine)

Deliberately mirrors Module 7's structure (risk-value-per-factor →
weighted average → renormalize for missing data → hard override), just
inverted to a "trust" scale and including `fraud_probability` itself as
one of the eight inputs, per the spec's own factor list. That overlap is
intentional, not accidental double-counting: fraud_probability represents
the *integrated* judgment across most of these signals, while the raw
factors here (OCR accuracy, image quality, document consistency, etc.)
are kept individually visible for the dashboard's transparency —
Module 8's weight on fraud_probability (0.15) is kept moderate rather
than dominant so it doesn't just echo Module 7's answer.

Duplicate Detection gets a symmetric hard ceiling (score capped at 15)
mirroring Module 7's 0.85 floor. Validated against 6 scenarios during
development, including a clean cert landing at 97.85, a duplicate capped
at 15, and a deliberately mid-quality cert landing at 74.5 — squarely in
the "Suspicious" band the spec's own example (72) describes. See
`tests/test_trust_score.py`.

The frontend renders this as an actual animated SVG gauge (270° arc,
color-coded, animates from 0 on load) rather than a static number, per
the spec's explicit ask for "Animated Gauge, Progress Bar, Confidence
Meter" — plus a per-factor breakdown of bars beneath it.

### Module 9 design note (Final Prediction)

Classifies on the Trust Score using the same >=80/50-79/<50 bands the
frontend gauge already displays, for consistency across the app. The
*confidence* in the classification is deliberately a separate number
from the trust score: it blends how far the score sits from the nearest
threshold (a 97 is a far more confident "Genuine" than an 81) with how
much of the 8-factor Trust Score actually had real data behind it (a
score built from 2 of 8 factors gets discounted confidence even at an
extreme value) — validated directly: identical trust_score=97 with full
vs. 20% data completeness produced confidence 0.925 vs 0.525.

The explanation is built dynamically from the actual underlying signals
(tampering score, blockchain status, QR validity, comparison consistency,
OCR accuracy) rather than being a generic template — so two certificates
with the same label but different reasons behind it get different
explanations. Duplicate Detection forces the label to Fake with
confidence >=0.9 regardless of trust score, consistent with the hard
overrides already in Modules 7 and 8. A `verification_summary` on the
response tracks which of the upstream modules have actually been run,
so the frontend can show what's still pending rather than presenting an
incomplete picture as final. See `tests/test_prediction.py` — all 7
tests were run against the real implementation, including exact boundary
cases (79.9 vs 80.0, 49.9 vs 50.0).

The frontend's certificate detail page now chains the entire back half of
the pipeline from one click: "Run Full Verification" → Fraud Analysis →
Trust Score → Final Prediction, landing on a verdict card with the
✅/⚠️/❌ label, confidence, explanation, recommended action, and a
checklist of which modules actually ran.

Say **"Continue"** to build Module 10 (Verification Report & Dashboard —
the last module) next, following the workflow below exactly.

---

## Workflow (fixed — never changes)

```
User → Login/Auth → Upload Certificate(s) → AI Document Type ID → OCR Extraction
     → Document Comparison → AI Verification (QR / Blockchain / Tampering / Duplicate)
     → AI Fraud Analysis & Trust Score → Genuine / Suspicious / Fake
     → Verification Report & Dashboard
```

## Architecture

```
certiverify/
├── backend/                     FastAPI (Python 3.11, async)
│   ├── app/
│   │   ├── main.py              App entrypoint, middleware, routers
│   │   ├── core/                config.py, security.py (JWT/hashing/OTP)
│   │   ├── db/                  async SQLAlchemy session
│   │   ├── models/               ORM models — all 10 modules' tables
│   │   ├── schemas/              Pydantic request/response contracts
│   │   ├── api/                  route handlers (one router per module)
│   │   ├── services/             email, storage, OCR, blockchain, etc.
│   │   └── utils/
│   ├── tests/                    pytest unit tests
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/                    Next.js + TypeScript + Tailwind + ShadCN (scaffolding next)
└── docker-compose.yml           db + backend (+ frontend, + ganache when added)
```

### Entity-relationship summary (Module 1–10 tables)

`users (1) ──< certificates (N) ──1:1── document_types`
`certificates ──1:1── ocr_data`
`certificates ──1:1── verification_results` (QR + blockchain + tampering + duplicate, one row)
`certificates ──1:1── fraud_analysis ──1:1── trust_scores ──1:1── final_predictions ──1:1── verification_reports`
`document_comparisons` keyed by `group_id` (links a student's degree+marksheet+resume set)
`otp_codes`, `password_reset_tokens` support Module 1 auth flows

A full Mermaid/ERD diagram will be generated once Module 2 (Upload) lands, since it
depends on the `group_id` linking convention being exercised by real data.

---

## Running Modules 1–9 today

```bash
cd certiverify/backend
cp .env.example .env          # edit SECRET_KEY at minimum
cd ..
docker compose up --build     # from certiverify/ root — starts Postgres + API + Next.js frontend
```

Frontend: `http://localhost:3000` — Register → check backend logs for the dev OTP → Verify → Log in → Upload certificates (classification runs automatically and shows as a badge).
API docs: `http://localhost:8000/api/docs`

```bash
curl -X POST http://localhost:8000/api/v1/certificates/{certificate_id}/classify \
  -H "Authorization: Bearer <access_token>"
```

> First call to `/classify` downloads the ~600MB CLIP ViT-B/32 weights from
> Hugging Face (cached afterward). No internet at runtime? It automatically
> falls back to the OpenCV heuristic classifier — no crash, lower confidence.

```bash
curl -X POST http://localhost:8000/api/v1/certificates/{certificate_id}/extract-ocr \
  -H "Authorization: Bearer <access_token>"
```

> First call to `/extract-ocr` downloads EasyOCR's detection+recognition
> models (~100MB, cached afterward). If neither EasyOCR nor Tesseract can
> load, the endpoint returns a clear 422 rather than a silent wrong answer.

```bash
curl -X POST http://localhost:8000/api/v1/comparisons/{group_id}/run \
  -H "Authorization: Bearer <access_token>"
```

> Requires at least 2 documents in the group to have OCR data already
> extracted — upload a Degree + Marksheet together (Module 2 auto-groups
> them), run `/extract-ocr` on both, then compare.

```bash
curl -X POST http://localhost:8000/api/v1/certificates/{certificate_id}/verify-qr \
  -H "Authorization: Bearer <access_token>"

curl -X POST http://localhost:8000/api/v1/certificates/{certificate_id}/verify-blockchain \
  -H "Authorization: Bearer <access_token>"
```

> Blockchain verification works out-of-the-box with `blockchain_status: "unavailable"`
> until you deploy `CertificateRegistry.sol` and set `CONTRACT_ADDRESS` — see the
> Module 6 design note below for the one-command deploy flow.

```bash
curl -X POST http://localhost:8000/api/v1/certificates/{certificate_id}/verify-tampering \
  -H "Authorization: Bearer <access_token>"

curl -X POST http://localhost:8000/api/v1/certificates/{certificate_id}/verify-duplicate \
  -H "Authorization: Bearer <access_token>"

# Or run all four Module 6 engines in one call:
curl -X POST http://localhost:8000/api/v1/certificates/{certificate_id}/verify-all \
  -H "Authorization: Bearer <access_token>"
```

```bash
curl -X POST http://localhost:8000/api/v1/certificates/{certificate_id}/analyze-fraud \
  -H "Authorization: Bearer <access_token>"
```

> Best run after `/verify-all` and `/extract-ocr` (and `/comparisons/{group_id}/run`
> if the certificate is part of a multi-document set) so every factor has
> real data — but it works fine with partial data too, since unavailable
> factors are excluded rather than penalized.

```bash
curl -X POST http://localhost:8000/api/v1/certificates/{certificate_id}/compute-trust-score \
  -H "Authorization: Bearer <access_token>"
```

> The frontend chains this automatically: "Run Full Verification" →
> Fraud Analysis → Trust Score → Final Prediction, all in one click.

```bash
curl -X POST http://localhost:8000/api/v1/certificates/{certificate_id}/predict \
  -H "Authorization: Bearer <access_token>"
```

> Requires a Trust Score to already exist — 400s with a clear message
> otherwise, telling you to run `/compute-trust-score` first.

Try it:
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Test User","email":"test@example.com","password":"StrongPass1","role":"student"}'

# In DEBUG mode with no SMTP configured, the OTP is printed to the backend container logs:
docker compose logs backend | grep "DEV EMAIL" -A3
```

Run tests:
```bash
cd backend
pip install -r requirements.txt
pytest -v
```

---

## Tech stack (per spec)

**Frontend:** React.js, Next.js, TypeScript, Tailwind CSS, ShadCN UI, Framer Motion, Chart.js
**Backend:** Python, FastAPI, REST APIs, JWT
**AI:** OpenCV, EasyOCR, Tesseract OCR, PyTorch, TensorFlow, YOLO, Scikit-learn
**Blockchain:** Ethereum, Solidity, Ganache, Web3.py
**Database:** PostgreSQL
**Storage:** Cloudinary or AWS S3

## Security implemented so far (Module 1)

- Bcrypt password hashing, strength validation
- JWT access + refresh tokens
- Email verification via OTP (expires in 10 min)
- Forgot/reset password via signed single-use token
- Role-based access control (admin / university / employer / student)
- Global rate limiting (SlowAPI)
- Security response headers (HSTS, X-Frame-Options, nosniff)
- Generic error responses (no user-enumeration on forgot-password/resend-otp)

Still to add as later modules land: CSRF tokens on cookie-based flows, AES field
encryption for sensitive OCR data, SQLi/XSS hardening review, and file-upload
antivirus/type-sniffing (Module 2).
