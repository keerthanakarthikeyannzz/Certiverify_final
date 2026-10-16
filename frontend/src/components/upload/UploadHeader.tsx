"use client";

import React from "react";
import { ShieldCheck, Cpu, Lock } from "lucide-react";
import { Badge } from "@/components/ui/Badge";

interface UploadHeaderProps {
  userName?: string;
  totalIngested?: number;
}

export const UploadHeader: React.FC<UploadHeaderProps> = ({
  totalIngested,
}) => {
  return (
    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-200">
      <div>
        <div className="flex items-center gap-2.5 mb-1.5">
          <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
            <ShieldCheck size={20} />
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 font-sans">
            Certificate Ingestion & Pipeline
          </h1>
          <Badge variant="brand" size="sm">
            AI PIPELINE v2
          </Badge>
        </div>
        <p className="text-xs sm:text-sm text-slate-500 max-w-2xl font-sans">
          Upload certificates, degrees, or marksheets for OCR text extraction, SHA-256 fingerprinting,
          forensic Error Level Analysis, and AI trust scoring.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 shrink-0">
        <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-600 shadow-xs">
          <Lock size={13} className="text-emerald-600" />
          <span>SHA-256 Verified</span>
        </div>
        {totalIngested !== undefined && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-600 shadow-xs">
            <Cpu size={13} className="text-indigo-600" />
            <span>
              Total Processed:{" "}
              <strong className="text-slate-900 font-bold">{totalIngested}</strong>
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default UploadHeader;
