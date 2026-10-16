"use client";

import React, { useState } from "react";
import {
  QrCode,
  Link2,
  ImageIcon,
  Copy,
  Loader2,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
} from "lucide-react";
import { VerificationResultResponse } from "@/lib/api";
import { Button } from "@/components/ui/Button";

interface ForensicSignalsGridProps {
  verification: VerificationResultResponse | null;
  certificateId: string;
  onVerifyQr: () => void;
  onVerifyBlockchain: () => void;
  onVerifyTampering: () => void;
  onVerifyDuplicate: () => void;
  verifyingQr: boolean;
  verifyingChain: boolean;
  verifyingTampering: boolean;
  verifyingDuplicate: boolean;
}

export const ForensicSignalsGrid: React.FC<ForensicSignalsGridProps> = ({
  verification,
  onVerifyQr,
  onVerifyBlockchain,
  onVerifyTampering,
  onVerifyDuplicate,
  verifyingQr,
  verifyingChain,
  verifyingTampering,
  verifyingDuplicate,
}) => {
  const [showTamperingDetail, setShowTamperingDetail] = useState(false);
  const [showDuplicateDetail, setShowDuplicateDetail] = useState(false);

  // 1. QR Status
  const qrStatus = verification?.qr_valid;
  const qrPresent = verification?.qr_present;
  const qrWarning = verification?.qr_warning;

  // 2. Blockchain Status
  const chainStatus = verification?.blockchain_status;

  // 3. Tampering
  const tamperingScore = verification?.tampering_score;
  const tamperingDetail = verification?.tampering_detail;
  const tamperingStatus = verification?.tampering_status;

  // 4. Duplicate
  const isDuplicate = verification?.is_duplicate;
  const duplicateDetail = verification?.duplicate_detail;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900 tracking-tight flex items-center gap-2">
          <ShieldAlert size={16} className="text-indigo-600" />
          Forensic Signal Quadrant
        </h3>
        <span className="text-xs text-slate-500">
          4 Independent Forensic Vectors
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Vector 1: Digital QR Verification */}
        <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between space-y-4 shadow-sm">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                <QrCode size={15} className="text-indigo-600" />
                QR Verification
              </span>
              <span
                className={`text-[11px] font-semibold px-2 py-0.5 rounded-md border ${
                  qrPresent === undefined
                    ? "text-slate-600 border-slate-200 bg-slate-50"
                    : !qrPresent
                    ? "text-amber-700 border-amber-200 bg-amber-50"
                    : qrStatus
                    ? "text-emerald-700 border-emerald-200 bg-emerald-50"
                    : "text-red-700 border-red-200 bg-red-50"
                }`}
              >
                {qrPresent === undefined
                  ? "PENDING"
                  : !qrPresent
                  ? "NO QR"
                  : qrStatus
                  ? "VERIFIED"
                  : "INVALID"}
              </span>
            </div>

            <div className="text-xs text-slate-600 space-y-1">
              {qrPresent === undefined ? (
                <p className="text-slate-400">Execute scan to detect digital cryptographic QR.</p>
              ) : !qrPresent ? (
                <p className="text-slate-500">No QR code detected in document boundaries.</p>
              ) : (
                <>
                  <p className={qrStatus ? "text-emerald-700 font-medium" : "text-red-700 font-medium"}>
                    {qrStatus ? "Digital payload signature valid." : "QR payload parsing failed."}
                  </p>
                  {qrWarning && <p className="text-[11px] text-amber-700">⚠ {qrWarning}</p>}
                </>
              )}
            </div>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={onVerifyQr}
            disabled={verifyingQr}
            className="w-full"
          >
            {verifyingQr && <Loader2 size={12} className="animate-spin" />}
            <span>{qrPresent !== undefined ? "Re-scan QR" : "Run QR Check"}</span>
          </Button>
        </div>

        {/* Vector 2: Blockchain Ledger */}
        <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between space-y-4 shadow-sm">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                <Link2 size={15} className="text-indigo-600" />
                Blockchain Ledger
              </span>
              <span
                className={`text-[11px] font-semibold px-2 py-0.5 rounded-md border ${
                  !chainStatus
                    ? "text-slate-600 border-slate-200 bg-slate-50"
                    : chainStatus === "verified"
                    ? "text-emerald-700 border-emerald-200 bg-emerald-50"
                    : chainStatus === "not_found"
                    ? "text-amber-700 border-amber-200 bg-amber-50"
                    : "text-red-700 border-red-200 bg-red-50"
                }`}
              >
                {chainStatus ? chainStatus.toUpperCase() : "PENDING"}
              </span>
            </div>

            <div className="text-xs text-slate-600 space-y-1">
              {!chainStatus ? (
                <p className="text-slate-400">Verify document hash against distributed ledger.</p>
              ) : chainStatus === "verified" ? (
                <div>
                  <p className="text-emerald-700 font-medium">Cryptographic hash registered on-chain.</p>
                  {verification?.blockchain_tx_hash && (
                    <p className="text-[10px] font-mono text-slate-400 truncate mt-1">
                      TX: {verification.blockchain_tx_hash.slice(0, 16)}…
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-amber-700">Hash not found or network node unconfigured.</p>
              )}
            </div>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={onVerifyBlockchain}
            disabled={verifyingChain}
            className="w-full"
          >
            {verifyingChain && <Loader2 size={12} className="animate-spin" />}
            <span>{chainStatus ? "Re-query Ledger" : "Query Blockchain"}</span>
          </Button>
        </div>

        {/* Vector 3: Tampering & Image Forensics */}
        <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between space-y-4 shadow-sm">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                <ImageIcon size={15} className="text-indigo-600" />
                Tampering Analysis
              </span>
              <span
                className={`text-[11px] font-semibold px-2 py-0.5 rounded-md border ${
                  tamperingStatus === "not_applicable_for_pdf_text_layer"
                    ? "text-amber-700 border-amber-200 bg-amber-50"
                    : tamperingStatus?.startsWith("failed:")
                    ? "text-red-700 border-red-200 bg-red-50"
                    : tamperingScore === undefined || tamperingScore === null
                    ? "text-slate-600 border-slate-200 bg-slate-50"
                    : tamperingScore < 30
                    ? "text-emerald-700 border-emerald-200 bg-emerald-50"
                    : tamperingScore < 60
                    ? "text-amber-700 border-amber-200 bg-amber-50"
                    : "text-red-700 border-red-200 bg-red-50"
                }`}
              >
                {tamperingStatus === "not_applicable_for_pdf_text_layer"
                  ? "NOT APPLICABLE"
                  : tamperingStatus?.startsWith("failed:")
                  ? "FAILED"
                  : tamperingStatus?.startsWith("skipped:")
                  ? "SKIPPED"
                  : tamperingScore !== undefined && tamperingScore !== null
                  ? `${Math.round(tamperingScore)} / 100`
                  : "PENDING"}
              </span>
            </div>

            <div className="text-xs text-slate-600 space-y-1">
              {tamperingStatus === "not_applicable_for_pdf_text_layer" ? (
                <p className="text-amber-700 font-medium">
                  Not applicable for digital PDF text layer (vector document).
                </p>
              ) : tamperingStatus?.startsWith("failed:") ? (
                <p className="text-red-700 font-medium">
                  Scan error: {tamperingStatus.replace(/^failed:\s*/, "")}
                </p>
              ) : tamperingStatus?.startsWith("skipped:") ? (
                <p className="text-slate-500">
                  Skipped: {tamperingStatus.replace(/^skipped:\s*/, "")}
                </p>
              ) : tamperingScore === undefined || tamperingScore === null ? (
                <p className="text-slate-400">ELA, clone, and font anomaly inspection.</p>
              ) : (
                <div>
                  <p
                    className={
                      tamperingScore < 30
                        ? "text-emerald-700 font-medium"
                        : tamperingScore < 60
                        ? "text-amber-700 font-medium"
                        : "text-red-700 font-medium"
                    }
                  >
                    {tamperingScore < 30
                      ? "Low tampering risk detected (analyzed)."
                      : tamperingScore < 60
                      ? "Minor visual anomalies detected (analyzed)."
                      : "High probability of image manipulation (analyzed)."}
                  </p>
                  {tamperingDetail && (
                    <button
                      onClick={() => setShowTamperingDetail(!showTamperingDetail)}
                      className="text-[11px] text-indigo-600 hover:underline flex items-center gap-0.5 mt-1 cursor-pointer font-medium"
                    >
                      {showTamperingDetail ? "Hide sub-signals" : "Show sub-signals"}
                      {showTamperingDetail ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={onVerifyTampering}
            disabled={verifyingTampering}
            className="w-full"
          >
            {verifyingTampering && <Loader2 size={12} className="animate-spin" />}
            <span>{tamperingScore !== undefined ? "Re-run Tampering" : "Run Tampering"}</span>
          </Button>
        </div>

        {/* Vector 4: Duplicate & Conflict Detection */}
        <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between space-y-4 shadow-sm">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                <Copy size={15} className="text-indigo-600" />
                Duplicate Detection
              </span>
              <span
                className={`text-[11px] font-semibold px-2 py-0.5 rounded-md border ${
                  isDuplicate === undefined
                    ? "text-slate-600 border-slate-200 bg-slate-50"
                    : !isDuplicate
                    ? "text-emerald-700 border-emerald-200 bg-emerald-50"
                    : "text-red-700 border-red-200 bg-red-50"
                }`}
              >
                {isDuplicate === undefined
                  ? "PENDING"
                  : !isDuplicate
                  ? "UNIQUE"
                  : "DUPLICATE"}
              </span>
            </div>

            <div className="text-xs text-slate-600 space-y-1">
              {isDuplicate === undefined ? (
                <p className="text-slate-400">Check hash, serial & visual dHash across registry.</p>
              ) : (
                <div>
                  <p className={!isDuplicate ? "text-emerald-700 font-medium" : "text-red-700 font-medium"}>
                    {!isDuplicate
                      ? "No conflicting certificate records."
                      : "Conflict or duplicate detected."}
                  </p>
                  {duplicateDetail && (
                    <button
                      onClick={() => setShowDuplicateDetail(!showDuplicateDetail)}
                      className="text-[11px] text-indigo-600 hover:underline flex items-center gap-0.5 mt-1 cursor-pointer font-medium"
                    >
                      {showDuplicateDetail ? "Hide details" : "Show details"}
                      {showDuplicateDetail ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={onVerifyDuplicate}
            disabled={verifyingDuplicate}
            className="w-full"
          >
            {verifyingDuplicate && <Loader2 size={12} className="animate-spin" />}
            <span>{isDuplicate !== undefined ? "Re-check Duplicates" : "Check Duplicates"}</span>
          </Button>
        </div>
      </div>

      {/* Expanded Tampering Forensic Sub-signals */}
      {showTamperingDetail && tamperingDetail && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs space-y-3">
          <div className="flex items-center justify-between border-b border-slate-200/80 pb-2">
            <span className="font-semibold text-slate-800">
              Deep Tampering & Signal Analysis
            </span>
            <span className="text-slate-500 font-medium">
              Overall Risk: {verification?.tampering_risk_level || "EVALUATED"}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-white p-3 rounded-lg border border-slate-200">
              <p className="text-[10px] text-slate-400 uppercase font-semibold">Image Quality</p>
              <p className="text-sm font-bold text-slate-800 mt-0.5">
                {tamperingDetail.image_quality?.score != null
                  ? `${Math.round(tamperingDetail.image_quality.score)}/100`
                  : "—"}
              </p>
            </div>
            <div className="bg-white p-3 rounded-lg border border-slate-200">
              <p className="text-[10px] text-slate-400 uppercase font-semibold">ELA Compression</p>
              <p className="text-sm font-bold text-slate-800 mt-0.5">
                {tamperingDetail.ela?.risk != null
                  ? `${Math.round(tamperingDetail.ela.risk)}% Risk`
                  : "—"}
              </p>
            </div>
            <div className="bg-white p-3 rounded-lg border border-slate-200">
              <p className="text-[10px] text-slate-400 uppercase font-semibold">Copy-Paste / Clone</p>
              <p className="text-sm font-bold text-slate-800 mt-0.5">
                {tamperingDetail.copy_paste?.detected ? "DETECTED" : "NONE"}
              </p>
            </div>
            <div className="bg-white p-3 rounded-lg border border-slate-200">
              <p className="text-[10px] text-slate-400 uppercase font-semibold">Font Consistency</p>
              <p className="text-sm font-bold text-slate-800 mt-0.5">
                {tamperingDetail.font_consistency?.score != null
                  ? `${Math.round(tamperingDetail.font_consistency.score)}/100`
                  : "—"}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Expanded Duplicate Detection Signals */}
      {showDuplicateDetail && duplicateDetail && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs space-y-3">
          <div className="flex items-center justify-between border-b border-slate-200/80 pb-2">
            <span className="font-semibold text-slate-800">
              Duplicate & Conflict Sub-signals
            </span>
            <span className="text-slate-500 font-medium">Status: {duplicateDetail.duplicate_status}</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="p-2.5 bg-white rounded-lg border border-slate-200">
              <span className="text-slate-400 block text-[10px] font-semibold uppercase">File Hash Match</span>
              <span className="font-semibold text-slate-800">
                {duplicateDetail.file_hash_match ? "YES (Match)" : "NO"}
              </span>
            </div>
            <div className="p-2.5 bg-white rounded-lg border border-slate-200">
              <span className="text-slate-400 block text-[10px] font-semibold uppercase">Certificate Number</span>
              <span className="font-semibold text-slate-800">
                {duplicateDetail.certificate_number_match ? "YES (Match)" : "NO"}
              </span>
            </div>
            <div className="p-2.5 bg-white rounded-lg border border-slate-200">
              <span className="text-slate-400 block text-[10px] font-semibold uppercase">Field Similarity</span>
              <span className="font-semibold text-slate-800">
                {Math.round(duplicateDetail.field_similarity)}%
              </span>
            </div>
            <div className="p-2.5 bg-white rounded-lg border border-slate-200">
              <span className="text-slate-400 block text-[10px] font-semibold uppercase">Visual Similarity</span>
              <span className="font-semibold text-slate-800">
                {Math.round(duplicateDetail.visual_similarity)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ForensicSignalsGrid;
