"use client";

import React from "react";
import Link from "next/link";
import { Upload, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";

interface DashboardHeaderProps {
  userName?: string;
  userRole?: string;
  onRefresh: () => void;
  refreshing: boolean;
}

export const DashboardHeader: React.FC<DashboardHeaderProps> = ({
  userRole = "STUDENT",
  onRefresh,
  refreshing,
}) => {
  return (
    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[11px] text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider">
            Forensic Telemetry
          </span>
          <span className="text-[11px] text-slate-500 font-medium">
            ROLE: {userRole.toUpperCase()}
          </span>
        </div>
        <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
          Authenticity & Fraud Detection Console
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-0.5 max-w-2xl leading-relaxed">
          Real-time cryptographic hashing, neural OCR extraction, and multi-vector forgery detection telemetry.
        </p>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <Button
          variant="secondary"
          size="sm"
          onClick={onRefresh}
          disabled={refreshing}
          icon={<RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />}
        >
          {refreshing ? "Refreshing..." : "Sync State"}
        </Button>

        <Link href="/dashboard/upload">
          <Button variant="primary" size="sm" icon={<Upload size={13} />}>
            Ingest Document
          </Button>
        </Link>
      </div>
    </div>
  );
};

