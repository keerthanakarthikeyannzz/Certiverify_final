"use client";

import React from "react";
import { FileText, ShieldCheck, AlertTriangle, ShieldAlert } from "lucide-react";
import { PredictionDistribution } from "@/lib/api";

interface KpiGridProps {
  totalCertificates: number;
  distribution?: PredictionDistribution;
}

export const KpiGrid: React.FC<KpiGridProps> = ({
  totalCertificates,
  distribution,
}) => {
  const genuine = distribution?.genuine ?? 0;
  const suspicious = distribution?.suspicious ?? 0;
  const fake = distribution?.fake ?? 0;

  const kpis = [
    {
      label: "TOTAL CERTIFICATES",
      value: totalCertificates,
      description: "All certificates processed",
      pct: totalCertificates > 0 ? `${totalCertificates} total records` : "No certificates ingested yet",
      icon: FileText,
      color: "text-slate-900",
      iconColor: "text-indigo-600",
      badge: "Registry Active",
      badgeColor: "text-indigo-700 bg-indigo-50 border-indigo-200",
    },
    {
      label: "GENUINE",
      value: genuine,
      description: "Verified authentic",
      pct: `${totalCertificates ? Math.round((genuine / totalCertificates) * 100) : 0}% of total`,
      icon: ShieldCheck,
      color: "text-emerald-700",
      iconColor: "text-emerald-600",
      badge: "Authentic",
      badgeColor: "text-emerald-700 bg-emerald-50 border-emerald-200",
    },
    {
      label: "SUSPICIOUS",
      value: suspicious,
      description: "Needs manual review",
      pct: `${totalCertificates ? Math.round((suspicious / totalCertificates) * 100) : 0}% of total`,
      icon: AlertTriangle,
      color: "text-amber-700",
      iconColor: "text-amber-600",
      badge: "Needs Review",
      badgeColor: "text-amber-700 bg-amber-50 border-amber-200",
    },
    {
      label: "FAKE",
      value: fake,
      description: "Identified as fraudulent",
      pct: `${totalCertificates ? Math.round((fake / totalCertificates) * 100) : 0}% of total`,
      icon: ShieldAlert,
      color: "text-rose-700",
      iconColor: "text-rose-600",
      badge: "Fraudulent",
      badgeColor: "text-rose-700 bg-rose-50 border-rose-200",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {kpis.map((kpi) => {
        const Icon = kpi.icon;
        return (
          <div
            key={kpi.label}
            className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm transition-all duration-150 hover:shadow-md flex flex-col justify-between"
          >
            <div className="flex items-start justify-between gap-2 mb-3">
              <span className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                {kpi.label}
              </span>
              <span
                className={`text-[10px] px-2 py-0.5 rounded-full font-medium tracking-wide uppercase border ${kpi.badgeColor}`}
              >
                {kpi.badge}
              </span>
            </div>

            <div className="mb-2">
              <span className={`text-3xl font-bold tracking-tight block ${kpi.color}`}>
                {kpi.value.toLocaleString()}
              </span>
              <span className="text-xs text-slate-500 font-medium block mt-0.5">
                {kpi.pct}
              </span>
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span className="truncate">{kpi.description}</span>
              <Icon size={16} className={kpi.iconColor} />
            </div>
          </div>
        );
      })}
    </div>
  );
};

