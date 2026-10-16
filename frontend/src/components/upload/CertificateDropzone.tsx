"use client";

import React from "react";
import { UploadCloud, FileType, CheckCircle2 } from "lucide-react";
import { Select } from "@/components/ui/Select";

export const MANUAL_DOC_TYPES: { value: string; label: string }[] = [
  { value: "degree_certificate", label: "Degree Certificate" },
  { value: "marksheet", label: "SSLC / Marksheet" },
  { value: "diploma", label: "Diploma Certificate" },
  { value: "transfer_certificate", label: "Transfer Certificate" },
  { value: "aadhaar_card", label: "Aadhaar Card" },
  { value: "resume", label: "Resume / CV" },
];

interface CertificateDropzoneProps {
  selectedDocType: string;
  onDocTypeChange: (val: string) => void;
  getRootProps: () => Record<string, unknown>;
  getInputProps: () => Record<string, unknown>;
  isDragActive: boolean;
  disabled?: boolean;
}

export const CertificateDropzone: React.FC<CertificateDropzoneProps> = ({
  selectedDocType,
  onDocTypeChange,
  getRootProps,
  getInputProps,
  isDragActive,
  disabled,
}) => {
  return (
    <div className="space-y-4">
      {/* Step 1: Pre-Ingestion Classification Tag */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-2">
            <span className="w-5 h-5 rounded-md bg-indigo-50 border border-indigo-100 text-indigo-700 text-[11px] font-bold flex items-center justify-center">
              01
            </span>
            <span className="text-xs font-semibold text-slate-800 uppercase tracking-wide">
              Document Classification (Optional)
            </span>
          </div>
          <span className="text-xs text-slate-500">
            Auto-detected by neural model if left blank
          </span>
        </div>

        <Select
          id="doc-type-selector"
          value={selectedDocType}
          onChange={(e) => onDocTypeChange(e.target.value)}
          disabled={disabled}
        >
          <option value="">— Auto-Detect Document Classification —</option>
          {MANUAL_DOC_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </Select>
      </div>

      {/* Step 2: Large Dropzone */}
      <div
        {...getRootProps()}
        className={`relative border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center transition-all duration-200 cursor-pointer select-none bg-white shadow-sm ${
          isDragActive
            ? "border-indigo-600 bg-indigo-50/50 scale-[1.01]"
            : "border-slate-300 hover:border-indigo-500 hover:bg-slate-50/60"
        } ${disabled ? "opacity-50 cursor-not-allowed pointer-events-none" : ""}`}
      >
        <input {...getInputProps()} />

        <div className="flex flex-col items-center justify-center space-y-3">
          <div
            className={`w-16 h-16 rounded-2xl flex items-center justify-center transition-transform duration-200 ${
              isDragActive
                ? "bg-indigo-600 text-white scale-110 shadow-md"
                : "bg-indigo-50 text-indigo-600"
            }`}
          >
            <UploadCloud className="w-8 h-8" />
          </div>

          <div className="space-y-1">
            <p className="text-base font-semibold text-slate-900 tracking-tight">
              {isDragActive
                ? "Drop certificate files right here..."
                : "Drag & drop certificates or click to browse"}
            </p>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Supports standard institutional formats. Maximum file size per document is 15 MB.
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
            {["PDF", "PNG", "JPG", "JPEG"].map((fmt) => (
              <span
                key={fmt}
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-md"
              >
                <FileType className="w-3 h-3 text-indigo-600" />
                {fmt}
              </span>
            ))}
          </div>

          <div className="flex items-center gap-1.5 text-[11px] text-emerald-700 font-medium pt-2">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            <span>Encrypted transmission & automated integrity analysis</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CertificateDropzone;
