"use client";

import React, { useState } from "react";
import { ListChecks } from "lucide-react";
import { PipelineStage } from "@/lib/api";
import { PipelineStageItem } from "./PipelineStageItem";

interface PipelineStageListProps {
  stages: PipelineStage[];
  loading?: boolean;
  errorMessage?: string | null;
}

export const PipelineStageList: React.FC<PipelineStageListProps> = ({ stages, loading, errorMessage }) => {
  const [filter, setFilter] = useState<"ALL" | "COMPLETED" | "PENDING">("ALL");

  const filteredStages = stages.filter((stage) => {
    if (filter === "COMPLETED") return stage.status === "COMPLETED";
    if (filter === "PENDING") return stage.status === "PENDING";
    return true;
  });

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <ListChecks size={16} className="text-primary" />
          <h2 className="text-xs font-semibold text-slate-800 uppercase tracking-wider font-mono">
            Verification Pipeline Sequence ({stages.length} Stages)
          </h2>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 self-start sm:self-auto bg-slate-50 p-1 rounded-lg border border-slate-200">
          <button
            onClick={() => setFilter("ALL")}
            className={`px-2.5 py-1 rounded text-[11px] font-mono transition ${
              filter === "ALL"
                ? "bg-primary text-white font-semibold shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            All ({stages.length})
          </button>
          <button
            onClick={() => setFilter("COMPLETED")}
            className={`px-2.5 py-1 rounded text-[11px] font-mono transition ${
              filter === "COMPLETED"
                ? "bg-emerald-600 text-white font-semibold shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Done ({stages.filter((s) => s.status === "COMPLETED").length})
          </button>
          <button
            onClick={() => setFilter("PENDING")}
            className={`px-2.5 py-1 rounded text-[11px] font-mono transition ${
              filter === "PENDING"
                ? "bg-amber-600 text-white font-semibold shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Pending ({stages.filter((s) => s.status === "PENDING").length})
          </button>
        </div>
      </div>

      {loading ? (
        <div className="py-8 text-center text-xs font-mono text-slate-400">
          Loading verification pipeline telemetry...
        </div>
      ) : errorMessage ? (
        <div className="py-8 text-center px-4 space-y-2">
          <p className="text-xs font-mono font-medium text-amber-600">
            Pipeline status unavailable
          </p>
          <p className="text-[11px] font-mono text-slate-500 max-w-sm mx-auto">
            The verification pipeline status endpoint is temporarily unavailable from the backend service. Individual forensic modules remain operational.
          </p>
        </div>
      ) : stages.length === 0 ? (
        <div className="py-8 text-center text-xs font-mono text-slate-400">
          No pipeline telemetry available from backend.
        </div>
      ) : (
        <div className="space-y-2">
          {filteredStages.map((stage, idx) => (
            <PipelineStageItem key={stage.stage} stage={stage} index={idx} />
          ))}
        </div>
      )}
    </div>
  );
};
