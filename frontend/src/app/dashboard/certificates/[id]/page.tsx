"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ShieldCheck, ScanLine, Check, Pencil, Loader2, ArrowLeft, QrCode, Link2, AlertTriangle, CircleCheck, CircleX, CircleHelp, Sparkles, Copy, ImageIcon, Zap, Gauge, Activity, ShieldAlert, ShieldX, ListChecks, FileText, Download, RefreshCw, Layers } from "lucide-react";
import { Button } from "@/components/ui/Button";
import {
  certificateApi, CertificateResponse, getAccessToken,
  ocrApi, OCRDataResponse, OCRDataUpdate, DocumentValidationResponse,
  verificationApi, VerificationResultResponse, EnhancedVerificationResponse,
  fraudApi, FraudAnalysisResponse,
  trustScoreApi, TrustScoreResponse,
  predictionApi, FinalPredictionResponse, EvidenceBreakdown,
  verificationResultApi,
  reportApi, VerificationReportResponse,
  pipelineApi, PipelineStage, PipelineStatusResponse,
  documentTypeApi, DocumentTypeResponse,
} from "@/lib/api";
import {
  PipelineHeader,
  PipelineProgressCard,
  PipelineStageList,
  DocumentViewer,
  OcrTelemetryCard,
  OcrFieldTable,
} from "@/components/pipeline";
import {
  ForensicCockpitHeader,
  FinalVerdictMegaCard,
  DocumentPreviewCanvas,
  OcrExtractionTable,
  ForensicSignalsGrid,
  AiEvidencePanel,
  AuditLedgerTimeline,
  VerificationReportPanel,
  CompleteVerificationResultCard,
} from "@/components/certificate-details";

const FIELD_LABELS: [keyof OCRDataUpdate, string][] = [
  ["student_name", "Student Name"],
  ["university_name", "University Name"],
  ["register_number", "Register Number"],
  ["roll_number", "Roll Number"],
  ["certificate_number", "Certificate Number"],
  ["department", "Department"],
  ["course", "Course"],
  ["cgpa", "CGPA"],
  ["percentage", "Percentage"],
  ["date_of_issue", "Date of Issue"],
];

export default function CertificateDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [cert, setCert] = useState<CertificateResponse | null>(null);
  const [ocrData, setOcrData] = useState<OCRDataResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [ocrStage, setOcrStage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editValues, setEditValues] = useState<OCRDataUpdate>({});
  const [error, setError] = useState<string | null>(null);
  const [verification, setVerification] = useState<VerificationResultResponse | null>(null);
  const [verifyingQr, setVerifyingQr] = useState(false);
  const [verifyingChain, setVerifyingChain] = useState(false);
  const [verifyingTampering, setVerifyingTampering] = useState(false);
  const [verifyingDuplicate, setVerifyingDuplicate] = useState(false);
  const [verifyingAll, setVerifyingAll] = useState(false);
  const [fraudAnalysis, setFraudAnalysis] = useState<FraudAnalysisResponse | null>(null);
  const [analyzingFraud, setAnalyzingFraud] = useState(false);
  const [trustScore, setTrustScore] = useState<TrustScoreResponse | null>(null);
  const [computingTrust, setComputingTrust] = useState(false);
  const [prediction, setPrediction] = useState<FinalPredictionResponse | null>(null);
  const [predicting, setPredicting] = useState(false);
  const [report, setReport] = useState<VerificationReportResponse | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [downloadingReport, setDownloadingReport] = useState(false);
  const [validation, setValidation] = useState<DocumentValidationResponse | null>(null);
  const [docType, setDocType] = useState<DocumentTypeResponse | null>(null);

  // ── Phase 5: Pipeline Telemetry & View State ─────────
  const [pipeline, setPipeline] = useState<PipelineStatusResponse | null>(null);
  const [loadingPipeline, setLoadingPipeline] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"pipeline" | "cockpit">("pipeline");

  function seedEditValues(data: OCRDataResponse) {
    const seeded: OCRDataUpdate = {};
    FIELD_LABELS.forEach(([key]) => {
      // @ts-expect-error - dynamic field assignment across a known key union
      seeded[key] = data[key] ?? "";
    });
    setEditValues(seeded);
  }

  const refreshAllData = useCallback(async () => {
    if (id && typeof window !== "undefined") {
      localStorage.setItem("cv_current_certificate_id", id);
    }
    try {
      const [vRes, fRes, tRes, pRes, rRes, oRes, dRes, valRes, pipeRes] = await Promise.allSettled([
        verificationApi.get(id),
        fraudApi.get(id),
        trustScoreApi.get(id),
        predictionApi.get(id),
        reportApi.get(id),
        ocrApi.get(id),
        documentTypeApi.get(id),
        ocrApi.validate(id),
        pipelineApi.status(id)
      ]);

      if (vRes.status === "fulfilled") setVerification(vRes.value.data);
      if (fRes.status === "fulfilled") setFraudAnalysis(fRes.value.data);
      if (tRes.status === "fulfilled") setTrustScore(tRes.value.data);
      if (pRes.status === "fulfilled") setPrediction(pRes.value.data);
      if (rRes.status === "fulfilled") setReport(rRes.value.data);
      if (oRes.status === "fulfilled") {
        setOcrData(oRes.value.data);
        seedEditValues(oRes.value.data);
      }
      if (dRes.status === "fulfilled") setDocType(dRes.value.data);
      if (valRes.status === "fulfilled") setValidation(valRes.value.data);
      if (pipeRes.status === "fulfilled") setPipeline(pipeRes.value.data);
    } catch (err) {
      console.error("Error refreshing certificate data:", err);
    }
  }, [id]);

  const loadPipeline = useCallback(async () => {
    setLoadingPipeline(true);
    setPipelineError(null);
    try {
      const { data } = await pipelineApi.status(id);
      setPipeline(data);
    } catch {
      setPipeline(null);
      setPipelineError("Pipeline status unavailable");
    } finally {
      setLoadingPipeline(false);
    }
  }, [id]);

  const loadValidation = useCallback(async () => {
    try {
      const { data } = await ocrApi.validate(id);
      setValidation(data);
    } catch {
      setValidation(null);
    }
  }, [id]);

  const loadDocType = useCallback(async () => {
    try {
      const { data } = await documentTypeApi.get(id);
      setDocType(data);
    } catch {
      setDocType(null);
    }
  }, [id]);

  const loadOcrData = useCallback(async () => {
    try {
      const { data } = await ocrApi.get(id);
      setOcrData(data);
      seedEditValues(data);
      await loadValidation();
    } catch {
      setOcrData(null);
    }
  }, [id, loadValidation]);

  useEffect(() => {
    if (!getAccessToken()) {
      router.push("/login");
      return;
    }
    certificateApi
      .get(id)
      .then((res) => setCert(res.data))
      .catch((err: unknown) => {
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 403) {
          setError("Access Denied (403): You do not have permission to view this certificate record.");
        } else if (status === 404) {
          setError("Certificate Not Found (404): The requested credential does not exist or has been removed.");
        } else {
          setError("Failed to load certificate. Please verify your connection and try again.");
        }
      });
    loadOcrData();
    loadPipeline();
    loadValidation();
    loadDocType();
    verificationApi.get(id).then((res) => setVerification(res.data)).catch(() => setVerification(null));
    fraudApi.get(id).then((res) => setFraudAnalysis(res.data)).catch(() => setFraudAnalysis(null));
    trustScoreApi.get(id).then((res) => setTrustScore(res.data)).catch(() => setTrustScore(null));
    predictionApi.get(id).then((res) => setPrediction(res.data)).catch(() => setPrediction(null));
    reportApi.get(id).then((res) => setReport(res.data)).catch(() => setReport(null));
  }, [id, router, loadOcrData, loadPipeline, loadValidation, loadDocType]);

  const searchParams = useSearchParams();
  const sectionParam = searchParams?.get("section");

  useEffect(() => {
    if (!sectionParam) return;
    const s = sectionParam.toLowerCase();
    if (s === "ocr") {
      setActiveTab("pipeline");
      setTimeout(() => {
        const el = document.getElementById("ocr-section");
        if (el) el.scrollIntoView({ behavior: "smooth" });
      }, 200);
    } else if (s === "ai-analysis") {
      setActiveTab("cockpit");
      setTimeout(() => {
        const el = document.getElementById("ai-analysis-section");
        if (el) el.scrollIntoView({ behavior: "smooth" });
      }, 200);
    } else if (s === "verification" || s === "qr" || s === "blockchain") {
      setActiveTab("cockpit");
      setTimeout(() => {
        const el = document.getElementById("verification-section");
        if (el) el.scrollIntoView({ behavior: "smooth" });
      }, 200);
    } else if (s === "report") {
      setActiveTab("cockpit");
      setTimeout(() => {
        const el = document.getElementById("verification-report-section") || document.getElementById("report-section");
        if (el) el.scrollIntoView({ behavior: "smooth" });
      }, 200);
    }
  }, [sectionParam]);

  async function handleRunPipeline() {
    setRunning(true);
    setPipelineError(null);
    try {
      const { data } = await pipelineApi.runPipeline(id);
      setPipeline(data);
      await refreshAllData();
    } catch {
      setPipelineError("Pipeline execution failed. Please retry.");
    } finally {
      setRunning(false);
    }
  }

  async function handleRunOcr() {
    setRunning(true);
    setError(null);
    setOcrStage("Extracting text via Neural OCR inference engine...");

    try {
      const { data: ocrRes } = await ocrApi.extract(id);
      setOcrData(ocrRes);
      seedEditValues(ocrRes);
      await loadValidation();

      setOcrStage("Updating verification pipeline telemetry...");
      try {
        const { data: runData } = await pipelineApi.runPipeline(id);
        setPipeline(runData);
      } catch (pipeErr) {
        console.warn("Pipeline run after OCR error:", pipeErr);
      }
      await refreshAllData();
      setOcrStage("✓ OCR Extraction Complete");
      setTimeout(() => setOcrStage(null), 2500);
    } catch (err: unknown) {
      setOcrStage(null);
      let msg = "OCR extraction failed. Please try again.";
      if (err && typeof err === "object") {
        const axiosErr = err as {
          response?: { status?: number; data?: { detail?: string | object } };
          message?: string;
          code?: string;
        };
        const status = axiosErr.response?.status;
        const detail = axiosErr.response?.data?.detail;

        if (!axiosErr.response) {
          if (axiosErr.code === "ECONNREFUSED" || axiosErr.message?.includes("Network Error")) {
            msg = "OCR request failed: Backend unavailable (connection refused). Ensure the FastAPI server is running on port 8000.";
          } else if (axiosErr.code === "ECONNABORTED" || axiosErr.message?.includes("timeout")) {
            msg = "OCR request failed: Request timed out. OCR processing took too long.";
          } else {
            msg = `OCR request failed: ${axiosErr.message ?? "No response from server"}`;
          }
        } else if (status === 401) {
          msg = "OCR request failed: HTTP 401 — Authentication failed. Please log in again.";
        } else if (status === 403) {
          msg = "OCR request failed: HTTP 403 — Access denied.";
        } else if (status === 404) {
          msg = "OCR request failed: HTTP 404 — Certificate not found on server.";
        } else if (status === 408) {
          msg = "OCR request failed: HTTP 408 — OCR processing timeout. Please try again.";
        } else if (status === 422) {
          const d = typeof detail === "string" ? detail : JSON.stringify(detail);
          msg = `OCR request failed: HTTP 422 — ${d}`;
        } else if (status === 500) {
          const d = typeof detail === "string" ? detail : JSON.stringify(detail);
          msg = `OCR request failed: HTTP 500 — ${d || "Internal server error"}`;
        } else if (status) {
          const d = typeof detail === "string" ? detail
            : typeof detail === "object" && detail !== null ? JSON.stringify(detail)
              : "";
          msg = `OCR request failed: HTTP ${status}${d ? ` — ${d}` : ""}`;
        }
      }
      setError(msg);
    } finally {
      setRunning(false);
    }
  }

