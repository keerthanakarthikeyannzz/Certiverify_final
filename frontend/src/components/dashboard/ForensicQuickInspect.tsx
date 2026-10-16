"use client";

import React from "react";
import Link from "next/link";
import { Upload, ScanLine, Layers, FileText, ArrowRight } from "lucide-react";

export const ForensicQuickInspect: React.FC = () => {
  const quickActions = [
    {
      title: "Upload Certificate",
      description: "Verify a new document",
      href: "/dashboard/upload",
      icon: Upload,
      color: "text-indigo-600",
    },
    {
      title: "Deep Document Analysis",
      description: "Deep document analysis",
      href: "/dashboard/certificates",
      icon: ScanLine,
      color: "text-blue-600",
    },
    {
      title: "Bulk Upload",
      description: "Upload multiple files",
      href: "/dashboard/upload",
      icon: Layers,
      color: "text-emerald-600",
    },
    {
      title: "View Reports",
      description: "Generate reports",
      href: "/dashboard/reports",
      icon: FileText,
      color: "text-amber-600",
    },
  ];

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Quick Actions</h3>
          <p className="text-xs text-slate-500">Common tasks to get started</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {quickActions.map((action) => {
          const Icon = action.icon;
          return (
            <Link
              key={action.title}
              href={action.href}
              className="p-3.5 bg-slate-50 border border-slate-200 hover:border-indigo-500 rounded-lg transition-all duration-150 hover:bg-white hover:shadow-sm group flex flex-col justify-between"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="p-2 rounded-lg bg-white border border-slate-200 text-slate-700 shadow-xs">
                  <Icon size={16} className={action.color} />
                </div>
                <ArrowRight size={13} className="text-slate-400 group-hover:text-indigo-600 group-hover:translate-x-0.5 transition-transform" />
              </div>
              <div>
                <h4 className="text-xs font-semibold text-slate-900 group-hover:text-indigo-600 transition-colors mb-0.5">
                  {action.title}
                </h4>
                <p className="text-[11px] text-slate-500 leading-snug">
                  {action.description}
                </p>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
};

