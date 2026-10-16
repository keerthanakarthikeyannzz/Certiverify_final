"use client";

import React from "react";
import { Check, Clock, AlertTriangle, Minus, Loader2 } from "lucide-react";
import { PipelineStage } from "@/lib/api";
import { Badge } from "@/components/ui";

interface PipelineStageItemProps {
  stage: PipelineStage;
  index: number;
}

export const PipelineStageItem: React.FC<PipelineStageItemProps> = ({ stage, index }) => {
  const isCompleted = stage.status === "COMPLETED";
  const isRunning = stage.status === "RUNNING";
  const isPending = stage.status === "PENDING";
  const isFailed = stage.status === "FAILED";
  const isUnavailable = stage.status === "UNAVAILABLE" || stage.status === "NOT_APPLICABLE";

  const getStatusBadge = () => {
    if (isCompleted) {
      return <Badge variant="genuine" size="sm"><Check size={10} className="mr-0.5" /> DONE</Badge>;
    }
    if (isRunning) {
      return (
        <Badge variant="neutral" size="sm" className="bg-primary/10 text-primary border-primary/30 animate-pulse">
          <Loader2 size={10} className="animate-spin mr-0.5" /> RUNNING
        </Badge>
      );
    }
    if (isFailed) {
      return <Badge variant="fake" size="sm"><AlertTriangle size={10} className="mr-0.5" /> FAILED</Badge>;
    }
    if (isUnavailable) {
      return <Badge variant="neutral" size="sm"><Minus size={10} className="mr-0.5" /> N/A</Badge>;
    }
    return <Badge variant="suspicious" size="sm"><Clock size={10} className="mr-0.5" /> PENDING</Badge>;
  };

  const formattedIndex = String(index + 1).padStart(2, "0");

  return (
    <div
      className={`p-3 rounded-lg border transition flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
        isCompleted
          ? "bg-slate-50/80 border-slate-200 hover:border-emerald-300"
          : isRunning
          ? "bg-primary-tint/30 border-primary/30 shadow-xs"
          : isFailed
          ? "bg-rose-50 border-rose-200"
          : isUnavailable
          ? "bg-slate-50/40 border-slate-200 opacity-60"
          : "bg-white border-slate-200 hover:border-slate-300"
      }`}
    >
      <div className="flex items-start sm:items-center gap-3 min-w-0">
        <span className="font-mono text-[11px] text-slate-400 font-bold shrink-0 w-6">
          {formattedIndex}
        </span>

        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold text-slate-900 font-sans">
              {stage.label}
            </span>
            <span className="text-[10px] font-mono text-slate-400 hidden md:inline">
              [{stage.stage}]
            </span>
          </div>
          {stage.summary && (
            <p className="text-[11px] text-slate-600 font-mono mt-0.5 truncate max-w-lg">
              {stage.summary}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2.5 shrink-0 self-end sm:self-center">
        {stage.completed_at && (
          <span className="text-[10px] font-mono text-slate-400">
            {new Date(stage.completed_at).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })}
          </span>
        )}
        {stage.duration_ms != null && (
          <span className="text-[10px] font-mono text-primary font-medium">
            {stage.duration_ms}ms
          </span>
        )}
        {getStatusBadge()}
      </div>
    </div>
  );
};
