"use client";

import React from "react";
import { Activity, ShieldCheck, QrCode, Link2, Copy, FileSearch } from "lucide-react";

interface PipelineHealthCardProps {
  duplicateCount?: number;
  tamperedCount?: number;
  qrVerifiedCount?: number;
  blockchainVerifiedCount?: number;
  docTypeDistribution?: Record<string, number>;
}

export const PipelineHealthCard: React.FC<PipelineHealthCardProps> = ({
  duplicateCount = 0,
  tamperedCount = 0,
  qrVerifiedCount = 0,
  blockchainVerifiedCount = 0,
  docTypeDistribution,
}) => {
  const checks = [
    {
      name: "QR Cryptographic Payload",
      count: qrVerifiedCount,
      icon: QrCode,
      color: "text-emerald-700",
      status: "ACTIVE",
    },
    {
      name: "Blockchain On-Chain Hash",
      count: blockchainVerifiedCount,
      icon: Link2,
      color: "text-indigo-700",
      status: "SYNCED",
    },
    {
      name: "ELA Tampering & Copy-Paste",
      count: tamperedCount,
      icon: ShieldCheck,
      color: "text-amber-700",
      status: "ENGAGED",
    },
    {
      name: "Perceptual Duplicate Collision",
      count: duplicateCount,
      icon: Copy,
      color: "text-rose-700",
      status: "RUNNING",
    },
  ];

  const types = docTypeDistribution ? Object.entries(docTypeDistribution) : [];

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 font-sans flex items-center gap-2">
            <Activity size={15} className="text-indigo-600" />
            Pipeline Health & Multi-Factor Status
          </h3>
          <p className="text-xs text-slate-500">Live operational state of background forensic engines</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {checks.map((c) => {
          const Icon = c.icon;
          return (
            <div
              key={c.name}
              className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between"
            >
              <div className="flex items-center gap-2.5">
                <Icon size={16} className={c.color} />
                <div>
                  <span className="text-xs font-semibold text-slate-800 block">{c.name}</span>
                  <span className="text-[10px] font-mono text-slate-400">Total processed: {c.count}</span>
                </div>
              </div>
              <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                {c.status}
              </span>
            </div>
          );
        })}
      </div>

      {types.length > 0 && (
        <div className="pt-3 border-t border-slate-100">
          <span className="text-[10px] font-mono uppercase text-slate-500 block mb-2 font-semibold">
            Extracted Document Classification Mix
          </span>
          <div className="flex flex-wrap gap-1.5">
            {types.map(([t, count]) => (
              <span
                key={t}
                className="text-xs font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 flex items-center gap-1"
              >
                <FileSearch size={10} className="text-indigo-600" />
                <span className="capitalize">{t.replace(/_/g, " ")}:</span>
                <strong className="text-slate-900">{count}</strong>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
