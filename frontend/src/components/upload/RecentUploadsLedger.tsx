"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  FileText,
  ImageIcon,
  Eye,
  ScanSearch,
  Trash2,
  Loader2,
  GitCompare,
  Tag,
  BookOpen,
  ChevronDown,
  Copy,
  Check,
  Search,
  Hash,
  ExternalLink,
} from "lucide-react";
import { CertificateResponse, certificateApi } from "@/lib/api";
import { MANUAL_DOC_TYPES } from "./CertificateDropzone";
import { Badge } from "@/components/ui/Badge";

const DOC_TYPE_LABELS: Record<string, string> = {
  degree_certificate: "Degree Certificate",
  marksheet: "SSLC / Marksheet",
  diploma: "Diploma Certificate",
  resume: "Resume / CV",
  transfer_certificate: "Transfer Certificate",
  experience_certificate: "Experience Certificate",
  aadhaar_card: "Aadhaar Card",
  identity_card: "Identity Card",
  unknown: "Unknown Document",
};

interface RecentUploadsLedgerProps {
  certificates: CertificateResponse[];
  docTypes: Record<string, { label: string; confidence: number } | "loading" | undefined>;
  ocrRunning: Record<string, boolean>;
  certDocTypes: Record<string, string>;
  deletingId: string | null;
  onRunOcr: (certId: string) => void;
  onDelete: (id: string, filename: string) => void;
  onCertDocTypeChange: (certId: string, type: string) => void;
}

