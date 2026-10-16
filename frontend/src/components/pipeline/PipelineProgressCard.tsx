"use client";

import React from "react";
import { CheckCircle2, Clock, AlertTriangle, Cpu, Layers, Loader2, RefreshCw } from "lucide-react";
import { PipelineStage, PipelineStatusResponse } from "@/lib/api";
import { Badge, Button } from "@/components/ui";

interface PipelineProgressCardProps {
  pipeline?: PipelineStatusResponse | null;
  overallStatus?: "FULLY_COMPLETE" | "PARTIALLY_COMPLETE" | "NOT_STARTED" | string;
  completionPct?: number;
  stages?: PipelineStage[];
  loading?: boolean;
  isRunning?: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
}

export const PipelineProgressCard: React.FC<PipelineProgressCardProps> = ({
  pipeline,
  overallStatus,
  completionPct,
  stages,
  loading = false,
  isRunning = false,
  errorMessage,
  onRetry,
}) => {
  const activeOverallStatus = isRunning
    ? "RUNNING"
    : (pipeline?.overall_status ?? overallStatus ?? "NOT_STARTED");
  const activeCompletionPct = pipeline?.completion_pct ?? completionPct ?? 0;
  const activeStages = pipeline?.stages ?? stages ?? [];

  const completedCount = activeStages.filter((s) => s.status === "COMPLETED" || s.status === "NOT_APPLICABLE").length;
  const pendingCount = activeStages.filter((s) => s.status === "PENDING").length;
  const unavailableCount = activeStages.filter((s) => s.status === "UNAVAILABLE").length;
  const failedCount = activeStages.filter((s) => s.status === "FAILED").length;
  const totalStages = activeStages.length || 14;

  const failedStage = activeStages.find((s) => s.status === "FAILED");

  const pct = Math.min(100, Math.max(0, Math.round(activeCompletionPct)));

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-primary-tint border border-primary/20 flex items-center justify-center text-primary">
            <Layers size={14} />
          </div>
          <h2 className="text-xs font-semibold text-slate-800 uppercase tracking-wider font-mono">
            Verification Pipeline Telemetry
          </h2>
        </div>
        <span className="text-[10px] font-mono text-slate-400">
          BACKEND CONTRACT: 14 ATOMIC STAGES
        </span>
      </div>

      {/* Progress Metric & Overall Status */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <span className="text-3xl sm:text-4xl font-bold font-mono text-slate-900">
            {loading && !pipeline ? "…" : errorMessage ? "—" : `${pct}%`}
          </span>
          <span className="text-xs font-mono text-slate-500">
            {errorMessage ? "Pipeline status unavailable" : `${completedCount} of ${totalStages} Stages Verified`}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {errorMessage ? (
            <Badge variant="fake" size="sm">PIPELINE ERROR</Badge>
          ) : isRunning ? (
            <Badge variant="neutral" size="sm" className="bg-primary/10 text-primary border-primary/30">
              <Loader2 size={11} className="animate-spin mr-1" />
              RUNNING
            </Badge>
          ) : (
            <Badge
              variant={
                activeOverallStatus === "FULLY_COMPLETE"
                  ? "genuine"
                  : activeOverallStatus === "PARTIALLY_COMPLETE"
                  ? "suspicious"
                  : "neutral"
              }
              size="sm"
            >
              {activeOverallStatus.replace(/_/g, " ")}
            </Badge>
          )}
        </div>
      </div>

      {/* Real Completion Progress Bar */}
      <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden border border-slate-200">
        <div
          className="h-full bg-gradient-to-r from-primary to-emerald-500 transition-all duration-500 rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Stage Breakdown Matrix */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 flex items-center gap-2">
          <CheckCircle2 size={15} className="text-emerald-600 shrink-0" />
          <div>
            <p className="text-[10px] font-mono uppercase text-slate-400">Completed</p>
            <p className="text-xs font-bold text-slate-900 font-mono">{completedCount}</p>
          </div>
        </div>

        <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 flex items-center gap-2">
          <Clock size={15} className="text-amber-600 shrink-0" />
          <div>
            <p className="text-[10px] font-mono uppercase text-slate-400">Pending</p>
            <p className="text-xs font-bold text-slate-900 font-mono">{pendingCount}</p>
          </div>
        </div>

        <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 flex items-center gap-2">
          <Cpu size={15} className="text-slate-400 shrink-0" />
          <div>
            <p className="text-[10px] font-mono uppercase text-slate-400">Not Applicable</p>
            <p className="text-xs font-bold text-slate-500 font-mono">{unavailableCount}</p>
          </div>
        </div>

        <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 flex items-center gap-2">
          <AlertTriangle size={15} className="text-rose-600 shrink-0" />
          <div>
            <p className="text-[10px] font-mono uppercase text-slate-400">Failed</p>
            <p className="text-xs font-bold text-slate-900 font-mono">{failedCount}</p>
          </div>
        </div>
      </div>

      {/* Failed Stage Alert Banner & Retry Functionality */}
      {(failedStage || errorMessage) && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-center justify-between gap-3 text-xs font-mono">
          <div className="flex items-center gap-2 text-rose-700">
            <AlertTriangle size={14} className="shrink-0" />
            <span>
              {failedStage ? `Failed Stage: ${failedStage.label}` : errorMessage}
            </span>
          </div>
          {onRetry && (
            <Button
              variant="outline"
              size="sm"
              onClick={onRetry}
              disabled={isRunning}
              icon={<RefreshCw size={11} className={isRunning ? "animate-spin" : ""} />}
            >
              Retry Pipeline
            </Button>
          )}
        </div>
      )}
    </div>
  );
};
