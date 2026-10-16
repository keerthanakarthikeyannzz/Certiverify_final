import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

// In the browser, use a relative base URL so all /api/* requests go through
// the Next.js rewrite proxy (next.config.js) → backend. This avoids:
//   - CORS preflight failures (same-origin request via proxy)
//   - IPv4/IPv6 mismatch ("connection refused" on macOS)
// On the server (SSR/RSC), use the full backend URL for direct communication.
const API_URL =
  typeof window === "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000")
    : "";

// Use this for generating direct href/src URLs (e.g. preview, download).
// Always use the full backend URL so browser can open links directly.
const BACKEND_DIRECT_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export const api = axios.create({ baseURL: API_URL });

// --- token storage (in-memory + localStorage; swap for httpOnly cookies in prod) ---
export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("cv_access_token");
}
export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("cv_refresh_token");
}
export function setTokens(access: string, refresh: string) {
  localStorage.setItem("cv_access_token", access);
  localStorage.setItem("cv_refresh_token", refresh);
}
export function clearTokens() {
  localStorage.removeItem("cv_access_token");
  localStorage.removeItem("cv_refresh_token");
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let isRefreshing = false;
let refreshQueue: (() => void)[] = [];

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && !original._retry && getRefreshToken()) {
      if (isRefreshing) {
        await new Promise<void>((resolve) => refreshQueue.push(resolve));
        return api(original);
      }
      original._retry = true;
      isRefreshing = true;
      try {
        const { data } = await axios.post(`${API_URL}/api/v1/auth/refresh`, {
          refresh_token: getRefreshToken(),
        });
        setTokens(data.access_token, data.refresh_token);
        refreshQueue.forEach((cb) => cb());
        refreshQueue = [];
        return api(original);
      } catch {
        clearTokens();
        if (typeof window !== "undefined") window.location.href = "/login";
      } finally {
        isRefreshing = false;
      }
    }
    if (error.response?.status === 429) {
      const retryAfter = error.response.headers?.["retry-after"];
      const seconds = retryAfter ? parseInt(retryAfter, 10) : 60;
      const friendlyMessage = `Too many requests. Please try again in ${isNaN(seconds) ? 60 : seconds} seconds.`;
      if (error.response.data && typeof error.response.data === "object") {
        (error.response.data as Record<string, any>).detail = friendlyMessage;
      }
      error.message = friendlyMessage;
    }
    return Promise.reject(error);
  }
);

// --- typed endpoint helpers ---
export interface UserResponse {
  id: string;
  full_name: string;
  email: string;
  role: string;
  is_active: boolean;
  is_email_verified: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserResponse;
}

export const authApi = {
  register: (data: { full_name: string; email: string; password: string; role: string }) =>
    api.post<UserResponse>("/api/v1/auth/register", data),

  verifyEmail: (data: { email: string; code: string }) =>
    api.post<UserResponse>("/api/v1/auth/verify-email", data),

  resendOtp: (data: { email: string }) => api.post("/api/v1/auth/resend-otp", data),

  login: (data: { email: string; password: string }) =>
    api.post<TokenResponse>("/api/v1/auth/login", data),

  forgotPassword: (data: { email: string }) => api.post("/api/v1/auth/forgot-password", data),

  resetPassword: (data: { token: string; new_password: string }) =>
    api.post("/api/v1/auth/reset-password", data),

  me: () => api.get<UserResponse>("/api/v1/auth/me"),

  logout: () => api.post("/api/v1/auth/logout"),
};

export interface CertificateResponse {
  id: string;
  original_filename: string;
  file_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  group_id?: string;
  uploaded_at: string;
}

export interface DocumentTypeResponse {
  id: string;
  certificate_id: string;
  predicted_type: string;
  confidence_score: number;
  model_used: string;
  created_at: string;
}

export const documentTypeApi = {
  classify: (certificateId: string) =>
    api.post<DocumentTypeResponse>(`/api/v1/certificates/${certificateId}/classify`),
  get: (certificateId: string) =>
    api.get<DocumentTypeResponse>(`/api/v1/certificates/${certificateId}/document-type`),
};

export interface OCRDataResponse {
  id: string;
  certificate_id: string;
  student_name?: string;
  university_name?: string;
  register_number?: string;
  roll_number?: string;
  certificate_number?: string;
  department?: string;
  course?: string;
  cgpa?: number;
  percentage?: number;
  date_of_issue?: string;
  qr_code_data?: string;
  has_signature: boolean;
  has_seal: boolean;
  ocr_accuracy: number;
  ocr_engine: string;
  field_confidences: Record<string, number>;
  created_at: string;
}