export const RecentUploadsLedger: React.FC<RecentUploadsLedgerProps> = ({
  certificates,
  docTypes,
  ocrRunning,
  certDocTypes,
  deletingId,
  onRunOcr,
  onDelete,
  onCertDocTypeChange,
}) => {
  const [search, setSearch] = useState("");
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  const handleCopyHash = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  // Group certificates by group_id or certificate id
  const grouped: Record<string, CertificateResponse[]> = {};
  for (const cert of certificates) {
    const key = cert.group_id || cert.id;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(cert);
  }

  // Filter groups
  const filteredGroups = Object.entries(grouped).filter(([, group]) =>
    group.some(
      (c) =>
        c.original_filename.toLowerCase().includes(search.toLowerCase()) ||
        c.sha256_hash.toLowerCase().includes(search.toLowerCase()) ||
        c.id.toLowerCase().includes(search.toLowerCase())
    )
  );

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
      {/* Header with Search */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-slate-900 tracking-tight">
            Ingested Credentials Registry ({certificates.length})
          </h2>
        </div>

        {certificates.length > 0 && (
          <div className="relative w-full sm:w-64">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <input
              type="text"
              placeholder="Filter by filename or hash..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-900 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 transition-colors"
            />
          </div>
        )}
      </div>

      {/* Empty State */}
      {certificates.length === 0 ? (
        <div className="text-center py-10 border border-dashed border-slate-200 rounded-xl bg-slate-50/50">
          <FileText size={32} className="mx-auto text-slate-300 mb-2" />
          <p className="text-sm font-semibold text-slate-700">
            No Credentials Ingested Yet
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Drag and drop certificates above to populate the ledger.
          </p>
        </div>
      ) : filteredGroups.length === 0 ? (
        <div className="text-center py-8 text-xs text-slate-400">
          No records match filter query &quot;{search}&quot;.
        </div>
      ) : (
        <div className="space-y-4">
          {filteredGroups.map(([groupId, group]) => (
            <div key={groupId} className="space-y-2">
              {group.length > 1 && (
                <div className="flex items-center justify-between px-2 text-xs text-slate-500">
                  <span className="text-[11px] font-semibold flex items-center gap-1.5 text-indigo-600">
                    <GitCompare size={13} />
                    Document Batch ({group.length} linked credentials)
                  </span>
                  <Link
                    href={`/dashboard/groups/${groupId}`}
                    className="flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 hover:underline"
                  >
                    Compare Set <ExternalLink size={10} />
                  </Link>
                </div>
              )}

              {group.map((cert) => {
                const isPdf = cert.file_type.toLowerCase() === "pdf";
                const classification = docTypes[cert.id];
                const isClassifying = classification === "loading";
                const isOcrActive = ocrRunning[cert.id];

                return (
                  <div
                    key={cert.id}
                    className="bg-white border border-slate-200 hover:border-slate-300 rounded-xl p-4 transition-all shadow-xs space-y-3"
                  >
                    {/* Top Row: File details, Badges, Actions */}
                    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                      {/* File Icon & Info */}
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center shrink-0">
                          {isPdf ? (
                            <FileText size={18} className="text-indigo-600" />
                          ) : (
                            <ImageIcon size={18} className="text-emerald-600" />
                          )}
                        </div>

                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-slate-900 truncate">
                            {cert.original_filename}
                          </p>
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400 mt-0.5">
                            <span>{(cert.file_size_bytes / 1024).toFixed(0)} KB</span>
                            <span>•</span>
                            <span>{new Date(cert.uploaded_at).toLocaleString()}</span>
                            <span>•</span>
                            <span className="font-mono">ID: {cert.id.slice(0, 8)}</span>
                          </div>
                        </div>
                      </div>

                      {/* Right: Badges & Actions */}
                      <div className="flex flex-wrap items-center gap-2 shrink-0">
                        {/* Classification badge */}
                        {isClassifying && (
                          <span className="flex items-center gap-1 text-xs text-slate-500 px-2.5 py-1 rounded-md bg-slate-100 border border-slate-200">
                            <Loader2 size={11} className="animate-spin text-indigo-600" />
                            Classifying...
                          </span>
                        )}
                        {classification && classification !== "loading" && (
                          <Badge variant="brand" size="sm">
                            <Tag size={10} className="mr-1" />
                            {DOC_TYPE_LABELS[classification.label] || classification.label}
                            {classification.confidence != null && (
                              <span className="ml-1 opacity-75">
                                ({(classification.confidence * 100).toFixed(0)}%)
                              </span>
                            )}
                          </Badge>
                        )}

                        {/* Preview */}
                        <a
                          href={certificateApi.previewUrl(cert.id)}
                          target="_blank"
                          rel="noreferrer"
                          className="p-2 rounded-lg border border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors"
                          title="Preview Document"
                          aria-label="Preview Document"
                        >
                          <Eye size={15} />
                        </a>

                        {/* Cockpit link */}
                        <Link
                          href={`/dashboard/certificates/${cert.id}`}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-700 hover:bg-indigo-100 text-xs font-semibold transition-colors"
                          title="Open Verification Cockpit"
                        >
                          <ScanSearch size={14} />
                          <span>Inspect Cockpit</span>
                        </Link>

                        {/* Delete */}
                        <button
                          id={`delete-cert-${cert.id}`}
                          onClick={() => onDelete(cert.id, cert.original_filename)}
                          disabled={deletingId === cert.id}
                          className="p-2 rounded-lg border border-slate-200 text-slate-400 hover:text-red-600 hover:bg-red-50 hover:border-red-200 transition-colors disabled:opacity-40 cursor-pointer"
                          title="Delete Certificate"
                          aria-label="Delete Certificate"
                        >
                          {deletingId === cert.id ? (
                            <Loader2 size={15} className="animate-spin text-red-600" />
                          ) : (
                            <Trash2 size={15} />
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Middle Row: Cryptographic SHA-256 Hash Display */}
                    <div className="flex items-center justify-between gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200/80 rounded-lg">
                      <div className="flex items-center gap-1.5 min-w-0 font-mono text-[11px]">
                        <Hash size={12} className="text-emerald-600 shrink-0" />
                        <span className="text-slate-500 font-semibold shrink-0">SHA-256:</span>
                        <span className="text-slate-700 truncate select-all">
                          {cert.sha256_hash}
                        </span>
                      </div>
                      <button
                        onClick={() => handleCopyHash(cert.sha256_hash)}
                        className="p-1 text-slate-400 hover:text-slate-700 transition-colors shrink-0 cursor-pointer"
                        title="Copy SHA-256 hash"
                        aria-label="Copy SHA-256 hash"
                      >
                        {copiedHash === cert.sha256_hash ? (
                          <Check size={13} className="text-emerald-600" />
                        ) : (
                          <Copy size={13} />
                        )}
                      </button>
                    </div>

                    {/* Bottom Row: OCR Engine Trigger */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-2 border-t border-slate-100">
                      <div className="flex items-center gap-2 flex-1">
                        <BookOpen size={13} className="text-slate-400 shrink-0" />
                        <span className="text-xs font-semibold text-slate-600 shrink-0">
                          OCR Mode:
                        </span>
                        <div className="relative flex-1 max-w-xs">
                          <select
                            value={certDocTypes[cert.id] || ""}
                            onChange={(e) => onCertDocTypeChange(cert.id, e.target.value)}
                            id={`cert-doc-type-${cert.id}`}
                            aria-label="Document type for OCR"
                            className="w-full appearance-none bg-white border border-slate-200 rounded-lg px-2.5 py-1 pr-6 text-xs text-slate-800 focus:outline-none focus:border-indigo-600 cursor-pointer shadow-xs"
                          >
                            <option value="">Auto-Detect Layout Schema</option>
                            {MANUAL_DOC_TYPES.map((t) => (
                              <option key={t.value} value={t.value}>
                                {t.label}
                              </option>
                            ))}
                          </select>
                          <ChevronDown
                            size={12}
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
                          />
                        </div>
                      </div>

                      <button
                        id={`run-ocr-${cert.id}`}
                        onClick={() => onRunOcr(cert.id)}
                        disabled={isOcrActive}
                        className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors shadow-xs disabled:opacity-50 shrink-0 cursor-pointer"
                      >
                        {isOcrActive ? (
                          <>
                            <Loader2 size={13} className="animate-spin" />
                            <span>Extracting Neural OCR...</span>
                          </>
                        ) : (
                          <>
                            <ScanSearch size={13} />
                            <span>Run OCR Pipeline</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default RecentUploadsLedger;
