"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  RefreshCw,
  ScanLine,
  Zap,
  Download,
  FileText,
  Copy,
  Check,
  ShieldCheck,
  FileCode,
  HardDrive,
  Calendar,
  Layers,
  Loader2,
  AlertCircle,
} from "lucide-react";
import {
  CertificateResponse,
  PipelineStatusResponse,
  FinalPredictionResponse,
  VerificationReportResponse,
} from "@/lib/api";
import { Badge, Button } from "@/components/ui";

interface ForensicCockpitHeaderProps {
  cert: CertificateResponse | null;
  pipeline: PipelineStatusResponse | null;
  prediction: FinalPredictionResponse | null;
  report: VerificationReportResponse | null;
  activeTab: "pipeline" | "cockpit";
  onTabChange: (tab: "pipeline" | "cockpit") => void;
  onRefresh: () => void;
  onRunOcr: () => void;
  onVerifyAll: () => void;
  onGenerateReport: () => void;
  onDownloadReport: () => void;
  loadingPipeline: boolean;
  runningOcr: boolean;
  verifyingAll: boolean;
  generatingReport: boolean;
  downloadingReport: boolean;
}

export const ForensicCockpitHeader: React.FC<ForensicCockpitHeaderProps> = ({
  cert,
  pipeline,
  prediction,
  report,
  activeTab,
  onTabChange,
  onRefresh,
  onRunOcr,
  onVerifyAll,
  onGenerateReport,
  onDownloadReport,
  loadingPipeline,
  runningOcr,
  verifyingAll,
  generatingReport,
  downloadingReport,
}) => {
  const [copiedHash, setCopiedHash] = useState(false);
  const [copiedId, setCopiedId] = useState(false);

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const copyToClipboard = (text: string, type: "hash" | "id") => {
    navigator.clipboard.writeText(text);
    if (type === "hash") {
      setCopiedHash(true);
      setTimeout(() => setCopiedHash(false), 2000);
    } else {
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 2000);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Bar: Navigation & Primary Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard"
            className="p-2 bg-white hover:bg-slate-50 text-slate-500 hover:text-slate-900 rounded-lg border border-slate-200 shadow-sm transition"
            title="Back to Dashboard"
          >
            <ArrowLeft size={16} />
          </Link>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                {cert?.original_filename || "Certificate Inspection"}
              </h1>
              {prediction && (() => {
                const isInc = prediction.label === "inconclusive" || prediction.label.includes("inconclusive");
                const variant = prediction.label === "genuine"
                  ? "genuine"
                  : isInc
                  ? "inconclusive"
                  : prediction.label === "suspicious"
                  ? "suspicious"
                  : "fake";
                const display = isInc ? "NEEDS REVIEW" : prediction.label.toUpperCase();
                return (
                  <Badge variant={variant} size="md">
                    {display}
                  </Badge>
                );
              })()}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              AI Forensic Cockpit • Full Integrity & Cryptographic Verification Audit
            </p>
          </div>
        </div>

        {/* Global Action Cluster */}
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={loadingPipeline}
            icon={
              <RefreshCw
                size={13}
                className={loadingPipeline ? "animate-spin text-primary" : "text-slate-500"}
              />
            }
          >
            Refresh
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={onRunOcr}
            disabled={runningOcr}
            icon={
              runningOcr ? (
                <Loader2 size={13} className="animate-spin text-primary" />
              ) : (
                <ScanLine size={13} className="text-primary" />
              )
            }
          >
            {runningOcr ? "Running OCR..." : "Run OCR"}
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={onVerifyAll}
            disabled={verifyingAll}
            icon={
              verifyingAll ? (
                <Loader2 size={13} className="animate-spin text-white" />
              ) : (
                <Zap size={13} />
              )
            }
          >
            {verifyingAll ? "Verifying..." : "Verify All"}
          </Button>

          {report ? (
            <Button
              variant="outline"
              size="sm"
              onClick={onDownloadReport}
              disabled={downloadingReport}
              className="border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100"
              icon={
                downloadingReport ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Download size={13} />
                )
              }
            >
              Download PDF
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={onGenerateReport}
              disabled={generatingReport}
              icon={
                generatingReport ? (
                  <Loader2 size={13} className="animate-spin text-primary" />
                ) : (
                  <FileText size={13} className="text-slate-500" />
                )
              }
            >
              {generatingReport ? "Generating..." : "Generate Report"}
            </Button>
          )}
        </div>
      </div>

      {/* Metadata Pill Banner */}
      <div className="bg-white border border-slate-200 rounded-xl p-3 text-xs text-slate-600 shadow-sm grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 items-center">
        {/* Certificate ID */}
        <div className="flex items-center gap-2 min-w-0">
          <FileCode size={14} className="text-slate-400 shrink-0" />
          <div className="min-w-0">
            <p className="text-[10px] text-slate-400 uppercase font-mono">Certificate ID</p>
            <div className="flex items-center gap-1">
              <span className="font-mono text-slate-800 truncate">
                {cert?.id ? `${cert.id.slice(0, 8)}…` : "—"}
              </span>
              {cert?.id && (
                <button
                  onClick={() => copyToClipboard(cert.id, "id")}
                  className="text-slate-400 hover:text-slate-700 transition"
                  title="Copy ID"
                >
                  {copiedId ? <Check size={11} className="text-emerald-600" /> : <Copy size={11} />}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* File Format & Size */}
        <div className="flex items-center gap-2">
          <HardDrive size={14} className="text-slate-400 shrink-0" />
          <div>
            <p className="text-[10px] text-slate-400 uppercase font-mono">Format & Size</p>
            <p className="text-slate-800 font-mono">
              {(cert?.file_type || "PDF").toUpperCase()} • {formatFileSize(cert?.file_size_bytes)}
            </p>
          </div>
        </div>

        {/* Upload Date */}
        <div className="flex items-center gap-2">
          <Calendar size={14} className="text-slate-400 shrink-0" />
          <div>
            <p className="text-[10px] text-slate-400 uppercase font-mono">Uploaded At</p>
            <p className="text-slate-800">
              {cert?.uploaded_at
                ? new Date(cert.uploaded_at).toLocaleString("en-IN", {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "—"}
            </p>
          </div>
        </div>

        {/* SHA-256 Hash */}
        <div className="flex items-center gap-2 col-span-2 lg:col-span-2 min-w-0">
          <ShieldCheck size={14} className="text-emerald-600 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-[10px] text-slate-400 uppercase font-mono">SHA-256 Checksum</p>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-[11px] text-slate-700 truncate">
                {cert?.sha256_hash || "Computing on-chain signature..."}
              </span>
              {cert?.sha256_hash && (
                <button
                  onClick={() => copyToClipboard(cert.sha256_hash, "hash")}
                  className="text-slate-400 hover:text-slate-700 transition shrink-0"
                  title="Copy SHA-256 hash"
                >
                  {copiedHash ? (
                    <Check size={11} className="text-emerald-600" />
                  ) : (
                    <Copy size={11} />
                  )}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Inconclusive / Needs Review Alert Banner */}
      {prediction && (prediction.label === "inconclusive" || prediction.label.includes("inconclusive")) && (() => {
        const partial = (prediction.evidence?._partial_verification as any) || (prediction.evidence_breakdown?._partial_verification as any);
        const missing = partial?.missing_checks;
        return (
          <div className="bg-amber-50 border border-amber-300 rounded-xl p-3.5 flex items-start gap-3 text-xs text-amber-950 shadow-xs">
            <AlertCircle size={18} className="text-amber-600 shrink-0 mt-0.5" />
            <div className="flex-1 space-y-1">
              <div className="flex items-center gap-2 font-semibold text-amber-950 flex-wrap">
                <span>Verdict Inconclusive — Needs Review</span>
                {partial?.note && (
                  <span className="text-[11px] font-medium text-amber-900 bg-amber-100 px-2 py-0.5 rounded-full border border-amber-300 font-mono">
                    {partial.note}
                  </span>
                )}
              </div>
              <p className="text-amber-900">
                {prediction.explanation || "One or more critical verification checks could not run or require external cryptographic proof."}
              </p>
              {missing && missing.length > 0 && (
                <p className="text-[11px] text-amber-900 font-mono pt-1 border-t border-amber-200">
                  <span className="font-semibold font-sans">Missing verification checks: </span>
                  {missing.join(", ")}
                </p>
              )}
            </div>
          </div>
        );
      })()}

      {/* Primary Cockpit Navigation Tabs */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => onTabChange("cockpit")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold tracking-wide uppercase transition flex items-center gap-2 ${
              activeTab === "cockpit"
                ? "bg-primary/10 text-primary border border-primary/25 shadow-xs"
                : "text-slate-500 hover:text-slate-900 hover:bg-slate-100"
            }`}
          >
            <Layers size={14} />
            <span>AI Forensic Cockpit</span>
            {prediction && (() => {
              const isInc = prediction.label === "inconclusive" || prediction.label.includes("inconclusive");
              return (
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded font-bold uppercase ${
                    prediction.label === "genuine"
                      ? "bg-emerald-100 text-emerald-800"
                      : isInc
                      ? "bg-amber-100 text-amber-900 border border-amber-300"
                      : prediction.label === "suspicious"
                      ? "bg-amber-100 text-amber-800"
                      : "bg-rose-100 text-rose-800"
                  }`}
                >
                  {isInc ? "Needs review" : prediction.label}
                </span>
              );
            })()}
          </button>

          <button
            onClick={() => onTabChange("pipeline")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold tracking-wide uppercase transition flex items-center gap-2 ${
              activeTab === "pipeline"
                ? "bg-primary/10 text-primary border border-primary/25 shadow-xs"
                : "text-slate-500 hover:text-slate-900 hover:bg-slate-100"
            }`}
          >
            <ScanLine size={14} />
            <span>OCR & Verification Pipeline</span>
            {pipeline && (
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 text-slate-700 font-semibold">
                {pipeline.completion_pct}%
              </span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