export type OCRDataUpdate = Partial<
  Pick<
    OCRDataResponse,
    | "student_name"
    | "university_name"
    | "register_number"
    | "roll_number"
    | "certificate_number"
    | "department"
    | "course"
    | "cgpa"
    | "percentage"
    | "date_of_issue"
  >
>;

export interface FieldValidationItem {
  field: string;
  label: string;
  extracted_value?: string | null;
  confidence: number;
  status: "VALID" | "INVALID" | "MISSING" | "LOW_CONFIDENCE" | "NOT_APPLICABLE" | "NOT_DETECTED";
  reason: string;
}

export interface DocumentValidationResponse {
  certificate_id: string;
  document_type: string;
  classification_confidence: number;
  expected_fields: string[];
  field_validations: FieldValidationItem[];
}

export const ocrApi = {
  extract: async (certificateId: string, docType?: string, forceRefresh: boolean = false) => {
    const params = {
      ...(docType ? { doc_type: docType } : {}),
      ...(forceRefresh ? { force_refresh: true } : {}),
    };
    // Direct call first to avoid Next.js dev server rewrite proxy socket timeouts (ECONNRESET) on slow OCR inference
    const directUrl = BACKEND_DIRECT_URL
      ? `${BACKEND_DIRECT_URL}/api/v1/certificates/${certificateId}/extract-ocr`
      : `/api/v1/certificates/${certificateId}/extract-ocr`;
    try {
      return await api.post<OCRDataResponse>(directUrl, undefined, {
        params,
        timeout: 300_000,
      });
    } catch (err: any) {
      if (directUrl.startsWith("http") && (!err.response || err.code === "ECONNREFUSED")) {
        return await api.post<OCRDataResponse>(
          `/api/v1/certificates/${certificateId}/extract-ocr`,
          undefined,
          { params, timeout: 300_000 }
        );
      }
      throw err;
    }
  },
  get: (certificateId: string) =>
    api.get<OCRDataResponse>(`/api/v1/certificates/${certificateId}/ocr-data`),
  update: (certificateId: string, data: OCRDataUpdate) =>
    api.patch<OCRDataResponse>(`/api/v1/certificates/${certificateId}/ocr-data`, data),
  validate: (certificateId: string) =>
    api.post<DocumentValidationResponse>(`/api/v1/certificates/${certificateId}/validate`),
};

export interface ComparisonFieldDetail {
  values: (string | number)[];
  status: "matching" | "mismatched" | "missing";
}

export interface DocumentComparisonResponse {
  id: string;
  group_id: string;
  matching_fields: string[];
  mismatched_fields: string[];
  missing_fields: string[];
  consistency_percentage: number;
  details: Record<string, ComparisonFieldDetail>;
  created_at: string;
}

export const comparisonApi = {
  run: (groupId: string) => api.post<DocumentComparisonResponse>(`/api/v1/comparisons/${groupId}/run`),
  get: (groupId: string) => api.get<DocumentComparisonResponse>(`/api/v1/comparisons/${groupId}`),
  comparePair: (certificateIdA: string, certificateIdB: string) =>
    api.post<CertificatePairComparisonResponse>("/api/v1/comparisons/compare-pair", {
      certificate_id_a: certificateIdA,
      certificate_id_b: certificateIdB,
    }),
  uploadAndCompare: (certificateIdA: string, file: File) => {
    const formData = new FormData();
    formData.append("certificate_id_a", certificateIdA);
    formData.append("file", file);
    return api.post<CertificatePairComparisonResponse>(
      "/api/v1/comparisons/upload-and-compare",
      formData
    );
  },
};

// ---- Direct Compare (in-memory, no DB) ----

export interface FieldComparisonRow {
  field: string;
  field_label: string;
  doc1_value: string | null;
  doc2_value: string | null;
  similarity: number | null;   // 0-100, null when missing
  status: "match" | "partial" | "mismatch" | "missing";
}

export interface DirectCompareResponse {
  doc1_type: string;
  doc2_type: string;
  doc1_fields: Record<string, string | null>;
  doc2_fields: Record<string, string | null>;
  comparison: FieldComparisonRow[];
  similarity_percentage: number;
  comparison_score: number;          // 0-100 alias
  matched_fields: string[];
  mismatched_fields: string[];
  missing_fields: string[];
  doc1_ocr_accuracy: number;
  doc2_ocr_accuracy: number;
  pair_hint: string;                 // e.g. "Degree Certificate ↔ Resume"
  ai_summary: string[];             // human-readable bullet points
  documents_compared?: number;
  comparison_type?: "field_comparison" | "identical_document";
}

