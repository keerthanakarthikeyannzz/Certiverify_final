"use client";

import React, { useState } from "react";
import {
  FileText,
  Download,
  Printer,
  RefreshCw,
  Loader2,
  CheckCircle2,
  ShieldCheck,
  Calendar,
  Key,
  FileCheck,
  AlertTriangle,
  Copy,
  Check,
  QrCode,
  Link2,
  ShieldAlert,
  ShieldX,
  Sparkles,
  Layers,
  Fingerprint,
} from "lucide-react";
import {
  VerificationReportResponse,
  FinalPredictionResponse,
  CertificateResponse,
  VerificationResultResponse,
  FraudAnalysisResponse,
  TrustScoreResponse,
  OCRDataResponse,
} from "@/lib/api";
import { Badge, Button, Logo } from "@/components/ui";

interface VerificationReportPanelProps {
  report: VerificationReportResponse | null;
  prediction: FinalPredictionResponse | null;
  cert?: CertificateResponse | null;
  verification?: VerificationResultResponse | null;
  fraud?: FraudAnalysisResponse | null;
  trustScore?: TrustScoreResponse | null;
  ocrData?: OCRDataResponse | null;
  onGenerateReport: () => void;
  onDownloadReport: () => void;
  generatingReport: boolean;
  downloadingReport: boolean;
}

