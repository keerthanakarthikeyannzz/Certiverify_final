"use client";

import React from "react";
import Link from "next/link";
import { Clock } from "lucide-react";
import { TimelineEvent } from "@/lib/api";

interface ActivityLogProps {
  timeline?: TimelineEvent[];
}

export const ActivityLog: React.FC<ActivityLogProps> = ({ timeline = [] }) => {
  const formatTime = (ts: string) => {
    try {
      const d = new Date(ts);
      return d.toISOString().replace("T", " ").substring(11, 19);
    } catch {
      return ts;
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
            <Clock size={15} className="text-indigo-600" />
            Audit Activity Trail
          </h3>
          <p className="text-xs text-slate-500">
            Chronological audit log of ingestion, verification, and forensic events.
          </p>
        </div>
      </div>

      {timeline.length === 0 ? (
        <div className="py-8 text-center text-xs text-slate-500">
          No recent system events logged yet.
        </div>
      ) : (
        <div className="space-y-2.5 max-h-[340px] overflow-y-auto pr-1">
          {timeline.slice(0, 10).map((event, idx) => (
            <div
              key={`${event.certificate_id}-${idx}`}
              className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between gap-3 text-xs"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-1.5 h-1.5 rounded-full bg-indigo-600 shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-medium text-slate-900 truncate">
                    {event.event}
                  </p>
                  <Link
                    href={`/dashboard/certificates/${event.certificate_id}`}
                    className="text-[11px] text-slate-500 hover:text-indigo-600 truncate block transition-colors"
                  >
                    {event.filename}
                  </Link>
                </div>
              </div>

              <div className="text-right shrink-0">
                <span className="font-mono text-[10px] text-slate-500 block">
                  {formatTime(event.timestamp)}
                </span>
                {event.label && (
                  <span className="font-mono text-[9px] uppercase text-emerald-600 font-semibold">
                    {event.label}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

