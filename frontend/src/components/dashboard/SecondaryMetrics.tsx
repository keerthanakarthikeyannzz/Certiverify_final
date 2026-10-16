"use client";

import React from "react";
import { Gauge, ScanText, FileCheck, AlertTriangle } from "lucide-react";
import { ProgressBar } from "@/components/ui/ProgressBar";

interface SecondaryMetricsProps {
  avgTrustScore?: number;
  avgOcrAccuracy?: number;
  avgFraudProbability?: number;
  totalReports: number;
}

export const SecondaryMetrics: React.FC<SecondaryMetricsProps> = ({
  avgTrustScore,
  avgOcrAccuracy,
  avgFraudProbability,
  totalReports,
}) => {
  const trustValue = avgTrustScore != null ? Math.round(avgTrustScore) : null;
  const ocrPct =
    avgOcrAccuracy != null ? Math.round(avgOcrAccuracy * 100) : null;
  const fraudPct =
    avgFraudProbability != null ? Math.round(avgFraudProbability * 100) : null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Metric 1: Mean Trust Score */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
          <span className="text-[11px] uppercase tracking-wider font-semibold">
            Mean Trust Index
          </span>
          <Gauge size={15} className="text-indigo-600" />
        </div>
        <div className="flex items-baseline gap-2 mb-2">
          <span className="text-2xl font-bold text-slate-900">
            {trustValue != null ? `${trustValue}` : "N/A"}
          </span>
          <span className="text-xs text-slate-400">/ 100</span>
        </div>
        <ProgressBar
          value={trustValue ?? 0}
          size="xs"
          variant={trustValue != null && trustValue >= 70 ? "emerald" : "amber"}
        />
      </div>

      {/* Metric 2: Avg OCR Extraction */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
          <span className="text-[11px] uppercase tracking-wider font-semibold">
            Neural OCR Accuracy
          </span>
          <ScanText size={15} className="text-emerald-600" />
        </div>
        <div className="flex items-baseline gap-2 mb-2">
          <span className="text-2xl font-bold text-slate-900">
            {ocrPct != null ? `${ocrPct}%` : "N/A"}
          </span>
          <span className="text-xs text-slate-400">
            Dual-engine mean
          </span>
        </div>
        <ProgressBar value={ocrPct ?? 0} size="xs" variant="emerald" />
      </div>

      {/* Metric 3: Avg Fraud Probability */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
          <span className="text-[11px] uppercase tracking-wider font-semibold">
            Avg Fraud Risk
          </span>
          <AlertTriangle size={15} className="text-amber-600" />
        </div>

        <div className="flex items-baseline gap-2 mb-2">
          <span className="text-2xl font-bold text-slate-900">
            {fraudPct != null ? `${fraudPct}%` : "N/A"}
          </span>
          <span className="text-xs text-slate-400">
            Risk coefficient
          </span>
        </div>
        <ProgressBar
          value={fraudPct ?? 0}
          size="xs"
          variant={fraudPct != null && fraudPct > 35 ? "rose" : "amber"}
        />
      </div>

      {/* Metric 4: Reports Generated */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
          <span className="text-[11px] uppercase tracking-wider font-semibold">
            Signed PDF Reports
          </span>
          <FileCheck size={15} className="text-indigo-600" />
        </div>
        <div className="flex items-baseline gap-2 mb-2">
          <span className="text-2xl font-bold text-slate-900">
            {totalReports.toLocaleString()}
          </span>
          <span className="text-xs text-slate-400">
            Cryptographically sealed
          </span>
        </div>
        <div className="h-1.5 bg-indigo-50 rounded-full overflow-hidden">
          <div className="h-full bg-indigo-600 w-full rounded-full" />
        </div>
      </div>
    </div>
  );
};