export const directCompareApi = {
  compare: (
    filesOrFile1: File[] | File,
    file2OrDocTypes?: File | string[],
    docType1?: string,
    docType2?: string,
  ) => {
    const formData = new FormData();
    if (Array.isArray(filesOrFile1)) {
      const files = filesOrFile1;
      const docTypes = (file2OrDocTypes as string[]) || [];
      files.forEach((f) => formData.append("files", f));
      docTypes.forEach((dt) => formData.append("doc_types", dt));
    } else {
      const f1 = filesOrFile1;
      const f2 = file2OrDocTypes as File;
      formData.append("file1", f1);
      formData.append("file2", f2);
      if (docType1) formData.append("doc_type1", docType1);
      if (docType2) formData.append("doc_type2", docType2);
    }

    return api.post<DirectCompareResponse>("/api/v1/direct-compare", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 480_000,   // 8 min — OCR on 2-5 docs can take time
    });
  },

  /** Download a PDF comparison report without saving anything to the DB. */
  downloadPdf: async (
    filesOrFile1: File[] | File,
    file2OrDocTypes?: File | string[],
    docType1?: string,
    docType2?: string,
  ): Promise<void> => {
    const token = getAccessToken();
    if (!token) throw new Error("Not authenticated");

    const formData = new FormData();
    if (Array.isArray(filesOrFile1)) {
      const files = filesOrFile1;
      const docTypes = (file2OrDocTypes as string[]) || [];
      files.forEach((f) => formData.append("files", f));
      docTypes.forEach((dt) => formData.append("doc_types", dt));
    } else {
      const f1 = filesOrFile1;
      const f2 = file2OrDocTypes as File;
      formData.append("file1", f1);
      formData.append("file2", f2);
      if (docType1) formData.append("doc_type1", docType1);
      if (docType2) formData.append("doc_type2", docType2);
    }

    const res = await fetch(`${API_URL}/api/v1/direct-compare/pdf`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });

    if (!res.ok) {
      let detail = "";
      try {
        const text = await res.text();
        try {
          const json = JSON.parse(text);
          detail = json.detail?.message || json.detail || text;
        } catch {
          detail = text;
        }
      } catch {
        detail = `PDF generation failed (${res.status})`;
      }
      throw new Error(detail || `PDF generation failed (${res.status})`);
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const ts = new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-");
    a.download = `CertiVerify_Comparison_${ts}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};


export interface VerificationResultResponse {
  id: string;
  certificate_id: string;
  qr_present: boolean;
  qr_decoded_data?: Record<string, unknown>;
  qr_valid?: boolean;
  qr_warning?: string;
  blockchain_hash_submitted?: string;
  blockchain_hash_onchain?: string;
  blockchain_match?: boolean;
  blockchain_tx_hash?: string;
  blockchain_status?: string;
  // Hash consistency (fresh hash vs stored hash at verify time)
  hash_match_status?: string;              // MATCH | MISMATCH | NOT_REGISTERED | NOT_CHECKED
  // Tampering Detection
  tampering_score?: number;
  tampering_status?: string | null;
  tampering_flags?: string[];
  ela_heatmap_path?: string;
  tampering_risk_level?: string;           // LOW | MINOR_ANOMALIES | MODERATE_RISK | HIGH_RISK | VERY_HIGH_RISK
  tampering_confidence?: number;           // 0-100
  tampering_detail?: {
    status?: string;
    tampering_status?: string;
    image_quality?: {
      score: number;                       // 0-100 (high = good)
      status: string;                      // GOOD | MODERATE | POOR
      detail?: string;
      breakdown?: { resolution: number; sharpness: number; contrast: number; noise: number; brightness: number };
    };
    ela?: {
      score: number;                       // raw ELA mean score
      risk: number;                        // 0-100 risk derived from ELA
      status: string;                      // NORMAL | POSSIBLE_MANIPULATION
    };
    copy_paste?: {
      detected: boolean;
      score: number;                       // 0-100 risk
      cluster_size: number;
      clone_regions_count?: number;
      regions?: Array<{ x: number; y: number; w: number; h: number }>;
    };
    font_consistency?: {
      score: number;                       // 0-100 (high = consistent)
      status: string;                      // CONSISTENT | POSSIBLE_EDIT
      detail?: string;
    };
    text_analysis?: {                      // PART E — text layout / alignment
      score: number;                       // 0-100 (high = consistent)
      status: string;                      // NORMAL | ANOMALOUS
      detail?: string;
      alignment_score?: number;
      line_count?: number | null;
      spacing_cv?: number | null;
      density_cv?: number | null;
    };
    signature?: {
      detected: boolean;
      anomaly_score: number;
      contour_count?: number;
      reason?: string;
    };
    seal?: {
      detected: boolean;
      anomaly_score: number;
      reason?: string;
    };
    metadata?: {
      status: string;                      // NORMAL | MINOR_WARNING | WARNING
      anomalies?: string[];
      score?: number;
    };
    document_structure?: {
      anomaly_score: number;
      missing_fields?: string[];
      reason?: string;
    };
    findings?: Array<{
      type: string;
      status: string;
      score: number;
      confidence: number;
      reason: string;
      regions?: Array<{ x: number; y: number; w: number; h: number }>;
    }>;
  };
  // Duplicate Detection
  is_duplicate: boolean;
  duplicate_of_certificate_id?: string;
  duplicate_match_reason?: string;
  duplicate_detail?: {
    duplicate_status: string;             // NO_DUPLICATE | EXACT_FILE_DUPLICATE | DUPLICATE_UPLOAD | DUPLICATE_CERTIFICATE | POSSIBLE_DUPLICATE | CERTIFICATE_CONFLICT | QR_DUPLICATE | BLOCKCHAIN_DUPLICATE
    duplicate_type: string;
    duplicate_detected: boolean;
    confidence: number;                   // 0–100
    matched_certificate_id?: string | null;
    matched_fields: string[];
    conflicting_fields: string[];
    file_hash_match: boolean;
    certificate_number_match: boolean;
    registration_number_match: boolean;
    qr_match: boolean;
    field_similarity: number;             // 0–100 fuzzy field similarity
    visual_similarity: number;            // 0–100 dHash visual similarity
    same_owner: boolean;
    reason: string;
  };
  // Cross-Validation (QR data vs OCR fields)
  cross_validation_status?: string;         // CONSISTENT | MISMATCH | PARTIAL | UNAVAILABLE
  cross_validation_mismatches?: Array<{ field: string; qr_value: string; ocr_value: string }>;
  created_at: string;
}

// Part L — structured composite verification result
export interface EnhancedVerificationResponse {
  certificate_id: string;
  qr_verification: {
    status: string;                        // VERIFIED | INVALID | NOT_FOUND | PRESENT_UNVERIFIED
    qr_present: boolean;
    qr_decoded: boolean;
    qr_type: string;                       // json_payload | url | plain_text | none | unknown
    detection_source: string;              // direct_file | ocr_stored | none
    qr_confidence?: number | null;
    certificate_id_from_qr?: string | null;
    warning?: string | null;
  };
  hash_verification: {
    algorithm: string;                     // "SHA-256"
    uploaded_hash?: string;
    stored_hash?: string;
    status: string;                        // MATCH | MISMATCH | NOT_REGISTERED | NOT_CHECKED
  };
  blockchain_verification: {
    status: string;                        // VERIFIED | NOT_REGISTERED | HASH_MISMATCH | UNAVAILABLE | NOT_CHECKED
    algorithm: string;
    submitted_hash?: string | null;
    onchain_hash?: string | null;
    hash_match?: boolean | null;
    transaction_id?: string | null;
    timestamp?: string | null;
  };
  cross_validation: {
    status: string;                        // CONSISTENT | MISMATCH | UNAVAILABLE
    mismatches: Array<{ field: string; qr_value: string; ocr_value: string }>;
    fields_checked: number;
  };
  composite_status: string;               // STRONGLY_VERIFIED | VERIFIED | SUSPICIOUS | HIGH_RISK | INSUFFICIENT_EVIDENCE
  composite_detail: string;
  checks_completed: number;
  checks_total: number;
  verified_at?: string | null;
}

export const verificationApi = {
  verifyQr: (certificateId: string) =>
    api.post<VerificationResultResponse>(`/api/v1/certificates/${certificateId}/verify-qr`),
  verifyBlockchain: (certificateId: string) =>
    api.post<VerificationResultResponse>(`/api/v1/certificates/${certificateId}/verify-blockchain`),
  verifyTampering: (certificateId: string) =>
    api.post<VerificationResultResponse>(`/api/v1/certificates/${certificateId}/verify-tampering`),
  verifyDuplicate: (certificateId: string) =>
    api.post<VerificationResultResponse>(`/api/v1/certificates/${certificateId}/verify-duplicate`),
  verifyAll: (certificateId: string) =>
    api.post<VerificationResultResponse>(`/api/v1/certificates/${certificateId}/verify-all`),
  get: (certificateId: string) =>
    api.get<VerificationResultResponse>(`/api/v1/certificates/${certificateId}/verification`),
  getEnhanced: (certificateId: string) =>
    api.get<EnhancedVerificationResponse>(`/api/v1/certificates/${certificateId}/verify-enhanced`),
  elaHeatmapUrl: (certificateId: string) => {
    const token = getAccessToken();
    const query = token ? `?token=${encodeURIComponent(token)}` : "";
    return `${BACKEND_DIRECT_URL}/api/v1/certificates/${certificateId}/ela-heatmap${query}`;
  },
};

export interface FraudAnalysisResponse {
  id: string;
  certificate_id: string;
  fraud_probability: number;
  ocr_accuracy_weight: number;
  comparison_weight: number;
  qr_weight: number;
  blockchain_weight: number;
  tampering_weight: number;
  duplicate_weight: number;
  metadata_integrity_weight: number;
  image_quality_weight: number;
  // Rich analysis fields (from POST /analyze-fraud, Optional on GET)
  risk_level?: string;                      // LOW | MODERATE | HIGH | VERY_HIGH
  factor_risks?: Record<string, number>;    // raw 0-1 risk per factor
  critical_overrides_applied?: string[];    // hard floor labels that fired
  created_at: string;
}

export const fraudApi = {
  analyze: (certificateId: string) =>
    api.post<FraudAnalysisResponse>(`/api/v1/certificates/${certificateId}/analyze-fraud`),
  get: (certificateId: string) =>
    api.get<FraudAnalysisResponse>(`/api/v1/certificates/${certificateId}/fraud-analysis`),
};

export interface TrustScoreResponse {
  id: string;
  certificate_id: string;
  score: number;
  breakdown: {
    weights: Record<string, number>;
    factor_trust_values: Record<string, number>;
    evidence_breakdown?: EvidenceBreakdown;
    [key: string]: any;
  };
  created_at: string;
}

export const trustScoreApi = {
  compute: (certificateId: string) =>
    api.post<TrustScoreResponse>(`/api/v1/certificates/${certificateId}/compute-trust-score`),
  get: (certificateId: string) =>
    api.get<TrustScoreResponse>(`/api/v1/certificates/${certificateId}/trust-score`),
};

export interface VerificationSummary {
  document_type_identified: boolean;
  ocr_extracted: boolean;
  document_comparison_run: boolean;
  qr_checked: boolean;
  blockchain_checked: boolean;
  tampering_checked: boolean;
  duplicate_checked: boolean;
  fraud_analyzed: boolean;
  trust_score_computed: boolean;
  prediction_made?: boolean;
}

// Per-factor evidence entry returned by the AI engine
export interface EvidenceFactor {
  score?: number | null;
  status: string;       // "PASS" | "WARN" | "FAIL" | "VERIFIED" | "MATCH" | "MISMATCH" | "NOT_FOUND" | "UNAVAILABLE" | etc.
  label?: string;
  trust?: number;
  display_status?: string;
}

export interface PartialVerificationInfo {
  completed: number;
  total: number;
  note: string;
  is_partial: boolean;
  missing_checks?: string[];
}

export interface EvidenceBreakdown {
  ocr?: EvidenceFactor;
  classification?: EvidenceFactor;
  field_extraction?: EvidenceFactor;
  comparison?: EvidenceFactor;
  qr?: EvidenceFactor;
  blockchain?: EvidenceFactor;
  tampering?: EvidenceFactor;
  duplicate?: EvidenceFactor;
  metadata?: EvidenceFactor;
  _partial_verification?: PartialVerificationInfo;
  [key: string]: any;
}

export interface FinalPredictionResponse {
  id: string;
  certificate_id: string;
  label: "genuine" | "suspicious" | "fake" | "inconclusive" | string;
  confidence_score: number;
  explanation: string;
  recommended_action: string;
  fraud_probability?: number;
  evidence?: EvidenceBreakdown;
  evidence_breakdown?: EvidenceBreakdown;
  reasons?: string[];
  verification_summary?: VerificationSummary;
  created_at: string;
}

// Unified single-call verification result
export interface VerificationResultResponse {
  certificate_id: string;
  trust_score?: number;
  fraud_probability?: number;
  prediction?: "genuine" | "suspicious" | "fake" | "inconclusive" | string;
  confidence?: number;
  explanation?: string;
  recommended_action?: string;
  evidence?: EvidenceBreakdown;
  reasons?: string[];
  verification_summary: VerificationSummary;
  data_completeness: number;
}

export const predictionApi = {
  predict: (certificateId: string) =>
    api.post<FinalPredictionResponse>(`/api/v1/certificates/${certificateId}/predict`),
  get: (certificateId: string) =>
    api.get<FinalPredictionResponse>(`/api/v1/certificates/${certificateId}/prediction`),
  review: (certificateId: string, data: { verdict: string; review_note?: string }) =>
    api.post<{ certificate_id: string; verdict: string; review_note?: string; explanation: string }>(
      `/api/v1/certificates/${certificateId}/review`,
      data
    ),
};

export const verificationResultApi = {
  get: (certificateId: string) =>
    api.get<VerificationResultResponse>(`/api/v1/certificates/${certificateId}/verification-result`),
};

export interface FieldComparisonRowData {
  field: string;
  field_label: string;
  doc_a_value?: string | null;
  doc_b_value?: string | null;
  status: "MATCH" | "MISMATCH" | "UNKNOWN / NOT DETECTED";
  similarity?: number | null;
}

export interface CertificatePairComparisonResponse {
  certificate_id_a: string;
  certificate_id_b: string;
  doc_a_filename: string;
  doc_b_filename: string;
  doc_a_type: string;
  doc_b_type: string;
  comparison_rows: FieldComparisonRowData[];
  matched_count: number;
  mismatched_count: number;
  unknown_count: number;
  consistency_percentage: number;
  summary_narrative: string;
  overall_match_status?: string | null;
  field_comparisons?: any[] | null;
  summary?: string | null;
}



export interface CertificateHistoryItem {
  certificate_id: string;
  filename: string;
  file_type: string;
  document_type?: string | null;
  trust_score?: number | null;
  prediction?: string | null;
  status: string;
  timestamp: string;
  report_reference?: string | null;
}

export const certificateApi = {
  upload: (files: File[]) => {
    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));
    return api.post<{ group_id: string; certificates: CertificateResponse[] }>(
      "/api/v1/certificates/upload",
      formData,
    );
  },
  list: () => api.get<CertificateResponse[]>("/api/v1/certificates"),
  getHistory: () => api.get<CertificateHistoryItem[]>("/api/v1/certificates/history"),
  get: (id: string) => api.get<CertificateResponse>(`/api/v1/certificates/${id}`),
  previewUrl: (id: string) => {
    const token = getAccessToken();
    const query = token ? `?token=${encodeURIComponent(token)}` : "";
    return `${BACKEND_DIRECT_URL}/api/v1/certificates/${id}/preview${query}`;
  },
  remove: (id: string) => api.delete(`/api/v1/certificates/${id}`),
  deleteHistory: (id: string) =>
    api.delete<{ success: boolean; message: string; certificate_id: string }>(
      `/api/v1/certificates/history/${id}`,
    ),
};

// ---- Module 10 — Verification Report ----

export interface VerificationReportResponse {
  id: string;
  certificate_id: string;
  verification_id: string;
  pdf_path?: string;
  digital_signature?: string;
  generated_at: string;
}

export const reportApi = {
  generate: (certificateId: string) =>
    api.post<VerificationReportResponse>(`/api/v1/certificates/${certificateId}/generate-report`),
  get: (certificateId: string) =>
    api.get<VerificationReportResponse>(`/api/v1/certificates/${certificateId}/report`),
  downloadUrl: (certificateId: string) =>
    `${BACKEND_DIRECT_URL}/api/v1/certificates/${certificateId}/download-report`,
};

// ---- Module 10 — Dashboard Stats ----

export interface PredictionDistribution {
  genuine: number;
  suspicious: number;
  fake: number;
  inconclusive?: number;
  not_run: number;
}

export interface RecentCertificate {
  id: string;
  original_filename: string;
  file_type: string;
  uploaded_at: string;
  trust_score?: number;
  ocr_accuracy?: number;
  prediction_label?: string;
  fraud_probability?: number;
  has_report: boolean;
  verification_id?: string;
}

export interface TimelineEvent {
  certificate_id: string;
  filename: string;
  event: string;
  timestamp: string;
  label?: string;
}

export interface DashboardStatsResponse {
  total_certificates: number;
  avg_trust_score?: number;
  prediction_distribution: PredictionDistribution;
  recent_certificates: RecentCertificate[];
  timeline: TimelineEvent[];
  total_reports_generated: number;
  avg_ocr_accuracy?: number;
  avg_fraud_probability?: number;
  // Priority 8 — new additive fields
  duplicate_count?: number;
  tampered_count?: number;
  qr_verified_count?: number;
  blockchain_verified_count?: number;
  doc_type_distribution?: Record<string, number>;
}

export const dashboardApi = {
  stats: () => api.get<DashboardStatsResponse>("/api/v1/dashboard/stats"),
};

// ── Priority 8 — Analytics types ────────────────────────────────────────────

export interface AnalyticsOverview {
  total_certificates: number;
  genuine_count: number;
  suspicious_count: number;
  fake_count: number;
  not_predicted_count: number;
  duplicate_count: number;
  tampered_count: number;
  qr_verified_count: number;
  blockchain_verified_count: number;
  avg_trust_score?: number;
  avg_ocr_accuracy?: number;
  avg_fraud_probability?: number;
  avg_tampering_score?: number;
  qr_verification_rate?: number;
  blockchain_verification_rate?: number;
  tampering_detection_rate?: number;
  verification_completion_rate?: number;
}

export interface DocTypeDistribution {
  doc_types: Record<string, number>;
  total_classified: number;
}

export interface TrustBand {
  label: string;
  description: string;
  count: number;
  percentage: number;
}

export interface TrustDistribution {
  bands: TrustBand[];
  total_scored: number;
}

export interface FraudSignals {
  tampering_detected: number;
  duplicates_detected: number;
  blockchain_mismatch: number;
  qr_invalid: number;
  comparison_mismatch: number;
  certificate_conflict: number;
}

export interface TimeTrend {
  period: string;
  uploaded: number;
  verified: number;
}

export interface TimeTrendResponse {
  daily: TimeTrend[];
  weekly: TimeTrend[];
  monthly: TimeTrend[];
}

export interface UniversityStat {
  university_name: string;
  total: number;
  genuine: number;
  suspicious: number;
  fake: number;
  avg_trust_score?: number;
}

export interface UniversityStats {
  universities: UniversityStat[];
}

export const analyticsApi = {
  overview: () => api.get<AnalyticsOverview>("/api/v1/analytics/overview"),
  docTypes: () => api.get<DocTypeDistribution>("/api/v1/analytics/doc-types"),
  trustDistribution: () => api.get<TrustDistribution>("/api/v1/analytics/trust-distribution"),
  fraudSignals: () => api.get<FraudSignals>("/api/v1/analytics/fraud-signals"),
  timeTrends: () => api.get<TimeTrendResponse>("/api/v1/analytics/time-trends"),
  universityStats: () => api.get<UniversityStats>("/api/v1/analytics/university-stats"),
};

// ── Priority 8 — Pipeline Status types ──────────────────────────────────────

export interface PipelineStage {
  stage: string;
  label: string;
  status: "COMPLETED" | "PENDING" | "FAILED" | "UNAVAILABLE" | "RUNNING" | "NOT_APPLICABLE";
  completed_at?: string;
  summary?: string;
  duration_ms?: number;
}

export interface PipelineStatusResponse {
  certificate_id: string;
  filename: string;
  file_type: string;
  uploaded_at: string;
  overall_status: "FULLY_COMPLETE" | "PARTIALLY_COMPLETE" | "NOT_STARTED";
  completion_pct: number;
  stages: PipelineStage[];
}

export const pipelineApi = {
  status: (certificateId: string) =>
    api.get<PipelineStatusResponse>(`/api/v1/certificates/${certificateId}/pipeline`),
  runPipeline: (certificateId: string) =>
    api.post<PipelineStatusResponse>(`/api/v1/certificates/${certificateId}/run-pipeline`),
};

// ── Phase 2 — Async Verification Jobs ──────────────────────────────────────

export interface VerificationJobResponse {
  id: string;
  job_id?: string;
  certificate_id: string;
  organization_id?: string;
  status: "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED" | "CANCELLED";
  current_stage: string;
  progress_percentage: number;
  stage_states?: Record<string, { status: string; label?: string; started_at?: string; completed_at?: string; error?: string }>;
  error_details?: string;
  failed_stage?: string;
  retry_count: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface VerificationJobCreateResponse {
  job_id: string;
  certificate_id: string;
  status: string;
  current_stage: string;
  progress_percentage: number;
  message: string;
}

export const jobsApi = {
  getJobStatus: (jobId: string) =>
    api.get<VerificationJobResponse>(`/api/v1/jobs/${jobId}/status`),
  getLatestJobForCertificate: (certificateId: string) =>
    api.get<VerificationJobResponse>(`/api/v1/certificates/${certificateId}/job-status`),
  startVerificationJob: (certificateId: string) =>
    api.post<VerificationJobCreateResponse>(`/api/v1/certificates/${certificateId}/verify-async`),
  retryJob: (jobId: string) =>
    api.post<VerificationJobCreateResponse>(`/api/v1/jobs/${jobId}/retry`),
};

// ── Phase 3 — Evidence Provenance & Explainable AI ─────────────────────────

export interface EvidenceItemResponse {
  id: string;
  evidence_id: string;
  organization_id?: string | null;
  certificate_id: string;
  verification_job_id?: string | null;
  evidence_type: string;
  source: string;
  stage: string;
  timestamp: string;
  document_hash: string;
  algorithm_engine: string;
  algorithm_version?: string | null;
  confidence: number;
  result: string;
  explanation: string;
  details?: Record<string, any> | null;
  created_at: string;
}

export interface EvidencePaginatedResponse {
  items: EvidenceItemResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const evidenceApi = {
  getEvidence: (
    certificateId: string,
    params?: { evidence_type?: string; verification_job_id?: string; page?: number; page_size?: number }
  ) => api.get<EvidencePaginatedResponse>(`/api/v1/certificates/${certificateId}/evidence`, { params }),

  getJobs: (certificateId: string) =>
    api.get<
      Array<{
        id: string;
        status: string;
        current_stage: string;
        progress_percentage: number;
        retry_count: number;
        created_at: string;
        completed_at?: string;
      }>
    >(`/api/v1/certificates/${certificateId}/evidence/jobs`),
};

// ── Organizations API ────────────────────────────────────────────────────────

export interface OrganizationResponse {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface OrganizationMemberResponse {
  id: string;
  organization_id: string;
  user_id: string;
  role: string;
  created_at: string;
}

export const orgApi = {
  create: (data: { name: string; slug?: string }) =>
    api.post<OrganizationResponse>("/api/v1/organizations", data),
  getMyOrg: () => api.get<OrganizationResponse>("/api/v1/organizations/me"),
  getMembers: () => api.get<OrganizationMemberResponse[]>("/api/v1/organizations/me/members"),
};

// ── API Keys API ─────────────────────────────────────────────────────────────

export interface ApiKeyCreateRequest {
  name: string;
  permissions?: string[];
  rate_limit?: number;
  expires_at?: string;
}

export interface ApiKeyCreateResponse {
  id: string;
  organization_id: string;
  key_prefix: string;
  raw_key: string;
  name: string;
  permissions: string[];
  status: string;
  rate_limit: number;
  expires_at?: string;
  created_at: string;
}

export interface ApiKeyResponse {
  id: string;
  organization_id: string;
  key_prefix: string;
  name: string;
  permissions: string[];
  status: string;
  rate_limit: number;
  expires_at?: string;
  last_used_at?: string;
  created_at: string;
  revoked_at?: string;
}

export const apiKeyApi = {
  list: () => api.get<ApiKeyResponse[]>("/api/v1/api-keys"),
  create: (data: ApiKeyCreateRequest) => api.post<ApiKeyCreateResponse>("/api/v1/api-keys", data),
  revoke: (keyId: string) => api.delete<{ message: string; key_id: string }>(`/api/v1/api-keys/${keyId}`),
};

// ── Webhooks API ─────────────────────────────────────────────────────────────

export interface WebhookCreateRequest {
  endpoint_url: string;
  subscribed_events: string[];
}

export interface WebhookUpdateRequest {
  endpoint_url?: string;
  subscribed_events?: string[];
  active?: boolean;
}

export interface WebhookResponse {
  id: string;
  organization_id: string;
  endpoint_url: string;
  subscribed_events: string[];
  active: boolean;
  created_at: string;
  updated_at: string;
  secret?: string | null;
}

export interface WebhookDeliveryResponse {
  id: string;
  webhook_endpoint_id: string;
  event_type: string;
  payload: Record<string, any>;
  status: string;
  attempt_count: number;
  response_status?: number | null;
  response_body?: string | null;
  next_retry_at?: string | null;
  created_at: string;
  delivered_at?: string | null;
}

export const webhookApi = {
  list: () => api.get<WebhookResponse[]>("/api/v1/webhooks"),
  get: (webhookId: string) => api.get<WebhookResponse>(`/api/v1/webhooks/${webhookId}`),
  create: (data: WebhookCreateRequest) => api.post<WebhookResponse>("/api/v1/webhooks", data),
  update: (webhookId: string, data: WebhookUpdateRequest) => api.put<WebhookResponse>(`/api/v1/webhooks/${webhookId}`, data),
  delete: (webhookId: string) => api.delete<{ message: string; webhook_id: string }>(`/api/v1/webhooks/${webhookId}`),
  testDelivery: (webhookId: string) => api.post<WebhookDeliveryResponse>(`/api/v1/webhooks/${webhookId}/test-delivery`),
  listDeliveries: (webhookId: string) => api.get<WebhookDeliveryResponse[]>(`/api/v1/webhooks/${webhookId}/deliveries`),
};

// ── Audit Logs API ───────────────────────────────────────────────────────────

export interface AuditLogResponse {
  id: string;
  organization_id?: string | null;
  actor_user_id?: string | null;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  timestamp: string;
  ip_address?: string | null;
  user_agent?: string | null;
  metadata_json?: Record<string, any> | null;
}

export const auditLogApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get<AuditLogResponse[]>("/api/v1/audit-logs", { params }),
};