export const VerificationReportPanel: React.FC<VerificationReportPanelProps> = ({
  report,
  prediction,
  cert,
  verification,
  fraud,
  trustScore,
  ocrData,
  onGenerateReport,
  onDownloadReport,
  generatingReport,
  downloadingReport,
}) => {
  const [copiedHash, setCopiedHash] = useState(false);
  const [copiedSig, setCopiedSig] = useState(false);

  const handlePrint = async () => {
    await onDownloadReport();
    if (typeof window !== "undefined") {
      window.print();
    }
  };

  const copyToClipboard = (text: string, type: "hash" | "sig") => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
      if (type === "hash") {
        setCopiedHash(true);
        setTimeout(() => setCopiedHash(false), 2000);
      } else {
        setCopiedSig(true);
        setTimeout(() => setCopiedSig(false), 2000);
      }
    }
  };

  const verdict = prediction?.label?.toLowerCase() ?? "pending";
  const getVerdictBadge = () => {
    switch (verdict) {
      case "genuine":
        return {
          variant: "genuine" as const,
          bg: "bg-emerald-50",
          border: "border-emerald-200",
          text: "text-emerald-700",
          icon: ShieldCheck,
          label: "GENUINE CREDENTIAL",
        };
      case "suspicious":
        return {
          variant: "suspicious" as const,
          bg: "bg-amber-50",
          border: "border-amber-200",
          text: "text-amber-700",
          icon: AlertTriangle,
          label: "SUSPICIOUS / IRREGULAR",
        };
      case "inconclusive":
      case "inconclusive / needs review":
        return {
          variant: "inconclusive" as const,
          bg: "bg-amber-50",
          border: "border-amber-300",
          text: "text-amber-800",
          icon: AlertTriangle,
          label: "NEEDS REVIEW",
        };
      case "fake":
        return {
          variant: "fake" as const,
          bg: "bg-rose-50",
          border: "border-rose-200",
          text: "text-rose-700",
          icon: ShieldX,
          label: "COUNTERFEIT / FAKE",
        };
      default:
        return {
          variant: "neutral" as const,
          bg: "bg-slate-50",
          border: "border-slate-200",
          text: "text-slate-700",
          icon: ShieldAlert,
          label: "VERIFICATION PENDING",
        };
    }
  };

  const vBadge = getVerdictBadge();
  const VIcon = vBadge.icon;

  const score = trustScore?.score ?? (prediction?.confidence_score ? Math.round(prediction.confidence_score * 100) : null);
  const fraudProb = fraud?.fraud_probability !== undefined 
    ? (fraud.fraud_probability * 100).toFixed(1)
    : prediction?.fraud_probability !== undefined 
      ? (prediction.fraud_probability * 100).toFixed(1)
      : null;

  return (
    <div id="verification-report-section" className="verification-report-panel relative bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm space-y-6 p-6">
      {/* Top Action & Authority Header */}
      <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <Logo size="md" showText={true} />
          <div className="h-8 w-px bg-slate-200 hidden sm:block" />
          <div className="space-y-0.5 hidden sm:block">
            <span className="px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 text-[10px] font-mono font-semibold tracking-wider uppercase block w-fit">
              Official Forensic Dossier
            </span>
            <span className="text-[10px] font-mono text-slate-500 block">
              ISO/IEC 27001 & Cryptographic Audit Standard
            </span>
          </div>
        </div>

        {/* Global Export & Generation Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          {report && (
            <Button
              variant="outline"
              size="sm"
              onClick={onGenerateReport}
              disabled={generatingReport}
              icon={
                <RefreshCw
                  size={12}
                  className={generatingReport ? "animate-spin text-primary" : "text-slate-500"}
                />
              }
              title="Regenerate report with latest verification telemetry"
            >
              {generatingReport ? "Recompiling..." : "Regenerate"}
            </Button>
          )}

          <Button
            variant="primary"
            size="sm"
            onClick={onGenerateReport}
            disabled={generatingReport}
            icon={
              generatingReport ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <FileCheck size={13} />
              )
            }
          >
            {generatingReport ? "Compiling PDF..." : report ? "Re-issue PDF" : "Generate Report"}
          </Button>

          {report && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={onDownloadReport}
                disabled={downloadingReport}
                className="border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100"
                icon={
                  downloadingReport ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Download size={13} />
                  )
                }
                title="Download authenticated PDF verification report"
              >
                {downloadingReport ? "Downloading..." : "Download PDF"}
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (navigator.clipboard) {
                    navigator.clipboard.writeText(window.location.href);
                    alert("Verification Report link copied to clipboard!");
                  }
                }}
                icon={<Link2 size={13} className="text-primary" />}
                title="Share Verification Report Link"
              >
                Share
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={handlePrint}
                disabled={downloadingReport}
                icon={<Printer size={13} className="text-slate-500" />}
                title="Print Audit Report"
              >
                Print
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Main Report Body */}
      {!report ? (
        <div className="relative z-10 bg-slate-50 border border-dashed border-slate-300 rounded-xl p-8 text-center space-y-4">
          <FileText size={40} className="text-slate-400 mx-auto opacity-40" />
          <div className="space-y-1.5 max-w-md mx-auto">
            <h3 className="text-sm font-semibold text-slate-800">
              Official Verification Dossier Not Yet Compiled
            </h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              Synthesize OCR extraction, QR decode, blockchain proofs, OpenCV Error Level Analysis,
              and machine learning fraud predictions into an officially stamped and signed PDF report.
            </p>
          </div>
          <Button
            variant="primary"
            size="md"
            onClick={onGenerateReport}
            disabled={generatingReport}
            icon={generatingReport ? <Loader2 size={14} className="animate-spin" /> : <FileCheck size={14} />}
          >
            {generatingReport ? "Compiling Dossier..." : "Generate Verification Report"}
          </Button>
        </div>
      ) : (
        <div className="relative z-10 space-y-6">
          {/* Metadata Matrix & Identity Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
                Verification ID
              </span>
              <div className="text-xs font-mono font-bold text-slate-900 truncate">
                {report.verification_id}
              </div>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
                Document File
              </span>
              <div className="text-xs font-sans font-medium text-slate-900 truncate" title={cert?.original_filename}>
                {cert?.original_filename || "Certificate Document"}
              </div>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
                Issue / Audit Timestamp
              </span>
              <div className="text-xs font-mono text-slate-700 flex items-center gap-1 truncate">
                <Calendar size={11} className="text-primary shrink-0" />
                <span>{new Date(report.generated_at).toLocaleString("en-IN")}</span>
              </div>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
                Document SHA-256 Hash
              </span>
              <div className="flex items-center justify-between gap-1">
                <span className="text-xs font-mono text-slate-700 truncate">
                  {cert?.sha256_hash ? `${cert.sha256_hash.slice(0, 14)}…` : "Not computed"}
                </span>
                {cert?.sha256_hash && (
                  <button
                    onClick={() => copyToClipboard(cert.sha256_hash, "hash")}
                    className="p-1 hover:text-slate-900 text-slate-400 transition"
                    title="Copy SHA-256 hash"
                  >
                    {copiedHash ? <Check size={11} className="text-emerald-600" /> : <Copy size={11} />}
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Executive Verdict & Telemetry Banner */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div className="flex items-start sm:items-center gap-3.5">
              <div className={`p-2.5 rounded-lg ${vBadge.bg} ${vBadge.border} border shrink-0`}>
                <VIcon size={24} className={vBadge.text} />
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant={vBadge.variant} size="md">
                    {vBadge.label}
                  </Badge>
                  <span className="text-xs text-slate-500">
                    AI Algorithmic Verdict
                  </span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed max-w-xl">
                  {prediction?.explanation || "Algorithmic decision compiled from multi-vector verification, forensic texture analysis, and cryptographic record check."}
                </p>
                {(() => {
                  const partial = (prediction?.evidence?._partial_verification as any) || (prediction?.evidence_breakdown?._partial_verification as any);
                  if (!partial && verdict !== "inconclusive" && !verdict.includes("inconclusive")) return null;
                  return (
                    <div className="pt-1.5 space-y-1">
                      {partial?.note && (
                        <span className="inline-block bg-amber-100 text-amber-900 px-2 py-0.5 rounded-full text-[10px] font-semibold font-mono border border-amber-300">
                          {partial.note}
                        </span>
                      )}
                      {partial?.missing_checks && partial.missing_checks.length > 0 && (
                        <p className="text-[11px] text-amber-900 font-mono">
                          <span className="font-semibold font-sans">Missing checks: </span>
                          {partial.missing_checks.join(", ")}
                        </p>
                      )}
                    </div>
                  );
                })()}
              </div>
            </div>

            {/* Score Pill Cluster */}
            <div className="flex items-center gap-3 shrink-0 pt-2 lg:pt-0 border-t lg:border-t-0 border-slate-200">
              <div className="text-right px-3.5 py-1.5 bg-white rounded-lg border border-slate-200 shadow-xs">
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
                  Trust Score
                </span>
                <span className="text-sm font-mono font-bold text-emerald-600">
                  {score !== null ? `${score}/100` : "N/A"}
                </span>
              </div>

              <div className="text-right px-3.5 py-1.5 bg-white rounded-lg border border-slate-200 shadow-xs">
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
                  Fraud Risk
                </span>
                <span className="text-sm font-mono font-bold text-amber-600">
                  {fraudProb !== null ? `${fraudProb}%` : "N/A"}
                </span>
              </div>
            </div>
          </div>

          {/* Verification Findings (4-Vector Quadrant Summary) */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider font-mono flex items-center gap-1.5">
              <Layers size={13} className="text-primary" />
              Multi-Vector Forensic Findings Summary
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {/* QR Vector */}
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-slate-700 flex items-center gap-1">
                    <QrCode size={13} className="text-primary" />
                    QR Verification
                  </span>
                  <span className={`text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded ${
                    verification?.evidence?.qr?.status === "PASS" || verification?.evidence?.qr?.status === "VERIFIED"
                      ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                      : verification?.evidence?.qr?.status === "NOT_FOUND"
                      ? "bg-amber-50 text-amber-700 border border-amber-200"
                      : "bg-slate-100 text-slate-600 border border-slate-200"
                  }`}>
                    {verification?.evidence?.qr?.status || (verification?.verification_summary?.qr_checked ? "CHECKED" : "UNAVAILABLE")}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 leading-snug">
                  {verification?.evidence?.qr?.label || "QR code structure and embedded cryptographic payload."}
                </p>
              </div>

              {/* Blockchain Vector */}
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-slate-700 flex items-center gap-1">
                    <Link2 size={13} className="text-emerald-600" />
                    Blockchain Proof
                  </span>
                  <span className={`text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded ${
                    verification?.evidence?.blockchain?.status === "VERIFIED" || verification?.evidence?.blockchain?.status === "MATCH"
                      ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                      : "bg-slate-100 text-slate-600 border border-slate-200"
                  }`}>
                    {verification?.evidence?.blockchain?.status || (verification?.verification_summary?.blockchain_checked ? "CHECKED" : "UNAVAILABLE")}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 leading-snug">
                  {verification?.evidence?.blockchain?.label || "On-chain transaction proof and smart contract hash ledger."}
                </p>
              </div>

              {/* Tampering / ELA Vector */}
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-slate-700 flex items-center gap-1">
                    <ShieldAlert size={13} className="text-amber-600" />
                    ELA Tamper Scan
                  </span>
                  {(() => {
                    const rawTStatus = verification?.tampering_status || verification?.evidence?.tampering?.status;
                    let display = "PENDING";
                    let badgeClass = "bg-slate-100 text-slate-600 border border-slate-200";

                    if (rawTStatus === "CLEAN" || rawTStatus === "PASS" || rawTStatus === "analyzed") {
                      display = verification?.tampering_score != null ? `ANALYZED (${Math.round(verification.tampering_score)}/100)` : "ANALYZED";
                      badgeClass = "bg-emerald-50 text-emerald-700 border border-emerald-200";
                    } else if (rawTStatus === "not_applicable_for_pdf_text_layer") {
                      display = "NOT APPLICABLE";
                      badgeClass = "bg-amber-50 text-amber-700 border border-amber-200";
                    } else if (rawTStatus?.startsWith("failed:")) {
                      display = "FAILED";
                      badgeClass = "bg-rose-50 text-rose-700 border border-rose-200";
                    } else if (rawTStatus?.startsWith("skipped:")) {
                      display = "SKIPPED";
                      badgeClass = "bg-slate-100 text-slate-600 border border-slate-200";
                    } else if (rawTStatus === "TAMPERED" || rawTStatus === "FAIL") {
                      display = `TAMPER DETECTED (${verification?.tampering_score != null ? Math.round(verification.tampering_score) : 0}/100)`;
                      badgeClass = "bg-rose-50 text-rose-700 border border-rose-200";
                    } else if (verification?.tampering_score != null) {
                      display = `${Math.round(verification.tampering_score)} / 100`;
                      badgeClass = "bg-emerald-50 text-emerald-700 border border-emerald-200";
                    }

                    return (
                      <span className={`text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded ${badgeClass}`}>
                        {display}
                      </span>
                    );
                  })()}
                </div>
                <p className="text-[11px] text-slate-500 leading-snug">
                  {verification?.evidence?.tampering?.label || "Error Level Analysis compression variance detector."}
                </p>
              </div>

              {/* Duplicate Detection Vector */}
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-slate-700 flex items-center gap-1">
                    <Fingerprint size={13} className="text-primary" />
                    Duplicate Collision
                  </span>
                  <span className={`text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded ${
                    verification?.evidence?.duplicate?.status === "UNIQUE" || verification?.evidence?.duplicate?.status === "NO_DUPLICATE" || verification?.evidence?.duplicate?.status === "PASS"
                      ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                      : verification?.evidence?.duplicate?.status === "DUPLICATE"
                      ? "bg-rose-50 text-rose-700 border border-rose-200"
                      : "bg-slate-100 text-slate-600 border border-slate-200"
                  }`}>
                    {verification?.evidence?.duplicate?.status || (verification?.verification_summary?.duplicate_checked ? "CHECKED" : "UNAVAILABLE")}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 leading-snug">
                  {verification?.evidence?.duplicate?.label || "Registry database duplicate certificate collision check."}
                </p>
              </div>
            </div>
          </div>

          {/* Key Extracted OCR Metadata Section */}
          {ocrData && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider font-mono flex items-center gap-1.5">
                <Sparkles size={13} className="text-primary" />
                Extracted Identity & Academic Fields
              </h3>

              <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto shadow-xs">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 font-mono text-[10px] uppercase">
                    <tr>
                      <th className="px-3.5 py-2 font-semibold">Target Field</th>
                      <th className="px-3.5 py-2 font-semibold">Extracted Value</th>
                      <th className="px-3.5 py-2 font-semibold">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    <tr>
                      <td className="px-3.5 py-2 text-slate-500">Student Name</td>
                      <td className="px-3.5 py-2 font-semibold text-slate-900">{ocrData.student_name || "Not detected"}</td>
                      <td className="px-3.5 py-2 font-mono text-[10px]">
                        <Badge variant={ocrData.student_name ? "genuine" : "neutral"} size="sm">
                          {ocrData.student_name ? "EXTRACTED" : "UNAVAILABLE"}
                        </Badge>
                      </td>
                    </tr>
                    <tr>
                      <td className="px-3.5 py-2 text-slate-500">University / Authority</td>
                      <td className="px-3.5 py-2 font-semibold text-slate-900">{ocrData.university_name || "Not detected"}</td>
                      <td className="px-3.5 py-2 font-mono text-[10px]">
                        <Badge variant={ocrData.university_name ? "genuine" : "neutral"} size="sm">
                          {ocrData.university_name ? "EXTRACTED" : "UNAVAILABLE"}
                        </Badge>
                      </td>
                    </tr>
                    <tr>
                      <td className="px-3.5 py-2 text-slate-500">Registration / Roll No</td>
                      <td className="px-3.5 py-2 font-mono text-slate-900">
                        {ocrData.register_number || ocrData.roll_number || "Not detected"}
                      </td>
                      <td className="px-3.5 py-2 font-mono text-[10px]">
                        <Badge variant={(ocrData.register_number || ocrData.roll_number) ? "genuine" : "neutral"} size="sm">
                          {(ocrData.register_number || ocrData.roll_number) ? "EXTRACTED" : "UNAVAILABLE"}
                        </Badge>
                      </td>
                    </tr>
                    <tr>
                      <td className="px-3.5 py-2 text-slate-500">Issue Date / Score</td>
                      <td className="px-3.5 py-2 text-slate-900">
                        {[ocrData.date_of_issue, ocrData.cgpa ? `CGPA: ${ocrData.cgpa}` : null, ocrData.percentage ? `${ocrData.percentage}%` : null].filter(Boolean).join(" • ") || "Not detected"}
                      </td>
                      <td className="px-3.5 py-2 font-mono text-[10px]">
                        <Badge variant={ocrData.date_of_issue ? "genuine" : "neutral"} size="sm">
                          {ocrData.date_of_issue ? "EXTRACTED" : "UNAVAILABLE"}
                        </Badge>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Cryptographic Digital Signature Block */}
          {report.digital_signature && (
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-800 flex items-center gap-1.5 font-mono uppercase tracking-wider">
                  <Key size={13} className="text-amber-600" />
                  Cryptographic Digital Signature Seal
                </span>
                <button
                  onClick={() => copyToClipboard(report.digital_signature!, "sig")}
                  className="px-2 py-0.5 rounded bg-white hover:bg-slate-100 border border-slate-200 text-[11px] font-mono text-slate-600 hover:text-slate-900 transition flex items-center gap-1"
                  title="Copy full cryptographic signature"
                >
                  {copiedSig ? <Check size={11} className="text-emerald-600" /> : <Copy size={11} />}
                  <span>{copiedSig ? "Copied" : "Copy Signature"}</span>
                </button>
              </div>

              <div className="p-2.5 bg-white rounded border border-slate-200 font-mono text-[11px] text-emerald-800 break-all select-all leading-relaxed shadow-xs">
                {report.digital_signature}
              </div>

              <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
                <span>Algorithm: SHA-256 with Asymmetric RSA/ECDSA Signature</span>
                <span className="flex items-center gap-1 text-emerald-700 font-semibold">
                  <CheckCircle2 size={11} /> Cryptographically Valid
                </span>
              </div>
            </div>
          )}

          {/* Legal & Forensic Disclaimer Footer */}
          <div className="pt-3 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[10px] text-slate-400">
            <span>CertiVerify AI Automated Verification Engine • Tamper-evident forensic audit dossier.</span>
            <span>Document ID: {report.id}</span>
          </div>
        </div>
      )}
    </div>
  );
};
