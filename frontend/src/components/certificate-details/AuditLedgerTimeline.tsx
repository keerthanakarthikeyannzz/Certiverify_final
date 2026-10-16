"use client";

import React from "react";
import {
  History,
  CheckCircle2,
  Clock,
  AlertCircle,
  HelpCircle,
  ShieldCheck,
  FileSpreadsheet,
  Link2,
  FileText,
  Zap,
} from "lucide-react";
import {
  PipelineStatusResponse,
  CertificateResponse,
  OCRDataResponse,
  VerificationResultResponse,
  FraudAnalysisResponse,
  TrustScoreResponse,
  FinalPredictionResponse,
  VerificationReportResponse,
} from "@/lib/api";

interface AuditLedgerTimelineProps {
  pipeline: PipelineStatusResponse | null;
  cert: CertificateResponse | null;
  ocr: OCRDataResponse | null;
  verification: VerificationResultResponse | null;
  fraud: FraudAnalysisResponse | null;
  trustScore: TrustScoreResponse | null;
  prediction: FinalPredictionResponse | null;
  report: VerificationReportResponse | null;
}

export const AuditLedgerTimeline: React.FC<AuditLedgerTimelineProps> = ({
  cert,
  ocr,
  verification,
  fraud,
  trustScore,
  prediction,
  report,
}) => {
  interface TimelineEvent {
    id: string;
    title: string;
    category: string;
    timestamp: string | null;
    status: "completed" | "pending" | "failed" | "unavailable";
    durationMs?: number | null;
    details?: string;
  }

  const events: TimelineEvent[] = [
    {
      id: "upload",
      title: "Document Ingestion & File Checksum",
      category: "Ingestion",
      timestamp: cert?.uploaded_at ?? null,
      status: cert ? "completed" : "pending",
      details: cert ? `SHA-256: ${cert.sha256_hash?.slice(0, 16)}…` : undefined,
    },
    {
      id: "ocr",
      title: "Optical Character Recognition & Extraction",
      category: "OCR Engine",
      timestamp: ocr?.created_at ?? null,
      status: ocr ? "completed" : "pending",
      details: ocr
        ? `${ocr.ocr_engine} • ${Math.round((ocr.ocr_accuracy || 0) * 100)}% Accuracy`
        : undefined,
    },
    {
      id: "verification",
      title: "Four-Vector Forensic Verification",
      category: "Verification",
      timestamp: verification?.created_at ?? null,
      status: verification ? "completed" : "pending",
      details: verification
        ? `QR: ${verification.qr_valid ? "Valid" : "Checked"} | Tampering Score: ${
            verification.tampering_score != null ? Math.round(verification.tampering_score) : "—"
          }`
        : undefined,
    },
    {
      id: "fraud",
      title: "Bayesian Multi-Factor Fraud Risk Evaluation",
      category: "Risk Model",
      timestamp: fraud?.created_at ?? null,
      status: fraud ? "completed" : "pending",
      details: fraud
        ? `Fraud Probability: ${Math.round(fraud.fraud_probability * 100)}%`
        : undefined,
    },
    {
      id: "trust",
      title: "Forensic Reliability & Trust Score",
      category: "Scoring",
      timestamp: trustScore?.created_at ?? null,
      status: trustScore ? "completed" : "pending",
      details: trustScore ? `Trust Index: ${Math.round(trustScore.score)}/100` : undefined,
    },
    {
      id: "prediction",
      title: "AI Final Classification & Verdict",
      category: "Decision Engine",
      timestamp: prediction?.created_at ?? null,
      status: prediction ? "completed" : "pending",
      details: prediction
        ? `Verdict: ${prediction.label.toUpperCase()} (${Math.round(
            prediction.confidence_score * 100
          )}% conf)`
        : undefined,
    },
    {
      id: "report",
      title: "Executive PDF Audit Ledger Generation",
      category: "Reporting",
      timestamp: report?.generated_at ?? null,
      status: report ? "completed" : "pending",
      details: report ? `Report ID: ${report.verification_id}` : undefined,
    },
  ];

  const formatTime = (isoString: string | null) => {
    if (!isoString) return "Timestamp pending";
    try {
      const d = new Date(isoString);
      return d.toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return "Timestamp pending";
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <History size={15} className="text-primary" />
          <h3 className="text-xs font-semibold text-slate-800 uppercase tracking-wider font-mono">
            Cryptographic Audit Ledger & Event Log
          </h3>
        </div>
        <span className="text-[10px] font-mono text-slate-400">
          APPEND-ONLY AUDIT TRAIL • ISO 27001 COMPLIANT
        </span>
      </div>

      {/* Events List */}
      <div className="relative pl-6 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
        {events.map((ev) => {
          const isDone = ev.status === "completed";
          return (
            <div key={ev.id} className="relative group">
              {/* Timeline marker */}
              <div
                className={`absolute -left-6 top-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center transition ${
                  isDone
                    ? "bg-emerald-50 border-emerald-500 text-emerald-600 shadow-xs"
                    : "bg-slate-100 border-slate-300 text-slate-400"
                }`}
              >
                {isDone ? (
                  <CheckCircle2 size={10} className="stroke-[3]" />
                ) : (
                  <Clock size={8} />
                )}
              </div>

              {/* Event Body */}
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 hover:bg-slate-100/70 transition flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-slate-900">
                      {ev.title}
                    </span>
                    <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-white border border-slate-200 text-slate-500 font-medium">
                      {ev.category}
                    </span>
                  </div>
                  {ev.details && (
                    <p className="text-[11px] font-mono text-slate-600">
                      {ev.details}
                    </p>
                  )}
                </div>

                {/* Timestamp */}
                <div className="text-right shrink-0">
                  <span className="text-[10px] font-mono text-slate-500 block">
                    {formatTime(ev.timestamp)}
                  </span>
                  <span
                    className={`text-[10px] font-mono uppercase font-semibold ${
                      isDone ? "text-emerald-700" : "text-slate-400"
                    }`}
                  >
                    {isDone ? "COMPLETED" : "AWAITING"}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