async function handleSaveCorrections() {
  setSaving(true);
  setError(null);
  try {
    const payload: OCRDataUpdate = {
      ...editValues,
      cgpa: editValues.cgpa ? Number(editValues.cgpa) : undefined,
      percentage: editValues.percentage ? Number(editValues.percentage) : undefined,
    };
    const { data } = await ocrApi.update(id, payload);
    setOcrData(data);
    seedEditValues(data);
    await loadPipeline();
  } catch {
    setError("Could not save corrections. Please try again.");
  } finally {
    setSaving(false);
  }
}

async function handleVerifyQr() {
  setVerifyingQr(true);
  setError(null);
  try {
    const { data } = await verificationApi.verifyQr(id);
    setVerification(data);
    await loadPipeline();
  } catch (err: any) {
    const detail = err?.response?.data?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message || detail?.error || err?.message;
    setError(msg ? `QR verification failed: ${msg}` : "QR verification failed. Run OCR extraction first so a QR code can be detected.");
  } finally {
    setVerifyingQr(false);
  }
}

async function handleVerifyBlockchain() {
  setVerifyingChain(true);
  setError(null);
  try {
    const { data } = await verificationApi.verifyBlockchain(id);
    setVerification(data);
    await loadPipeline();
  } catch (err: any) {
    const detail = err?.response?.data?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message || detail?.error || err?.message;
    setError(msg ? `Blockchain verification failed: ${msg}` : "Blockchain verification failed to run.");
  } finally {
    setVerifyingChain(false);
  }
}

async function handleVerifyTampering() {
  setVerifyingTampering(true);
  setError(null);
  try {
    const { data } = await verificationApi.verifyTampering(id);
    setVerification(data);
    await loadPipeline();
  } catch (err: any) {
    const detail = err?.response?.data?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message || detail?.error || err?.message;
    setError(msg ? `Tampering analysis failed: ${msg}` : "Tampering analysis failed. The file may be unreadable.");
  } finally {
    setVerifyingTampering(false);
  }
}

async function handleVerifyDuplicate() {
  setVerifyingDuplicate(true);
  setError(null);
  try {
    const { data } = await verificationApi.verifyDuplicate(id);
    setVerification(data);
    await loadPipeline();
  } catch (err: any) {
    const detail = err?.response?.data?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message || detail?.error || err?.message;
    setError(msg ? `Duplicate check failed: ${msg}` : "Duplicate check failed. Please try again.");
  } finally {
    setVerifyingDuplicate(false);
  }
}

async function handleVerifyAll() {
  setVerifyingAll(true);
  setError(null);
  try {
    const { data } = await verificationApi.verifyAll(id);
    setVerification(data);
    await handleAnalyzeFraud();
    try {
      const { data: rep } = await reportApi.generate(id);
      setReport(rep);
    } catch { }
    await loadPipeline();
  } catch (err: any) {
    const detail = err?.response?.data?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message || detail?.error || err?.message;
    setError(msg ? `Verification failed: ${msg}` : "Full verification failed to complete. Try running each check individually.");
  } finally {
    setVerifyingAll(false);
  }
}

async function handleAnalyzeFraud() {
  setAnalyzingFraud(true);
  try {
    const { data } = await fraudApi.analyze(id);
    setFraudAnalysis(data);
    await handleComputeTrustScore();
  } catch (err: any) {
    const detail = err?.response?.data?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message || detail?.error || err?.message;
    setError(msg ? `Fraud analysis failed: ${msg}` : "Fraud analysis failed. Run at least QR/Blockchain/Tampering/Duplicate checks first.");
  } finally {
    setAnalyzingFraud(false);
  }
}

async function handleComputeTrustScore() {
  setComputingTrust(true);
  try {
    const { data } = await trustScoreApi.compute(id);
    setTrustScore(data);
    await handlePredict();
  } catch (err: any) {
    const detail = err?.response?.data?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message || detail?.error || err?.message;
    setError(msg ? `Trust score computation failed: ${msg}` : "Trust score computation failed.");
  } finally {
    setComputingTrust(false);
  }
}

async function handlePredict() {
  setPredicting(true);
  try {
    const { data } = await predictionApi.predict(id);
    setPrediction(data);
    await loadPipeline();
  } catch (err: any) {
    const detail = err?.response?.data?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message || detail?.error || err?.message;
    setError(msg ? `Final prediction failed: ${msg}` : "Final prediction failed. Compute the Trust Score first.");
  } finally {
    setPredicting(false);
  }
}

async function handleGenerateReport() {
  setGeneratingReport(true);
  setError(null);
  try {
    const { data } = await reportApi.generate(id);
    setReport(data);
    await loadPipeline();
  } catch {
    setError("Report generation failed. Ensure at least OCR and Final Prediction have been run.");
  } finally {
    setGeneratingReport(false);
  }
}

