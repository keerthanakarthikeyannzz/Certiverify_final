"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useRouter } from "next/navigation";
import { ShieldAlert, CheckCircle2, AlertCircle, X, Cpu, Layers } from "lucide-react";
import {
  certificateApi,
  CertificateResponse,
  getAccessToken,
  authApi,
  documentTypeApi,
  ocrApi,
} from "@/lib/api";
import {
  UploadHeader,
  CertificateDropzone,
  StagedFilesList,
  BlockchainRegistryCard,
  RecentUploadsLedger,
} from "@/components/upload";

export default function UploadPage() {
  const router = useRouter();

  // ── Core State ──────────────────────────────────────────────────────────
  const [pending, setPending] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [certificates, setCertificates] = useState<CertificateResponse[]>([]);
  const [userName, setUserName] = useState<string>("");
  const [docTypes, setDocTypes] = useState<
    Record<string, { label: string; confidence: number } | "loading" | undefined>
  >({});
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // ── Manual Doc-Type Selection ────────────────────────────────────────────
  const [selectedDocType, setSelectedDocType] = useState<string>("");
  const [pendingDocTypes, setPendingDocTypes] = useState<string[]>([]);

  // ── OCR State ───────────────────────────────────────────────────────────
  const [ocrRunning, setOcrRunning] = useState<Record<string, boolean>>({});
  const [certDocTypes, setCertDocTypes] = useState<Record<string, string>>({});

  // ── Bootstrap ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!getAccessToken()) {
      router.push("/login");
      return;
    }
    authApi
      .me()
      .then((res) => setUserName(res.data.full_name))
      .catch(() => router.push("/login"));
    refreshList();
  }, [router]);

  const refreshList = async () => {
    try {
      const { data } = await certificateApi.list();
      setCertificates(data);
      data.forEach((cert) => {
        documentTypeApi
          .get(cert.id)
          .then((res) =>
            setDocTypes((prev) => ({
              ...prev,
              [cert.id]: {
                label: res.data.predicted_type,
                confidence: res.data.confidence_score,
              },
            }))
          )
          .catch(() => {
            // Not classified yet
          });
      });
    } catch {
      // Non-fatal list sync failure
    }
  };

  // ── Dropzone Handlers ────────────────────────────────────────────────────
  const onDrop = useCallback(
    (accepted: File[]) => {
      setPending((prev) => [...prev, ...accepted]);
      setPendingDocTypes((prev) => [
        ...prev,
        ...accepted.map(() => selectedDocType),
      ]);
    },
    [selectedDocType]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
    },
    maxSize: 15 * 1024 * 1024,
  });

  const removePending = (index: number) => {
    setPending((prev) => prev.filter((_, i) => i !== index));
    setPendingDocTypes((prev) => prev.filter((_, i) => i !== index));
  };

  const clearPending = () => {
    setPending([]);
    setPendingDocTypes([]);
    setError(null);
  };

  // ── Upload Execution ─────────────────────────────────────────────────────
  const handleUpload = async () => {
    if (pending.length === 0) return;
    setUploading(true);
    setUploadProgress(15);
    setError(null);
    try {
      const timer = setInterval(() => {
        setUploadProgress((p) => (p < 85 ? p + 15 : p));
      }, 200);

      const { data } = await certificateApi.upload(pending);
      clearInterval(timer);
      setUploadProgress(100);

      data.certificates.forEach((cert, idx) => {
        const dt = pendingDocTypes[idx] || "";
        if (dt) {
          setCertDocTypes((prev) => ({ ...prev, [cert.id]: dt }));
        }
      });
      setPending([]);
      setPendingDocTypes([]);
      await refreshList();
      setToast({
        type: "success",
        message: `Successfully ingested ${data.certificates.length} document(s). Opening verification cockpit...`,
      });

      if (data.certificates.length > 0) {
        const targetId = data.certificates[0].id;
        if (typeof window !== "undefined") {
          localStorage.setItem("cv_current_certificate_id", targetId);
        }
        setTimeout(() => {
          router.push(`/dashboard/certificates/${targetId}`);
        }, 800);
      }
    } catch (err: unknown) {
      setUploadProgress(0);
      let message =
        "Upload failed. Please check file types (PDF/JPG/PNG) and size (max 15 MB) and try again.";
      if (err && typeof err === "object" && "response" in err) {
        const resp = (
          err as { response?: { status?: number; data?: { detail?: string } } }
        ).response;
        if (resp?.status === 401) message = "Session expired. Please log in again.";
        else if (resp?.status === 403)
          message = "Access denied. Please verify your email first.";
        else if (resp?.status === 413)
          message = "File too large. Maximum allowed size is 15 MB.";
        else if (resp?.data?.detail) message = resp.data.detail;
      } else if (err && typeof err === "object" && "code" in err) {
        const code = (err as { code?: string }).code;
        if (code === "ERR_NETWORK")
          message = "Cannot reach the server. Please check your connection.";
        else if (code === "ECONNABORTED")
          message = "Upload timed out. Please try again.";
      }
      setError(message);
    } finally {
      setUploading(false);
      setTimeout(() => setToast(null), 5000);
    }
  };

  // ── OCR Execution ────────────────────────────────────────────────────────
  const handleRunOcr = async (certId: string) => {
    const dt = certDocTypes[certId] || undefined;
    setOcrRunning((prev) => ({ ...prev, [certId]: true }));
    try {
      await ocrApi.extract(certId, dt);
      setToast({
        type: "success",
        message: "Neural OCR extraction complete!",
      });
    } catch {
      setToast({
        type: "error",
        message: "OCR extraction failed. Please try again.",
      });
    } finally {
      setOcrRunning((prev) => ({ ...prev, [certId]: false }));
      setTimeout(() => setToast(null), 4000);
    }
  };

  // ── Delete Execution ─────────────────────────────────────────────────────
  const handleDelete = async (id: string, filename: string) => {
    const confirmed = window.confirm(
      `Are you sure you want to delete "${filename}"?\n\nThis will permanently remove the certificate and all associated forensic data.`
    );
    if (!confirmed) return;

    setDeletingId(id);
    setToast(null);
    try {
      await certificateApi.remove(id);
      setCertificates((prev) => prev.filter((c) => c.id !== id));
      setDocTypes((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      await refreshList();
      setToast({
        type: "success",
        message: `"${filename}" was deleted successfully.`,
      });
    } catch {
      setToast({ type: "error", message: "Failed to delete the certificate." });
    } finally {
      setDeletingId(null);
      setTimeout(() => setToast(null), 4000);
    }
  };

  const latestCertificate = certificates.length > 0 ? certificates[0] : null;

  return (
    <div className="max-w-[1280px] mx-auto space-y-6">
      {/* Toast Notification */}
      {toast && (
        <div
          id="upload-toast"
          className={`fixed top-5 right-5 z-50 flex items-center gap-2.5 px-4 py-3 rounded-xl shadow-xl border text-xs font-semibold transition-all ${
            toast.type === "success"
              ? "bg-white border-emerald-200 text-emerald-800"
              : "bg-white border-red-200 text-red-800"
          }`}
        >
          {toast.type === "success" ? (
            <CheckCircle2 size={16} className="text-emerald-600" />
          ) : (
            <AlertCircle size={16} className="text-red-600" />
          )}
          <span>{toast.message}</span>
          <button
            onClick={() => setToast(null)}
            className="ml-2 text-slate-400 hover:text-slate-700"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* 1. Header Section */}
      <UploadHeader
        userName={userName}
        totalIngested={certificates.length}
      />

      {/* Upload Progress Indicator when active */}
      {uploading && (
        <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-sm space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
            <span>Ingesting document into pipeline...</span>
            <span>{uploadProgress}%</span>
          </div>
          <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-600 rounded-full transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="flex items-start gap-2.5 p-3.5 bg-red-50 border border-red-200 text-red-800 rounded-xl text-xs">
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* 2. Ingestion Workspace: 2-Column Responsive Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Dropzone & Staged Files (7 cols) */}
        <div className="lg:col-span-7 space-y-5">
          <CertificateDropzone
            selectedDocType={selectedDocType}
            onDocTypeChange={setSelectedDocType}
            getRootProps={getRootProps}
            getInputProps={getInputProps}
            isDragActive={isDragActive}
            disabled={uploading}
          />

          <StagedFilesList
            pending={pending}
            pendingDocTypes={pendingDocTypes}
            uploading={uploading}
            onRemove={removePending}
            onClearAll={clearPending}
            onUpload={handleUpload}
          />
        </div>

        {/* Right Column: Pipeline Stepper & Ledger Card (5 cols) */}
        <div className="lg:col-span-5 space-y-5">
          <BlockchainRegistryCard latestCertificate={latestCertificate} />

          {/* Step-by-Step Pipeline Stepper */}
          <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
                  <Layers size={15} />
                </div>
                <h3 className="text-sm font-semibold text-slate-900 tracking-tight">
                  Verification Pipeline Stages
                </h3>
              </div>
              <span className="text-[11px] font-semibold text-indigo-600">
                14 Checks
              </span>
            </div>

            <ol className="space-y-3 text-xs">
              {[
                { stage: "01", name: "SHA-256 Digesting", desc: "Cryptographic hash generation" },
                { stage: "02", name: "Document Classification", desc: "Neural layout classification" },
                { stage: "03", name: "Dual-Engine OCR Fusion", desc: "EasyOCR & Tesseract extraction" },
                { stage: "04", name: "Tamper Forensic ELA", desc: "Error level & metadata inspection" },
                { stage: "05", name: "Duplicate Detection", desc: "Cross-organization register match" },
                { stage: "06", name: "AI Trust Score Computation", desc: "Weighted integrity verdict" },
              ].map((step) => (
                <li key={step.stage} className="flex items-start gap-3">
                  <span className="w-6 h-6 rounded-md bg-slate-100 border border-slate-200 text-slate-700 font-bold text-[10px] flex items-center justify-center shrink-0 mt-0.5">
                    {step.stage}
                  </span>
                  <div>
                    <p className="font-semibold text-slate-800 leading-snug">{step.name}</p>
                    <p className="text-[11px] text-slate-400">{step.desc}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>

      {/* 3. Ingested Credentials Ledger */}
      <RecentUploadsLedger
        certificates={certificates}
        docTypes={docTypes}
        ocrRunning={ocrRunning}
        certDocTypes={certDocTypes}
        deletingId={deletingId}
        onRunOcr={handleRunOcr}
        onDelete={handleDelete}
        onCertDocTypeChange={(certId, type) =>
          setCertDocTypes((prev) => ({ ...prev, [certId]: type }))
        }
      />
    </div>
  );
}
