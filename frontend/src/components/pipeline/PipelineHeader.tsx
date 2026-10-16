"use client";

import React, { useState } from "react";
import { ArrowLeft, RefreshCw, Copy, Check, Hash, FileText, ImageIcon, ShieldCheck } from "lucide-react";
import { CertificateResponse, PipelineStatusResponse } from "@/lib/api";
import { Badge, Button } from "@/components/ui";

interface PipelineHeaderProps {
  certificate?: CertificateResponse | null;
  cert?: CertificateResponse | null;
  pipeline?: PipelineStatusResponse | null;
  overallStatus?: "FULLY_COMPLETE" | "PARTIALLY_COMPLETE" | "NOT_STARTED" | string;
  completionPct?: number;
  onBack?: () => void;
  onRefresh?: () => void;
  refreshing?: boolean;
  loading?: boolean;
}

export const PipelineHeader: React.FC<PipelineHeaderProps> = ({
  certificate,
  cert,
  pipeline,
  overallStatus,
  completionPct,
  onBack,
  onRefresh,
  refreshing = false,
  loading = false,
}) => {
  const activeCert = cert ?? certificate;
  const isRefreshing = refreshing || loading;
  const activeOverallStatus = pipeline?.overall_status ?? overallStatus;
  const activeCompletionPct = pipeline?.completion_pct ?? completionPct ?? 0;

  const [copied, setCopied] = useState(false);

  const handleCopyHash = () => {
    if (!activeCert?.sha256_hash) return;
    navigator.clipboard.writeText(activeCert.sha256_hash);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isPdf = activeCert?.file_type?.toLowerCase() === "pdf";

  const getStatusBadge = () => {
    if (activeOverallStatus === "FULLY_COMPLETE") {
      return (
        <Badge variant="genuine" size="sm">
          LEDGER VERIFIED · 100%
        </Badge>
      );
    }
    if (overallStatus === "PARTIALLY_COMPLETE") {
      return (
        <Badge variant="suspicious" size="sm">
          PIPELINE ACTIVE · {completionPct ? `${Math.round(completionPct)}%` : "IN PROGRESS"}
        </Badge>
      );
    }
    return (
      <Badge variant="neutral" size="sm">
        READY FOR INFERENCE
      </Badge>
    );
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
      {/* Top Navigation & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200">
        {onBack ? (
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-900 font-mono transition"
          >
            <ArrowLeft size={14} /> Back to Repository
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <ShieldCheck size={16} className="text-primary" />
            <span className="text-xs font-mono text-slate-900 font-semibold">CertiVerify Pipeline Cockpit</span>
          </div>
        )}

        <div className="flex items-center gap-2">
          {getStatusBadge()}
          {onRefresh && (
            <Button
              variant="outline"
              size="sm"
              onClick={onRefresh}
              disabled={isRefreshing}
              icon={<RefreshCw size={12} className={isRefreshing ? "animate-spin text-primary" : ""} />}
            >
              Sync
            </Button>
          )}
        </div>
      </div>

      {/* Identity Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-lg bg-primary-tint border border-primary/20 flex items-center justify-center text-primary shrink-0">
            {isPdf ? <FileText size={20} /> : <ImageIcon size={20} />}
          </div>
          <div className="min-w-0">
            <h1 className="text-base font-bold text-slate-900 truncate tracking-tight">
              {activeCert?.original_filename || "Certificate Ingestion"}
            </h1>
            <p className="text-xs text-slate-500 font-mono mt-0.5">
              Cert ID: <span className="text-slate-700">{activeCert?.id || "—"}</span>
            </p>
          </div>
        </div>

        {/* SHA-256 Checksum Pill */}
        {activeCert?.sha256_hash && (
          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-600 max-w-full overflow-hidden">
            <Hash size={13} className="text-primary shrink-0" />
            <span className="truncate max-w-[240px] text-[11px] text-slate-700">
              {activeCert.sha256_hash}
            </span>
            <button
              onClick={handleCopyHash}
              className="text-slate-400 hover:text-slate-900 transition ml-1 shrink-0 p-1"
              title="Copy Checksum"
            >
              {copied ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