// Authenticated download — uses fetch() + Bearer token so the backend JWT
// check passes. A plain <a href> or window.open sends NO auth header → 401.
async function handleDownloadReport() {
  if (!report) return;
  setDownloadingReport(true);
  try {
    const token = getAccessToken();
    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const res = await fetch(`${API_URL}/api/v1/certificates/${id}/download-report`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      setError(`Download failed (${res.status}). Please regenerate the report.`);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `CertiVerify_${report.verification_id}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch {
    setError("Download failed. Please try again.");
  } finally {
    setDownloadingReport(false);
  }
}

  if (!cert && error) {
    return (
      <main className="min-h-screen px-4 sm:px-6 lg:px-8 py-16 max-w-2xl mx-auto space-y-6">
        <div className="bg-white border border-slate-200 rounded-2xl p-8 text-center space-y-4 shadow-sm">
          <div className="w-14 h-14 rounded-2xl bg-red-50 text-red-600 flex items-center justify-center mx-auto border border-red-100">
            <ShieldAlert size={26} />
          </div>
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight">Unable to Load Certificate</h2>
            <p className="text-sm text-slate-500 mt-1 leading-relaxed">{error}</p>
          </div>
          <div className="pt-2 flex items-center justify-center gap-3">
            <Link href="/dashboard">
              <Button variant="secondary" size="sm">Back to Dashboard</Button>
            </Link>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setError(null);
                refreshAllData();
              }}
            >
              Retry
            </Button>
          </div>
        </div>
      </main>
    );
  }

  if (!cert) {
    return (
      <main className="min-h-screen px-4 sm:px-6 lg:px-8 py-8 max-w-7xl mx-auto space-y-6">
        <div className="space-y-4 animate-pulse">
          <div className="h-8 bg-slate-200 rounded-lg w-1/3" />
          <div className="h-24 bg-slate-100 rounded-xl border border-slate-200" />
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-7 h-96 bg-slate-100 rounded-xl border border-slate-200" />
            <div className="lg:col-span-5 h-96 bg-slate-100 rounded-xl border border-slate-200" />
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen px-4 sm:px-6 lg:px-8 py-8 max-w-7xl mx-auto space-y-6">
      {/* ── Top Forensic Cockpit & Pipeline Header ── */}
      <ForensicCockpitHeader
        cert={cert}
        pipeline={pipeline}
        prediction={prediction}
        report={report}
        activeTab={activeTab}
        onTabChange={(tab) => setActiveTab(tab)}
        onRefresh={() => {
          certificateApi.get(id).then((res) => setCert(res.data)).catch(() => { });
          loadOcrData();
          loadPipeline();
          loadValidation();
        }}
        onRunOcr={handleRunOcr}
        onVerifyAll={handleVerifyAll}
        onGenerateReport={handleGenerateReport}
        onDownloadReport={handleDownloadReport}
        loadingPipeline={loadingPipeline}
        runningOcr={running}
        verifyingAll={verifyingAll}
        generatingReport={generatingReport}
        downloadingReport={downloadingReport}
      />

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-sm rounded-xl px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} className="shrink-0 text-red-600" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-xs text-red-700 hover:text-red-900 font-medium">
            Dismiss
          </button>
        </div>
      )}

    {/* ── TAB 1: FIGMA SCREEN 3 - OCR & VERIFICATION PIPELINE ── */}
    {activeTab === "pipeline" && (
      <div className="space-y-6">
        {/* Prominent Complete Verification Result Card (When Available) */}
        <CompleteVerificationResultCard
          prediction={prediction}
          trustScore={trustScore}
          fraud={fraudAnalysis}
          verification={verification}
          ocrData={ocrData}
          docType={docType}
          validation={validation}
          report={report}
          cert={cert}
          onViewReport={() => {
            setActiveTab("cockpit");
            setTimeout(() => {
              const el = document.getElementById("verification-report-section");
              if (el) el.scrollIntoView({ behavior: "smooth" });
            }, 100);
          }}
          onDownloadReport={handleDownloadReport}
          downloadingReport={downloadingReport}
        />

        {/* Top 2-Column Grid: Document Preview & OCR Telemetry on Left, Pipeline Progress & 14 Stages on Right */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column (7 cols): Document Preview & OCR Telemetry */}
          <div className="lg:col-span-7 space-y-6">
            <DocumentViewer
              certificateId={id}
              filename={cert?.original_filename}
              fileType={cert?.file_type}
            />

            <OcrTelemetryCard
              ocrData={ocrData}
              running={running}
              ocrStage={ocrStage}
              onRunOcr={handleRunOcr}
            />
          </div>

          {/* Right Column (5 cols): Pipeline Progress & 14 Stages */}
          <div className="lg:col-span-5 space-y-6">
            <PipelineProgressCard
              pipeline={pipeline}
              loading={loadingPipeline}
              isRunning={running}
              errorMessage={pipelineError}
              onRetry={handleRunPipeline}
            />

            <PipelineStageList
              stages={pipeline?.stages ?? []}
              loading={loadingPipeline}
              errorMessage={pipelineError}
            />
          </div>
        </div>

        {/* Extracted Fields Table (Figma editable language) */}
        {ocrData && (
          <div id="ocr-section">
            <OcrFieldTable
              ocrData={ocrData}
              editValues={editValues}
              onChangeField={(key: keyof OCRDataUpdate, value: string) => setEditValues((prev) => ({ ...prev, [key]: value }))}
              onSave={handleSaveCorrections}
              saving={saving}
              onReset={() => {
                if (ocrData) {
                  const initial: OCRDataUpdate = {};
                  for (const [key] of FIELD_LABELS) {
                    const val = (ocrData as unknown as Record<string, unknown>)[key];
                    // @ts-expect-error - dynamic field assignment across a known key union
                    initial[key] = val != null ? String(val) : "";
                  }
                  setEditValues(initial);
                }
              }}
            />

            {/* Module 4 & 5 Document Type Classification & Field Validation */}
            <DocumentValidationPanel certificateId={id} ocrData={ocrData} />

            {/* Document Comparison Section */}
            <DocumentComparisonSection cert={cert} />
          </div>
        )}

        {!ocrData && (
          <div className="bg-white rounded-xl p-8 text-center border border-dashed border-slate-300 shadow-sm">
            <ScanLine className="mx-auto mb-3 text-primary opacity-60" size={36} />
            <p className="text-slate-900 font-semibold mb-1">OCR Processing Pending</p>
            <p className="text-sm text-slate-500 mb-4 max-w-md mx-auto">
              Execute optical character recognition to extract student records, grades, and security credentials into the verification pipeline.
            </p>
            <button
              onClick={handleRunOcr}
              disabled={running}
              className="rounded-lg bg-primary hover:bg-primary-hover disabled:opacity-60 text-white font-medium px-5 py-2.5 transition inline-flex items-center gap-2 text-sm shadow-sm"
            >
              {running && <Loader2 size={16} className="animate-spin" />}
              {running ? (ocrStage ?? "Processing OCR...") : "Run OCR Extraction"}
            </button>
          </div>
        )}
      </div>
    )}

    {/* ── TAB 2: AI FORENSIC COCKPIT (FIGMA SCREEN 4 MEGA-SCREEN) ── */}
    {activeTab === "cockpit" && (
      <div className="space-y-6">
        {/* Prominent Complete Verification Result Card */}
        <CompleteVerificationResultCard
          prediction={prediction}
          trustScore={trustScore}
          fraud={fraudAnalysis}
          verification={verification}
          ocrData={ocrData}
          docType={docType}
          validation={validation}
          report={report}
          cert={cert}
          onViewReport={() => {
            const el = document.getElementById("verification-report-section");
            if (el) el.scrollIntoView({ behavior: "smooth" });
          }}
          onDownloadReport={handleDownloadReport}
          downloadingReport={downloadingReport}
        />

        {/* Top Verdict Mega-Card with Trust Gauge and Fraud Index */}
        <FinalVerdictMegaCard
          prediction={prediction}
          trustScore={trustScore}
          fraud={fraudAnalysis}
          onPredict={handlePredict}
          onComputeTrust={handleComputeTrustScore}
          predicting={predicting}
          computingTrust={computingTrust}
        />

        {/* 2-Column Inspection Grid: Left Canvas & Verification Quadrant, Right Extracted Fields Table */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left 7 Columns: Canvas Preview & Forensic Quadrant */}
          <div className="lg:col-span-7 space-y-6">
            <DocumentPreviewCanvas
              certificateId={id}
              filename={cert?.original_filename}
              fileType={cert?.file_type}
              hasElaHeatmap={!!verification?.ela_heatmap_path}
            />

            <div id="verification-section">
              <ForensicSignalsGrid
                verification={verification}
                certificateId={id}
                onVerifyQr={handleVerifyQr}
                onVerifyBlockchain={handleVerifyBlockchain}
                onVerifyTampering={handleVerifyTampering}
                onVerifyDuplicate={handleVerifyDuplicate}
                verifyingQr={verifyingQr}
                verifyingChain={verifyingChain}
                verifyingTampering={verifyingTampering}
                verifyingDuplicate={verifyingDuplicate}
              />
            </div>
          </div>

          {/* Right 5 Columns: OCR Extracted Fields & Validation Schema */}
          <div className="lg:col-span-5 space-y-6">
            <OcrExtractionTable
              ocrData={ocrData}
              editValues={editValues}
              onChangeField={(key: keyof OCRDataUpdate, value: string) =>
                setEditValues((prev) => ({ ...prev, [key]: value }))
              }
              onSave={handleSaveCorrections}
              onReset={() => {
                if (ocrData) {
                  const initial: OCRDataUpdate = {};
                  for (const [key] of FIELD_LABELS) {
                    const val = (ocrData as unknown as Record<string, unknown>)[key];
                    // @ts-expect-error - dynamic field assignment across a known key union
                    initial[key] = val != null ? String(val) : "";
                  }
                  setEditValues(initial);
                }
              }}
              saving={saving}
              validation={validation}
            />

            {/* Multi-Document Group Comparison Section */}
            <DocumentComparisonSection cert={cert} />
          </div>
        </div>

        {/* Consolidated AI Evidence Factor Matrix & Bayesian Reasoning */}
        <div id="ai-analysis-section">
          <AiEvidencePanel
            prediction={prediction}
            fraud={fraudAnalysis}
            trustScore={trustScore}
          />
        </div>

        {/* Chronological Audit Ledger & Pipeline History */}
        <AuditLedgerTimeline
          pipeline={pipeline}
          cert={cert}
          ocr={ocrData}
          verification={verification}
          fraud={fraudAnalysis}
          trustScore={trustScore}
          prediction={prediction}
          report={report}
        />

        {/* Verification Report & Export Dossier (Figma Screen 5) */}
        <VerificationReportPanel
          report={report}
          prediction={prediction}
          cert={cert}
          verification={verification}
          fraud={fraudAnalysis}
          trustScore={trustScore}
          ocrData={ocrData}
          onGenerateReport={handleGenerateReport}
          onDownloadReport={handleDownloadReport}
          generatingReport={generatingReport}
          downloadingReport={downloadingReport}
        />
      </div>
    )}
  </main>
);
}

function VerificationStatusLine({
  present, valid, warning, absentLabel,
}: { present: boolean; valid?: boolean; warning?: string; absentLabel: string }) {
  if (!present) {
    return (
      <p className="text-xs text-suspicious flex items-center gap-1 mb-3">
        <CircleHelp size={14} /> {absentLabel}
      </p>
    );
  }
  return (
    <div className="mb-3">
      <p className={`text-xs flex items-center gap-1 ${valid ? "text-genuine" : "text-fake"}`}>
        {valid ? <CircleCheck size={14} /> : <CircleX size={14} />}
        {valid ? "Valid" : "Issues found"}
      </p>
      {warning && (
        <p className="text-xs text-gray-500 mt-1 flex items-start gap-1">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" /> {warning}
        </p>
      )}
    </div>
  );
}

function VerdictCard({ prediction }: { prediction: FinalPredictionResponse }) {
  const configMap: Record<string, { icon: any; color: string; bg: string; border: string; label: string; emoji: string }> = {
    genuine: { icon: ShieldCheck, color: "text-genuine", bg: "bg-genuine/10", border: "border-genuine/30", label: "Genuine", emoji: "✅" },
    suspicious: { icon: ShieldAlert, color: "text-suspicious", bg: "bg-suspicious/10", border: "border-suspicious/30", label: "Suspicious", emoji: "⚠️" },
    inconclusive: { icon: ShieldAlert, color: "text-amber-600", bg: "bg-amber-500/10", border: "border-amber-500/30", label: "Needs Review", emoji: "⚠️" },
    "inconclusive / needs review": { icon: ShieldAlert, color: "text-amber-600", bg: "bg-amber-500/10", border: "border-amber-500/30", label: "Needs Review", emoji: "⚠️" },
    fake: { icon: ShieldX, color: "text-fake", bg: "bg-fake/10", border: "border-fake/30", label: "Fake", emoji: "❌" },
  };
  const config = configMap[prediction.label.toLowerCase()] || {
    icon: ShieldAlert,
    color: "text-amber-600",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
    label: prediction.label || "Needs Review",
    emoji: "⚠️",
  };

  const Icon = config.icon;
  const summary = prediction.verification_summary;
  const summaryItems: [string, boolean][] = summary
    ? [
      ["Document Type Identified", summary.document_type_identified],
      ["OCR Extracted", summary.ocr_extracted],
      ["Document Comparison", summary.document_comparison_run],
      ["QR Checked", summary.qr_checked],
      ["Blockchain Checked", summary.blockchain_checked],
      ["Tampering Checked", summary.tampering_checked],
      ["Duplicate Checked", summary.duplicate_checked],
      ["Fraud Analyzed", summary.fraud_analyzed],
      ["Trust Score Computed", summary.trust_score_computed],
    ]
    : [];

  return (
    <div className={`glass-panel rounded-xl p-6 border ${config.border}`}>
      <div className={`flex items-center gap-3 rounded-lg p-4 mb-4 ${config.bg}`}>
        <Icon className={config.color} size={32} />
        <div>
          <p className={`text-xl font-bold ${config.color}`}>{config.emoji} {config.label}</p>
          <p className="text-xs text-gray-400">Confidence: {Math.round(prediction.confidence_score * 100)}%</p>
        </div>
      </div>

      <p className="text-sm text-gray-300 mb-4">{prediction.explanation}</p>

      <div className={`rounded-lg p-3 mb-4 text-sm ${config.bg} ${config.color}`}>
        <strong>Recommended Action:</strong> {prediction.recommended_action}
      </div>

      {summaryItems.length > 0 && (
        <div>
          <p className="text-xs text-gray-500 mb-2">Verification Summary:</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {summaryItems.map(([label, done]) => (
              <div key={label} className="flex items-center gap-1.5 text-xs text-gray-400">
                {done ? <CircleCheck size={12} className="text-genuine shrink-0" /> : <CircleHelp size={12} className="text-gray-600 shrink-0" />}
                {label}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TrustGauge({ score }: { score: number }) {
  const [animated, setAnimated] = useState(0);
  useEffect(() => {
    const timer = setTimeout(() => setAnimated(score), 100);
    return () => clearTimeout(timer);
  }, [score]);

  const color = score >= 80 ? "#16a34a" : score >= 50 ? "#d97706" : "#dc2626";
  const label = score >= 80 ? "Genuine" : score >= 50 ? "Suspicious" : "Fake";
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const arcFraction = 0.75; // 270-degree gauge, leaving a gap at the bottom
  const arcLength = circumference * arcFraction;
  const offset = arcLength - (animated / 100) * arcLength;

  return (
    <div className="relative shrink-0" style={{ width: 140, height: 140 }}>
      <svg width="140" height="140" viewBox="0 0 140 140">
        <circle
          cx="70" cy="70" r={radius} fill="none" stroke="#E2E8F0" strokeWidth="10"
          strokeDasharray={`${arcLength} ${circumference}`}
          strokeDashoffset={0}
          strokeLinecap="round"
          transform="rotate(135 70 70)"
        />
        <circle
          cx="70" cy="70" r={radius} fill="none" stroke={color} strokeWidth="10"
          strokeDasharray={`${arcLength} ${circumference}`}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(135 70 70)"
          style={{ transition: "stroke-dashoffset 1s ease-out" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold text-slate-900">{Math.round(animated)}</span>
        <span className="text-xs font-medium" style={{ color }}>{label}</span>
      </div>
    </div>
  );
}

function trustBarColor(value: number): string {
  if (value >= 80) return "bg-genuine";
  if (value >= 50) return "bg-suspicious";
  return "bg-fake";
}

function fraudRiskColor(probability: number): string {
  if (probability < 0.3) return "text-genuine";
  if (probability < 0.6) return "text-suspicious";
  return "text-fake";
}

function TamperingScoreLine({ score }: { score: number }) {
  const color = score < 30 ? "text-genuine" : score < 60 ? "text-suspicious" : "text-fake";
  const label = score < 30 ? "Low tampering risk" : score < 60 ? "Some indicators found" : "High tampering risk";
  return (
    <p className={`text-xs flex items-center gap-1 ${color}`}>
      {score < 30 ? <CircleCheck size={14} /> : <CircleX size={14} />}
      {label} ({Math.round(score)}/100)
    </p>
  );
}

function BlockchainStatusLine({ status }: { status: string }) {
  const map: Record<string, { label: string; color: string }> = {
    verified: { label: "Hash matches blockchain record", color: "text-genuine" },
    not_found: { label: "Hash not found on-chain", color: "text-suspicious" },
    mismatch: { label: "Hash mismatch — possible tampering", color: "text-fake" },
    unavailable: { label: "Blockchain unavailable (not configured or unreachable)", color: "text-gray-500" },
  };
  const info = map[status] || { label: status, color: "text-gray-400" };
  return <p className={`text-xs flex items-center gap-1 mb-3 ${info.color}`}>{info.label}</p>;
}

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.8 ? "text-genuine border-genuine/30 bg-genuine/10"
    : value >= 0.5 ? "text-suspicious border-suspicious/30 bg-suspicious/10"
      : "text-fake border-fake/30 bg-fake/10";
  return (
    <span className={`text-xs rounded-full px-2 py-0.5 border ${color}`}>
      {value > 0 ? `${pct}%` : "—"}
    </span>
  );
}

// ── Evidence Breakdown Panel ─────────────────────────────────────────────────

function EvidenceBreakdownPanel({
  evidence,
  reasons,
  fraudProbability,
}: {
  evidence: EvidenceBreakdown;
  reasons?: string[];
  fraudProbability?: number;
}) {
  const FACTORS: Array<{ key: keyof EvidenceBreakdown; label: string }> = [
    { key: "ocr", label: "OCR Confidence" },
    { key: "classification", label: "Doc Classification" },
    { key: "field_extraction", label: "Field Extraction" },
    { key: "comparison", label: "Doc Comparison" },
    { key: "qr", label: "QR Verification" },
    { key: "blockchain", label: "Blockchain" },
    { key: "tampering", label: "Tampering Analysis" },
    { key: "duplicate", label: "Duplicate Detection" },
    { key: "metadata", label: "Metadata Integrity" },
  ];

  function statusConfig(status: string) {
    const s = (status || "").toUpperCase();
    if (["PASS", "VERIFIED", "MATCH", "NOT_FOUND", "LOW_RISK", "CLEAN"].includes(s))
      return { color: "text-genuine", bg: "bg-genuine/10 border-genuine/20", icon: "✓" };
    if (["WARN", "NOT_REGISTERED", "MEDIUM_RISK", "FLAGGED"].includes(s))
      return { color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20", icon: "⚠" };
    if (["FAIL", "INVALID", "MISMATCH", "HIGH_RISK", "DUPLICATE"].includes(s))
      return { color: "text-fake", bg: "bg-fake/10 border-fake/20", icon: "✗" };
    return { color: "text-slate-500", bg: "bg-slate-50 border-slate-200", icon: "—" };
  }

  function displayStatus(factor: EvidenceBreakdown[string]) {
    if (!factor) return "UNAVAILABLE";
    return factor.display_status || factor.status || "UNAVAILABLE";
  }

  function displayScore(factor: EvidenceBreakdown[string]) {
    if (!factor) return null;
    if (factor.score != null) return `${Math.round(factor.score as number)}%`;
    return null;
  }

  return (
    <div className="mt-4 bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
          <ListChecks size={15} className="text-primary" />
          AI Evidence Breakdown
        </h3>
        {fraudProbability != null && (
          <span className={`text-xs font-semibold ${fraudProbability < 0.3 ? "text-genuine" : fraudProbability < 0.6 ? "text-suspicious" : "text-fake"}`}>
            Fraud Risk: {Math.round(fraudProbability * 100)}%
          </span>
        )}
      </div>

      {/* Per-factor grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 mb-4">
        {FACTORS.map(({ key, label }) => {
          const factor = evidence[key];
          const status = displayStatus(factor);
          const score = displayScore(factor);
          const cfg = statusConfig(status);
          return (
            <div key={key} className={`flex items-center justify-between rounded-lg px-3 py-2 border ${cfg.bg}`}>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold ${cfg.color}`}>{cfg.icon}</span>
                <span className="text-xs text-slate-700 font-medium">{label}</span>
              </div>
              <div className="flex items-center gap-1.5">
                {score && <span className="text-xs text-slate-500 font-mono">{score}</span>}
                <span className={`text-xs font-semibold ${cfg.color}`}>
                  {status.replace(/_/g, " ")}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Reasons list */}
      {reasons && reasons.length > 0 && (
        <div>
          <p className="text-xs text-slate-500 mb-2 font-medium">Verification Reasons:</p>
          <ul className="space-y-1">
            {reasons.map((r, i) => {
              const isPass = r.startsWith("✓");
              const isFail = r.startsWith("✗");
              const isWarn = r.startsWith("⚠");
              const color = isPass ? "text-genuine" : isFail ? "text-fake" : isWarn ? "text-suspicious" : "text-slate-600";
              return (
                <li key={i} className={`text-xs ${color} leading-relaxed`}>{r}</li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Enhanced Verification Evidence Panel ──────────────────────────────────────

function EnhancedVerificationPanel({
  verification,
  certId,
}: {
  verification: VerificationResultResponse;
  certId: string;
}) {
  const [enhanced, setEnhanced] = useState<EnhancedVerificationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch composite result whenever verification data is freshly available
  useEffect(() => {
    let cancelled = false;
    async function fetchEnhanced() {
      setLoading(true);
      setError(null);
      try {
        const res = await verificationApi.getEnhanced(certId);
        if (!cancelled) setEnhanced(res.data);
      } catch (e: unknown) {
        if (!cancelled) setError("Could not load enhanced verification summary.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchEnhanced();
    return () => { cancelled = true; };
  }, [certId, verification.blockchain_status, verification.qr_valid, verification.hash_match_status]);

  // ── hash consistency badge ────────────────────────────────────────────────
  const hashStatus = verification.hash_match_status;
  const hashConfig = {
    MATCH: { color: "text-genuine", bg: "bg-genuine/10 border-genuine/20", icon: "✓", label: "SHA-256 Hash Match" },
    MISMATCH: { color: "text-fake", bg: "bg-fake/10 border-fake/20", icon: "✗", label: "SHA-256 Hash Mismatch" },
    NOT_REGISTERED: { color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20", icon: "⚠", label: "Hash Not Registered" },
    NOT_CHECKED: { color: "text-slate-500", bg: "bg-slate-50 border-slate-200", icon: "—", label: "Hash Not Checked" },
  }[hashStatus || "NOT_CHECKED"] ?? { color: "text-slate-500", bg: "bg-slate-50 border-slate-200", icon: "—", label: hashStatus };

  // ── cross-validation badge ────────────────────────────────────────────────
  const cvStatus = verification.cross_validation_status;
  const cvConfig = {
    CONSISTENT: { color: "text-genuine", bg: "bg-genuine/10 border-genuine/20", icon: "✓", label: "QR ↔ OCR Consistent" },
    MISMATCH: { color: "text-fake", bg: "bg-fake/10 border-fake/20", icon: "✗", label: "QR ↔ OCR Mismatch" },
    PARTIAL: { color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20", icon: "⚠", label: "QR ↔ OCR Partial" },
    UNAVAILABLE: { color: "text-slate-500", bg: "bg-slate-50 border-slate-200", icon: "—", label: "Cross-val Unavailable" },
  }[cvStatus || "UNAVAILABLE"] ?? { color: "text-slate-500", bg: "bg-slate-50 border-slate-200", icon: "—", label: cvStatus };

  // ── composite status pill ─────────────────────────────────────────────────
  const compositeConfig: Record<string, { color: string; bg: string; label: string }> = {
    STRONGLY_VERIFIED: { color: "text-genuine", bg: "bg-genuine/15 border-genuine/30", label: "✓✓ Strongly Verified" },
    VERIFIED: { color: "text-genuine", bg: "bg-genuine/10 border-genuine/20", label: "✓ Verified" },
    SUSPICIOUS: { color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20", label: "⚠ Suspicious" },
    HIGH_RISK: { color: "text-fake", bg: "bg-fake/10 border-fake/20", label: "✗ High Risk" },
    INSUFFICIENT_EVIDENCE: { color: "text-slate-500", bg: "bg-slate-50 border-slate-200", label: "— Insufficient Evidence" },
  };
  const compositeStatus = enhanced?.composite_status ?? null;
  const cfg = compositeStatus ? compositeConfig[compositeStatus] : null;

  const hasAnyData = hashStatus || cvStatus;
  if (!hasAnyData && !enhanced) return null;

  return (
    <div className="mt-4 bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
          <ShieldCheck size={15} className="text-primary" />
          Verification Evidence
        </h3>
        {cfg && (
          <span className={`text-xs font-semibold px-3 py-1 rounded-full border ${cfg.color} ${cfg.bg}`}>
            {cfg.label}
          </span>
        )}
        {loading && !cfg && (
          <span className="text-xs text-slate-500 flex items-center gap-1">
            <Loader2 size={11} className="animate-spin" /> Loading composite...
          </span>
        )}
      </div>

      {/* Hash + Cross-validation row */}
      <div className="flex flex-wrap gap-2 mb-3">
        {hashStatus && (
          <span className={`text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-lg border ${hashConfig.bg} ${hashConfig.color}`}>
            <span className="font-bold">{hashConfig.icon}</span>
            {hashConfig.label}
          </span>
        )}
        {cvStatus && (
          <span className={`text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-lg border ${cvConfig.bg} ${cvConfig.color}`}>
            <span className="font-bold">{cvConfig.icon}</span>
            {cvConfig.label}
          </span>
        )}
        {/* QR type badge */}
        {verification.qr_present && verification.qr_decoded_data && (
          <span className="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-lg border bg-slate-50 border-slate-200 text-slate-600">
            QR type: {(verification.qr_decoded_data as Record<string, unknown>)["_qr_type"] as string ?? "detected"}
          </span>
        )}
      </div>

      {/* Cross-validation mismatches */}
      {verification.cross_validation_mismatches && verification.cross_validation_mismatches.length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-slate-500 mb-1.5 font-medium">Cross-validation mismatches:</p>
          <ul className="space-y-1">
            {verification.cross_validation_mismatches.map((m, i) => (
              <li key={i} className="text-xs text-fake flex items-start gap-1.5">
                <span className="font-bold mt-px">✗</span>
                <span>
                  <span className="text-slate-500">{m.field}:</span>{" "}
                  QR <span className="text-slate-900 font-semibold">"{m.qr_value}"</span>{" "}
                  vs OCR <span className="text-slate-900 font-semibold">"{m.ocr_value}"</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Composite detail from /verify-enhanced */}
      {enhanced?.composite_detail && (
        <p className="text-xs text-slate-600 leading-relaxed">{enhanced.composite_detail}</p>
      )}
      {enhanced && (
        <p className="text-xs text-slate-500 mt-1">
          {enhanced.checks_completed}/{enhanced.checks_total} verification checks completed
        </p>
      )}
      {error && <p className="text-xs text-slate-500 mt-1">{error}</p>}
    </div>
  );
}

// ── Tampering Detail Panel ────────────────────────────────────────────────────

function TamperingDetailPanel({
  detail,
  score,
  riskLevel,
  confidence,
  certId,
  hasHeatmap,
}: {
  detail: NonNullable<import("@/lib/api").VerificationResultResponse["tampering_detail"]>;
  score?: number;
  riskLevel?: string;
  confidence?: number;
  certId: string;
  hasHeatmap: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  // ── Risk level pill config ────────────────────────────────────────────────
  const riskConfig: Record<string, { color: string; bg: string }> = {
    LOW: { color: "text-genuine", bg: "bg-genuine/10 border-genuine/20" },
    MINOR_ANOMALIES: { color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20" },
    MODERATE_RISK: { color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20" },
    HIGH_RISK: { color: "text-fake", bg: "bg-fake/10 border-fake/20" },
    VERY_HIGH_RISK: { color: "text-fake", bg: "bg-fake/15 border-fake/30" },
  };
  const rc = riskLevel ? riskConfig[riskLevel] : null;

  // ── Sub-signal score bar ──────────────────────────────────────────────────
  function ScoreBar({ value, invert = false }: { value?: number; invert?: boolean }) {
    if (value == null) return <span className="text-gray-600 text-xs">—</span>;
    const pct = Math.round(invert ? value : value);
    const risk = invert ? pct : (100 - pct);
    const color = risk < 30 ? "bg-genuine" : risk < 60 ? "bg-suspicious" : "bg-fake";
    return (
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
          <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
        </div>
        <span className="text-xs text-slate-500 w-8 text-right font-mono">{pct}</span>
      </div>
    );
  }

  // ── Status badge ─────────────────────────────────────────────────────────
  function StatusBadge({ status, goodValues }: { status?: string; goodValues?: string[] }) {
    if (!status) return <span className="text-slate-400 text-xs">—</span>;
    const isGood = goodValues ? goodValues.includes(status) : (status === "NORMAL" || status === "CONSISTENT" || status === "GOOD");
    const color = isGood ? "text-genuine" : "text-suspicious";
    return <span className={`text-xs font-semibold ${color}`}>{status.replace(/_/g, " ")}</span>;
  }

  const iq = detail.image_quality;
  const ela = detail.ela;
  const cp = detail.copy_paste;
  const font = detail.font_consistency;
  const ta = detail.text_analysis;
  const sig = detail.signature;
  const seal = detail.seal;
  const meta = detail.metadata;
  const struct = detail.document_structure;
  const findings = detail.findings ?? [];
  const anomalousFindings = findings.filter(f => f.status !== "NORMAL" && f.status !== "CONSISTENT" && f.status !== "NOT_FOUND");

  return (
    <div className="mt-4 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Header — always visible */}
      <button
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-slate-50 transition"
        onClick={() => setExpanded(e => !e)}
        id="tampering-detail-toggle"
      >
        <div className="flex items-center gap-3">
          <ShieldAlert size={15} className="text-primary shrink-0" />
          <span className="text-sm font-semibold text-slate-900">Tampering Analysis Detail</span>
          {rc && riskLevel && (
            <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${rc.color} ${rc.bg}`}>
              {riskLevel.replace(/_/g, " ")}
            </span>
          )}
          {score != null && (
            <span className="text-xs text-slate-500 font-mono">Score: {Math.round(score)}/100</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {confidence != null && (
            <span className="text-xs text-slate-400 font-mono">Confidence: {Math.round(confidence)}%</span>
          )}
          <span className="text-xs text-primary font-medium">{expanded ? "▲ Hide" : "▼ Show signals"}</span>
        </div>
      </button>

      {expanded && (
        <div className="px-5 pb-5 border-t border-slate-200">

          {/* 3-column signal grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-4">

            {/* Image Quality */}
            {iq && (
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <p className="text-xs font-semibold text-slate-800 mb-2 flex items-center gap-1.5">
                  <Activity size={11} className="text-primary" /> Image Quality
                </p>
                <ScoreBar value={iq.score} />
                <p className="text-xs text-slate-500 mt-1">
                  <StatusBadge status={iq.status} goodValues={["GOOD"]} />
                  {iq.detail && <span className="ml-1 text-slate-600">— {iq.detail}</span>}
                </p>
                {iq.breakdown && (
                  <div className="mt-2 space-y-1">
                    {Object.entries(iq.breakdown).map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between">
                        <span className="text-xs text-slate-500 capitalize">{k}</span>
                        <span className="text-xs text-slate-700 font-mono">{Math.round(v as number)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ELA */}
            {ela && (
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <p className="text-xs font-semibold text-slate-800 mb-2 flex items-center gap-1.5">
                  <Gauge size={11} className="text-primary" /> ELA Compression
                </p>
                <ScoreBar value={ela.risk} invert />
                <p className="text-xs text-slate-500 mt-1">
                  <StatusBadge status={ela.status} goodValues={["NORMAL"]} />
                  <span className="ml-1 text-slate-600 font-mono">raw: {ela.score?.toFixed(1)}</span>
                </p>
                {hasHeatmap && (
                  <a
                    href={verificationApi.elaHeatmapUrl(certId)}
                    target="_blank" rel="noreferrer"
                    className="text-xs text-primary hover:underline mt-1 inline-block"
                  >View ELA heatmap ↗</a>
                )}
              </div>
            )}

            {/* Copy-Paste */}
            {cp && (
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <p className="text-xs font-semibold text-slate-800 mb-2 flex items-center gap-1.5">
                  <Copy size={11} className="text-primary" /> Copy-Paste
                </p>
                <ScoreBar value={cp.score} invert />
                <p className="text-xs mt-1">
                  {cp.detected
                    ? <span className="text-fake font-semibold">Detected ({cp.cluster_size} keypoint pairs)</span>
                    : <span className="text-genuine font-semibold">None detected (cluster: {cp.cluster_size})</span>
                  }
                </p>
              </div>
            )}

            {/* Font Consistency */}
            {font && (
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <p className="text-xs font-semibold text-slate-800 mb-2 flex items-center gap-1.5">
                  <FileText size={11} className="text-primary" /> Font Consistency
                </p>
                <ScoreBar value={font.score} />
                <p className="text-xs text-slate-500 mt-1">
                  <StatusBadge status={font.status} goodValues={["CONSISTENT"]} />
                </p>
              </div>
            )}

            {/* Text Analysis (PART E — NEW) */}
            {ta && (
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <p className="text-xs font-semibold text-slate-800 mb-2 flex items-center gap-1.5">
                  <ListChecks size={11} className="text-primary" /> Text Layout
                </p>
                <ScoreBar value={ta.score} />
                <p className="text-xs text-slate-500 mt-1">
                  <StatusBadge status={ta.status} goodValues={["NORMAL"]} />
                  {ta.detail && <span className="ml-1 text-slate-600">— {ta.detail}</span>}
                </p>
                {(ta.line_count != null || ta.spacing_cv != null) && (
                  <div className="mt-1 text-xs text-slate-500 space-y-0.5 font-mono">
                    {ta.line_count != null && <p>Lines: {ta.line_count}</p>}
                    {ta.spacing_cv != null && <p>Spacing CV: {ta.spacing_cv.toFixed(3)}</p>}
                    {ta.density_cv != null && <p>Density CV: {ta.density_cv.toFixed(3)}</p>}
                  </div>
                )}
              </div>
            )}

            {/* Signature */}
            {sig && (
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <p className="text-xs font-semibold text-slate-800 mb-2 flex items-center gap-1.5">
                  <Pencil size={11} className="text-primary" /> Signature
                </p>
                <p className="text-xs text-slate-600 mb-1">
                  {sig.detected ? "Detected" : "Not found"}
                </p>
                {sig.detected && (
                  <ScoreBar value={sig.anomaly_score} invert />
                )}
                {sig.reason && (
                  <p className="text-xs text-slate-500 mt-1">{sig.reason}</p>
                )}
              </div>
            )}

            {/* Seal */}
            {seal && (
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <p className="text-xs font-semibold text-slate-800 mb-2 flex items-center gap-1.5">
                  <ShieldCheck size={11} className="text-primary" /> Seal / Stamp
                </p>
                <p className="text-xs text-slate-600 mb-1">
                  {seal.detected ? "Detected" : "Not found"}
                </p>
                {seal.detected && (
                  <ScoreBar value={seal.anomaly_score} invert />
                )}
                {seal.reason && (
                  <p className="text-xs text-slate-500 mt-1">{seal.reason}</p>
                )}
              </div>
            )}

            {/* Metadata */}
            {meta && (
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <p className="text-xs font-semibold text-slate-800 mb-2 flex items-center gap-1.5">
                  <Download size={11} className="text-primary" /> Metadata
                </p>
                <StatusBadge status={meta.status} goodValues={["NORMAL"]} />
                {meta.anomalies && meta.anomalies.length > 0 && (
                  <ul className="mt-1 space-y-0.5">
                    {meta.anomalies.map((a, i) => (
                      <li key={i} className="text-xs text-suspicious flex gap-1">
                        <span>⚠</span><span>{a}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* Document Structure */}
            {struct && (
              <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <p className="text-xs font-semibold text-slate-800 mb-2 flex items-center gap-1.5">
                  <ListChecks size={11} className="text-primary" /> Doc Structure
                </p>
                <ScoreBar value={struct.anomaly_score} invert />
                {struct.missing_fields && struct.missing_fields.length > 0 && (
                  <p className="text-xs text-suspicious mt-1">
                    Missing: {struct.missing_fields.join(", ")}
                  </p>
                )}
                {struct.reason && (
                  <p className="text-xs text-slate-500 mt-0.5">{struct.reason}</p>
                )}
              </div>
            )}
          </div>

          {/* Anomalous findings list */}
          {anomalousFindings.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1.5">
                <AlertTriangle size={11} className="text-suspicious" /> Anomaly Findings
              </p>
              <ul className="space-y-2">
                {anomalousFindings.map((f, i) => (
                  <li key={i} className="text-xs bg-slate-50 rounded-lg px-3 py-2 border border-slate-200 shadow-xs">
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-slate-900 font-semibold capitalize">{f.type.replace(/_/g, " ")}</span>
                      <div className="flex items-center gap-2 font-mono">
                        <span className="text-slate-500">score {Math.round(f.score)}</span>
                        <span className="text-slate-400">conf {Math.round(f.confidence)}%</span>
                      </div>
                    </div>
                    <p className="text-slate-600">{f.reason}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Decision rules reminder */}
          <p className="text-xs text-slate-400 mt-4 italic">
            Note: No single anomaly automatically classifies a document as fake.
            Multiple strong signals are required for a HIGH RISK determination.
          </p>
        </div>
      )}
    </div>
  );
}

// ── DuplicateDetailPanel ──────────────────────────────────────────────────────

function DuplicateDetailPanel({
  detail,
}: {
  detail: NonNullable<import("@/lib/api").VerificationResultResponse["duplicate_detail"]>;
}) {
  const [expanded, setExpanded] = useState(false);

  // Status → display config
  const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: string }> = {
    NO_DUPLICATE: { label: "No Duplicate", color: "text-genuine", bg: "bg-genuine/10 border-genuine/20", icon: "✓" },
    EXACT_FILE_DUPLICATE: { label: "Exact File Duplicate", color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20", icon: "⚠" },
    DUPLICATE_UPLOAD: { label: "Duplicate Upload", color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20", icon: "↺" },
    DUPLICATE_CERTIFICATE: { label: "Duplicate Certificate", color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20", icon: "⚠" },
    POSSIBLE_DUPLICATE: { label: "Possible Duplicate", color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20", icon: "?" },
    CERTIFICATE_CONFLICT: { label: "Certificate Conflict", color: "text-fake", bg: "bg-fake/10 border-fake/20", icon: "✗" },
    QR_DUPLICATE: { label: "QR Duplicate", color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20", icon: "⚠" },
    BLOCKCHAIN_DUPLICATE: { label: "Blockchain Duplicate", color: "text-suspicious", bg: "bg-suspicious/10 border-suspicious/20", icon: "⛓" },
  };

  const cfg = STATUS_CONFIG[detail.duplicate_status] ?? STATUS_CONFIG["NO_DUPLICATE"];
  const isConflict = detail.duplicate_status === "CERTIFICATE_CONFLICT";
  const isClean = detail.duplicate_status === "NO_DUPLICATE";

  function ConfidenceBar({ value }: { value: number }) {
    const color = value >= 80 ? "bg-fake" : value >= 50 ? "bg-suspicious" : "bg-genuine";
    return (
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
          <div className={`h-full rounded-full ${color}`} style={{ width: `${value}%` }} />
        </div>
        <span className="text-xs text-slate-500 w-10 text-right font-mono">{value.toFixed(0)}%</span>
      </div>
    );
  }

  function SignalFlag({ active, label }: { active: boolean; label: string }) {
    return (
      <div className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md border font-medium ${active
          ? "border-amber-200 bg-amber-50 text-amber-700 font-semibold"
          : "border-slate-200 bg-slate-50 text-slate-500"
        }`}>
        <span>{active ? "⚠" : "✓"}</span>
        <span>{label}</span>
      </div>
    );
  }

  return (
    <div className="mt-4 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Header */}
      <button
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-slate-50 transition"
        onClick={() => setExpanded(e => !e)}
        id="duplicate-detail-toggle"
      >
        <div className="flex items-center gap-3">
          <Copy size={15} className="text-primary shrink-0" />
          <span className="text-sm font-semibold text-slate-900">Duplicate Detection Detail</span>
          <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${cfg.color} ${cfg.bg}`}>
            {cfg.icon} {cfg.label}
          </span>
          {detail.duplicate_detected && (
            <span className="text-xs text-slate-500 font-mono">
              Confidence: {detail.confidence.toFixed(0)}%
            </span>
          )}
        </div>
        <span className="text-xs text-primary font-medium">{expanded ? "▲ Hide" : "▼ Show detail"}</span>
      </button>

      {expanded && (
        <div className="px-5 pb-5 border-t border-slate-200">
          {/* Confidence */}
          {detail.duplicate_detected && (
            <div className="mt-4">
              <p className="text-xs text-slate-500 mb-1">Match Confidence</p>
              <ConfidenceBar value={detail.confidence} />
            </div>
          )}

          {/* Signal flags grid */}
          <div className="mt-4">
            <p className="text-xs font-semibold text-slate-700 mb-2">Detection Signals</p>
            <div className="flex flex-wrap gap-2">
              <SignalFlag active={detail.file_hash_match} label="File Hash" />
              <SignalFlag active={detail.certificate_number_match} label="Cert Number" />
              <SignalFlag active={detail.registration_number_match} label="Reg/Roll Number" />
              <SignalFlag active={detail.qr_match} label="QR Payload" />
              {detail.field_similarity > 0 && (
                <div className="text-xs px-2.5 py-1 rounded-md border border-slate-200 bg-slate-50 text-slate-600 font-mono">
                  Field Similarity: {detail.field_similarity.toFixed(0)}%
                </div>
              )}
              {detail.visual_similarity > 0 && (
                <div className="text-xs px-2.5 py-1 rounded-md border border-slate-200 bg-slate-50 text-slate-600 font-mono">
                  Visual Similarity: {detail.visual_similarity.toFixed(0)}%
                </div>
              )}
            </div>
          </div>

          {/* Field similarity bars */}
          {(detail.field_similarity > 0 || detail.visual_similarity > 0) && (
            <div className="mt-4 space-y-2">
              <p className="text-xs font-semibold text-slate-700 mb-2">Similarity Analysis</p>
              {detail.field_similarity > 0 && (
                <div>
                  <p className="text-xs text-slate-500 mb-1">Fuzzy Field Similarity</p>
                  <ConfidenceBar value={detail.field_similarity} />
                </div>
              )}
              {detail.visual_similarity > 0 && (
                <div>
                  <p className="text-xs text-slate-500 mb-1">Visual Similarity (dHash)</p>
                  <ConfidenceBar value={detail.visual_similarity} />
                </div>
              )}
            </div>
          )}

          {/* Matched fields */}
          {detail.matched_fields.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
                <CircleCheck size={11} className="text-amber-600" /> Matched Fields
              </p>
              <div className="flex flex-wrap gap-1.5">
                {detail.matched_fields.map(f => (
                  <span key={f} className="text-xs px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-medium">
                    {f.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Conflicting fields */}
          {detail.conflicting_fields.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
                <CircleX size={11} className="text-rose-600" /> Conflicting Fields
              </p>
              <div className="flex flex-wrap gap-1.5">
                {detail.conflicting_fields.map(f => (
                  <span key={f} className="text-xs px-2.5 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 font-medium">
                    {f.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Same owner indicator */}
          <div className="mt-4 flex items-center gap-2">
            <span className="text-xs text-slate-500">Same Account Re-upload:</span>
            <span className={`text-xs font-semibold ${detail.same_owner ? "text-genuine" : "text-slate-500"}`}>
              {detail.same_owner ? "Yes — benign re-upload" : "No / Unknown"}
            </span>
          </div>

          {/* Matched certificate link */}
          {detail.matched_certificate_id && (
            <div className="mt-3">
              <p className="text-xs text-slate-500">
                Matched Certificate:{" "}
                <a
                  href={`/dashboard/certificates/${detail.matched_certificate_id}`}
                  className="text-primary hover:underline font-mono font-medium"
                >
                  {detail.matched_certificate_id.slice(0, 16)}…
                </a>
              </p>
            </div>
          )}

          {/* Reason */}
          <div className="mt-4 bg-slate-50 rounded-lg px-3 py-2 border border-slate-200">
            <p className="text-xs text-slate-600 italic">{detail.reason}</p>
          </div>

          {/* Conflict warning */}
          {isConflict && (
            <div className="mt-3 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2 flex items-start gap-2">
              <AlertTriangle size={13} className="text-rose-600 mt-0.5 shrink-0" />
              <p className="text-xs text-rose-700">
                Certificate number matches an existing record but identity fields conflict.
                This is treated as strong suspicious evidence in the fraud analysis.
              </p>
            </div>
          )}

          {/* Clean indicator */}
          {isClean && (
            <div className="mt-3 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 flex items-center gap-2">
              <CircleCheck size={13} className="text-emerald-600" />
              <p className="text-xs text-emerald-700 font-medium">No duplicate or conflicting certificate found in the system.</p>
            </div>
          )}

          <p className="text-xs text-slate-400 mt-4 italic">
            Note: Duplicate detection considers file hash, certificate number, registration number,
            QR data, fuzzy field similarity, and visual appearance (dHash).
          </p>
        </div>
      )}
    </div>
  );
}

// ── VerificationPipelinePanel ─────────────────────────────────────────────────
// Priority 8 (PART B/C) — per-certificate pipeline timeline

function VerificationPipelinePanel({ certificateId }: { certificateId: string }) {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pipeline, setPipeline] = useState<PipelineStatusResponse | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  async function loadPipeline() {
    if (pipeline) { setExpanded(e => !e); return; }
    setExpanded(true);
    setLoading(true);
    try {
      const { data } = await pipelineApi.status(certificateId);
      setPipeline(data);
    } catch {
      setFetchError("Failed to load pipeline status.");
    } finally {
      setLoading(false);
    }
  }

  const STATUS_CHIP: Record<string, { label: string; cls: string }> = {
    COMPLETED: { label: "✓ Completed", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    PENDING: { label: "· Pending", cls: "bg-slate-100 text-slate-500 border-slate-200" },
    FAILED: { label: "✗ Failed", cls: "bg-rose-50 text-rose-700 border-rose-200" },
    UNAVAILABLE: { label: "— N/A", cls: "bg-slate-50 text-slate-400 border-slate-200" },
  };

  return (
    <div className="mb-4 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Header toggle */}
      <button
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-slate-50 transition"
        onClick={loadPipeline}
        id="pipeline-status-toggle"
      >
        <div className="flex items-center gap-2">
          <ListChecks size={14} className="text-primary shrink-0" />
          <span className="text-sm font-semibold text-slate-900">Verification Pipeline Status</span>
          {pipeline && (
            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ml-1 ${pipeline.overall_status === "FULLY_COMPLETE" ? "text-emerald-700 bg-emerald-50 border-emerald-200"
                : pipeline.overall_status === "NOT_STARTED" ? "text-slate-500 bg-slate-50 border-slate-200"
                  : "text-amber-700 bg-amber-50 border-amber-200"
              }`}>
              {pipeline.completion_pct.toFixed(0)}% complete
            </span>
          )}
        </div>
        <span className="text-xs text-primary font-medium">{expanded ? "▲ Hide" : "▼ Show stages"}</span>
      </button>

      {expanded && (
        <div className="border-t border-slate-200 px-5 pb-5">
          {loading && (
            <div className="flex items-center gap-2 text-xs text-slate-500 mt-4">
              <Loader2 size={12} className="animate-spin text-primary" /> Loading pipeline…
            </div>
          )}
          {fetchError && (
            <p className="text-xs text-fake mt-4">{fetchError}</p>
          )}
          {pipeline && !loading && (
            <>
              {/* Progress bar */}
              <div className="mt-4 mb-5">
                <div className="flex justify-between text-xs text-slate-500 mb-1 font-mono">
                  <span>{pipeline.overall_status.replace(/_/g, " ")}</span>
                  <span>{pipeline.completion_pct.toFixed(0)}%</span>
                </div>
                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-primary to-emerald-500 transition-all"
                    style={{ width: `${pipeline.completion_pct}%` }}
                  />
                </div>
              </div>

              {/* Stage rows */}
              <div className="relative">
                {/* Vertical connector line */}
                <div className="absolute left-3 top-3 bottom-3 w-px bg-slate-200" />

                <div className="space-y-3">
                  {pipeline.stages.map((stage: PipelineStage) => {
                    const chip = STATUS_CHIP[stage.status] ?? STATUS_CHIP.PENDING;
                    const isCompleted = stage.status === "COMPLETED";
                    return (
                      <div key={stage.stage} className="flex items-start gap-3 pl-2">
                        {/* Timeline dot */}
                        <div className={`mt-1 w-4 h-4 rounded-full flex items-center justify-center shrink-0 z-10 border ${isCompleted ? "bg-emerald-50 border-emerald-500"
                            : stage.status === "UNAVAILABLE" ? "bg-slate-50 border-slate-200"
                              : "bg-slate-100 border-slate-300"
                          }`}>
                          {isCompleted && <Check size={9} className="text-emerald-700" />}
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-semibold text-slate-900">{stage.label}</span>
                            <span className={`text-xs px-1.5 py-0.5 rounded border font-mono ${chip.cls}`}>
                              {chip.label}
                            </span>
                          </div>
                          {stage.summary && (
                            <p className="text-xs text-slate-500 mt-0.5 truncate">{stage.summary}</p>
                          )}
                          {stage.completed_at && (
                            <p className="text-[10px] text-slate-400 font-mono mt-0.5">
                              {new Date(stage.completed_at).toLocaleString("en-IN", {
                                day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
                              })}
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── DocumentValidationPanel ──────────────────────────────────────────────────
// Module 4 & 5 document type classification & document-specific field validation panel

function DocumentValidationPanel({
  certificateId,
  ocrData,
}: {
  certificateId: string;
  ocrData: OCRDataResponse;
}) {
  const [validation, setValidation] = useState<import("@/lib/api").DocumentValidationResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    ocrApi
      .validate(certificateId)
      .then((res) => { if (active) setValidation(res.data); })
      .catch(() => { if (active) setValidation(null); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [certificateId, ocrData]);

  if (loading && !validation) {
    return (
      <div className="bg-white rounded-xl p-4 mt-6 text-xs text-slate-500 border border-slate-200 flex items-center gap-2">
        <Loader2 size={14} className="animate-spin text-primary" /> Validating extracted fields against document schema...
      </div>
    );
  }

  if (!validation) return null;

  const statusBadges: Record<string, { label: string; cls: string }> = {
    VALID: { label: "✓ VALID", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    INVALID: { label: "✗ INVALID", cls: "bg-rose-50 text-rose-700 border-rose-200" },
    LOW_CONFIDENCE: { label: "⚠ REVIEW", cls: "bg-amber-50 text-amber-700 border-amber-200" },
    MISSING: { label: "— MISSING", cls: "bg-slate-50 text-slate-500 border-slate-200" },
    NOT_DETECTED: { label: "— NOT DETECTED", cls: "bg-slate-50 text-slate-400 border-slate-200" },
    NOT_APPLICABLE: { label: "— N/A", cls: "bg-slate-50 text-slate-400 border-slate-200" },
  };

  const formattedType = validation.document_type
    .split("_")
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

  return (
    <div className="mt-6 bg-white rounded-xl p-5 border border-slate-200 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-slate-500">Document Type:</span>
            <span className="text-sm font-bold text-slate-900">{formattedType}</span>
            <span className="text-xs rounded-full px-2.5 py-0.5 bg-indigo-50 text-indigo-700 border border-indigo-200 font-medium">
              {Math.round(validation.classification_confidence * 100)}% Confidence
            </span>
          </div>
          <p className="text-xs text-slate-500">
            Field validation schema for {formattedType}
          </p>
        </div>
      </div>

      <div className="mb-4">
        <p className="text-xs font-medium text-slate-700 mb-2">Expected Schema Fields:</p>
        <div className="flex flex-wrap gap-1.5">
          {validation.expected_fields.map((f, i) => (
            <span key={i} className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
              {f}
            </span>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200">
        <table className="w-full text-xs">
          <thead className="bg-slate-50 text-slate-600 text-left font-medium border-b border-slate-200">
            <tr>
              <th className="px-3.5 py-2 font-medium">Field</th>
              <th className="px-3.5 py-2 font-medium">Extracted Value</th>
              <th className="px-3.5 py-2 font-medium w-24">Confidence</th>
              <th className="px-3.5 py-2 font-medium w-28">Validation Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {validation.field_validations.map((item) => {
              const badge = statusBadges[item.status] || statusBadges.MISSING;
              return (
                <tr key={item.field} className="hover:bg-slate-50/50">
                  <td className="px-3.5 py-2 text-slate-700 font-medium">{item.label}</td>
                  <td className="px-3.5 py-2 text-slate-900 font-mono">{item.extracted_value || "—"}</td>
                  <td className="px-3.5 py-2">
                    <ConfidenceBadge value={item.confidence} />
                  </td>
                  <td className="px-3.5 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium inline-block ${badge.cls}`}>
                      {badge.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── DocumentComparisonSection ────────────────────────────────────────────────
// Displays comparison status for multi-document sets or explicit unavailable state

function DocumentComparisonSection({ cert }: { cert: CertificateResponse | null }) {
  if (!cert) return null;

  if (!cert.group_id) {
    return (
      <div className="mt-6 bg-white rounded-xl p-4 border border-slate-200 shadow-sm flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ListChecks size={16} className="text-slate-400" />
          <div>
            <p className="text-xs font-semibold text-slate-700">Document Comparison</p>
            <p className="text-xs text-slate-500">Unavailable / Not applicable (Single document uploaded)</p>
          </div>
        </div>
        <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-500 border border-slate-200 font-medium">
          Single Doc
        </span>
      </div>
    );
  }

  return (
    <div className="mt-6 bg-white rounded-xl p-4 border border-slate-200 shadow-sm flex items-center justify-between">
      <div className="flex items-center gap-2">
        <ListChecks size={16} className="text-indigo-600" />
        <div>
          <p className="text-xs font-semibold text-slate-900">Multi-Document Group Active</p>
          <p className="text-xs text-slate-500">
            Group ID: <span className="font-mono text-slate-700">{cert.group_id.slice(0, 16)}…</span>
          </p>
        </div>
      </div>
      <a
        href={`/dashboard/compare?group_id=${cert.group_id}`}
        className="text-xs text-indigo-600 hover:text-indigo-700 hover:underline font-medium"
      >
        View Full Document Comparison ↗
      </a>
    </div>
  );
}
