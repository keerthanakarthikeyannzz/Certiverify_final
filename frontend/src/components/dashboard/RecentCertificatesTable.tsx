"use client";

import React from "react";
import Link from "next/link";
import {
  FileText,
  Search,
  ExternalLink,
  Download,
  Loader2,
  FileQuestion,
} from "lucide-react";
import { RecentCertificate } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

interface RecentCertificatesTableProps {
  certificates: RecentCertificate[];
  search: string;
  onSearchChange: (val: string) => void;
  filterLabel: string;
  onFilterChange: (val: any) => void;
  onDownloadReport: (certId: string, verificationId?: string) => Promise<void>;
  downloadingId: string | null;
}

export const RecentCertificatesTable: React.FC<RecentCertificatesTableProps> = ({
  certificates,
  search,
  onSearchChange,
  filterLabel,
  onFilterChange,
  onDownloadReport,
  downloadingId,
}) => {
  const filterOptions = [
    { label: "All Records", value: "all" },
    { label: "Genuine", value: "genuine" },
    { label: "Suspicious", value: "suspicious" },
    { label: "Needs Review", value: "inconclusive" },
    { label: "Fake", value: "fake" },
    { label: "Pending Verification", value: "not_run" },
  ];

  const renderVerdictBadge = (label?: string) => {
    switch (label) {
      case "genuine":
        return (
          <Badge variant="genuine" size="sm" dot>
            GENUINE
          </Badge>
        );
      case "suspicious":
        return (
          <Badge variant="suspicious" size="sm" dot>
            SUSPICIOUS
          </Badge>
        );
      case "inconclusive":
      case "inconclusive / needs review":
        return (
          <Badge variant="inconclusive" size="sm" dot>
            NEEDS REVIEW
          </Badge>
        );
      case "fake":
        return (
          <Badge variant="fake" size="sm" dot>
            FORGERY
          </Badge>
        );
      default:
        return (
          <Badge variant="neutral" size="sm">
            PENDING
          </Badge>
        );
    }
  };

  const formatTimestamp = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toISOString().replace("T", " ").substring(0, 16);
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
      {/* Table Header Controls */}
      <div className="p-4 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">
            Recent Certificate Registry
          </h2>
          <p className="text-xs text-slate-500">
            Cryptographic ledger of recently analyzed credentials and forensic outcomes.
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          {filterOptions.map((opt) => (
            <button
              key={opt.value}
              onClick={() => onFilterChange(opt.value)}
              className={`text-xs px-2.5 py-1 rounded-lg font-medium transition-colors ${
                filterLabel === opt.value
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-50 text-slate-600 hover:text-slate-900 border border-slate-200 hover:bg-slate-100"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Search Bar Sub-header */}
      <div className="px-4 py-2.5 bg-slate-50/70 border-b border-slate-100 flex items-center gap-2">
        <Search size={14} className="text-slate-400 shrink-0" />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter by certificate filename or verification ID..."
          className="w-full bg-transparent border-none text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none"
        />
        {search && (
          <button
            onClick={() => onSearchChange("")}
            className="text-xs text-slate-400 hover:text-slate-700 shrink-0"
          >
            Clear
          </button>
        )}
      </div>

      {/* Table Canvas */}
      <div className="overflow-x-auto">
        {certificates.length === 0 ? (
          <div className="p-12 text-center">
            <FileQuestion size={36} className="text-slate-300 mx-auto mb-3" />
            <h3 className="text-sm font-semibold text-slate-900 mb-1">
              No Certificate Records Found
            </h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto mb-4">
              {search
                ? `No certificates matched your search term "${search}".`
                : "Your certificate verification ledger is currently empty. Ingest your first certificate to run the verification engine."}
            </p>
            <Link href="/dashboard/upload">
              <Button variant="primary" size="sm">
                Upload Certificate
              </Button>
            </Link>
          </div>
        ) : (
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50 text-[11px] text-slate-500 uppercase tracking-wider font-semibold">
                <th className="py-2.5 px-4">Document Name</th>
                <th className="py-2.5 px-4">Timestamp</th>
                <th className="py-2.5 px-4">Verification ID</th>
                <th className="py-2.5 px-4">OCR Accuracy</th>
                <th className="py-2.5 px-4">Trust Score</th>
                <th className="py-2.5 px-4">Verdict</th>
                <th className="py-2.5 px-4 text-right">Cockpit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {certificates.map((cert) => (
                <tr
                  key={cert.id}
                  className="hover:bg-slate-50/70 transition-colors group"
                >
                  {/* Filename & Type */}
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2.5 min-w-0 max-w-xs">
                      <div className="p-1.5 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600 shrink-0">
                        <FileText size={14} />
                      </div>
                      <div className="min-w-0">
                        <Link
                          href={`/dashboard/certificates/${cert.id}`}
                          className="font-medium text-slate-900 hover:text-indigo-600 truncate block transition-colors"
                          title={cert.original_filename}
                        >
                          {cert.original_filename}
                        </Link>
                        <span className="font-mono text-[10px] text-slate-400 uppercase">
                          {cert.file_type}
                        </span>
                      </div>
                    </div>
                  </td>

                  {/* Timestamp */}
                  <td className="py-3 px-4 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                    {formatTimestamp(cert.uploaded_at)}
                  </td>

                  {/* Verification ID / Hash */}
                  <td className="py-3 px-4 font-mono text-[11px] text-indigo-600 whitespace-nowrap">
                    {cert.verification_id ? (
                      <span className="font-semibold">{cert.verification_id}</span>
                    ) : (
                      <span className="text-slate-400">#{cert.id.substring(0, 8)}</span>
                    )}
                  </td>

                  {/* OCR Accuracy */}
                  <td className="py-3 px-4 whitespace-nowrap font-mono text-[11px]">
                    {cert.ocr_accuracy != null ? (
                      <span className="text-slate-700 font-medium">
                        {Math.round(cert.ocr_accuracy * 100)}%
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>

                  {/* Trust Score */}
                  <td className="py-3 px-4 whitespace-nowrap font-mono text-[11px]">
                    {cert.trust_score != null ? (
                      <span
                        className={`font-semibold ${
                          cert.trust_score >= 70
                            ? "text-emerald-600"
                            : cert.trust_score >= 40
                            ? "text-amber-600"
                            : "text-rose-600"
                        }`}
                      >
                        {Math.round(cert.trust_score)} / 100
                      </span>
                    ) : (
                      <span className="text-slate-400">Pending</span>
                    )}
                  </td>

                  {/* Final Verdict Badge */}
                  <td className="py-3 px-4 whitespace-nowrap">
                    {renderVerdictBadge(cert.prediction_label)}
                  </td>

                  {/* Actions: View & Download PDF */}
                  <td className="py-3 px-4 text-right whitespace-nowrap">
                    <div className="inline-flex items-center gap-1.5">
                      {cert.has_report && (
                        <button
                          onClick={() =>
                            onDownloadReport(cert.id, cert.verification_id)
                          }
                          disabled={downloadingId === cert.id}
                          title="Download Signed PDF Report"
                          className="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors"
                        >
                          {downloadingId === cert.id ? (
                            <Loader2 size={13} className="animate-spin" />
                          ) : (
                            <Download size={13} />
                          )}
                        </button>
                      )}

                      <Link
                        href={`/dashboard/certificates/${cert.id}`}
                        className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 rounded-lg border border-indigo-100 font-medium transition-colors"
                      >
                        <span>Inspect</span>
                        <ExternalLink size={11} />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

