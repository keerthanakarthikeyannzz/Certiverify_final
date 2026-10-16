"use client";

import React from "react";
import Link from "next/link";
import {
  ShieldCheck,
  AlertTriangle,
  ShieldX,
  FileText,
  Download,
  QrCode,
  Link2,
  ShieldAlert,
  Fingerprint,
  CheckCircle2,
  Layers,
  Sparkles,
  Loader2,
  FileCheck,
} from "lucide-react";
import {
  FinalPredictionResponse,
  TrustScoreResponse,
  FraudAnalysisResponse,
  VerificationResultResponse,
  OCRDataResponse,
  DocumentTypeResponse,
  DocumentValidationResponse,
  VerificationReportResponse,
  CertificateResponse,
} from "@/lib/api";
import { Badge, Button } from "@/components/ui";

interface CompleteVerificationResultCardProps {
  prediction: FinalPredictionResponse | null;
  trustScore: TrustScoreResponse | null;
  fraud: FraudAnalysisResponse | null;
  verification: VerificationResultResponse | null;
  ocrData: OCRDataResponse | null;
  docType: DocumentTypeResponse | null;
  validation: DocumentValidationResponse | null;
  report: VerificationReportResponse | null;
  cert: CertificateResponse | null;
  onViewReport: () => void;
  onDownloadReport: () => void;
  downloadingReport: boolean;
}

export const CompleteVerificationResultCard: React.FC<CompleteVerificationResultCardProps> = ({
  prediction,
  trustScore,
  fraud,
  verification,
  ocrData,
  docType,
  validation,
  report,
  cert,
  onViewReport,
  onDownloadReport,
  downloadingReport,
}) => {
  if (!prediction) return null;

  const verdict = prediction.label.toLowerCase();

  const getVerdictTheme = () => {
    switch (verdict) {
      case "genuine":
        return {
          variant: "genuine" as const,
          badgeBg: "bg-emerald-50",
          badgeBorder: "border-emerald-200",
          badgeText: "text-emerald-700",
          bannerBg: "bg-emerald-50/60",
          border: "border-emerald-200",
          icon: ShieldCheck,
          label: "GENUINE CERTIFICATE",
          statusText: "Verified Authentic & Tamper-Free",
        };
      case "suspicious":
        return {
          variant: "suspicious" as const,
          badgeBg: "bg-amber-50",
          badgeBorder: "border-amber-200",
          badgeText: "text-amber-700",
          bannerBg: "bg-amber-50/60",
          border: "border-amber-200",
          icon: AlertTriangle,
          label: "SUSPICIOUS / IRREGULAR",
          statusText: "Anomalies Detected — Manual Review Required",
        };
      case "inconclusive":
      case "inconclusive / needs review":
        return {
          variant: "inconclusive" as const,
          badgeBg: "bg-amber-50",
          badgeBorder: "border-amber-300",
          badgeText: "text-amber-800",
          bannerBg: "bg-amber-50/70",
          border: "border-amber-200",
          icon: AlertTriangle,
          label: "NEEDS REVIEW / INCONCLUSIVE",
          statusText: "Inconclusive — Some Verification Signals Missing",
        };
      case "fake":
        return {
          variant: "fake" as const,
          badgeBg: "bg-rose-50",
          badgeBorder: "border-rose-200",
          badgeText: "text-rose-700",
          bannerBg: "bg-rose-50/60",
          border: "border-rose-200",
          icon: ShieldX,
          label: "FORGERY / COUNTERFEIT",
          statusText: "Evidence of Tampering or Discrepancy",
        };
      default:
        return {
          variant: "neutral" as const,
          badgeBg: "bg-slate-50",
          badgeBorder: "border-slate-200",
          badgeText: "text-slate-700",
          bannerBg: "bg-slate-50/60",
          border: "border-slate-200",
          icon: ShieldAlert,
          label: "VERIFICATION COMPLETED",
          statusText: "Analysis finalized",
        };
    }
  };

  const theme = getVerdictTheme();
  const VerdictIcon = theme.icon;

  const certificateType =
    docType?.predicted_type ||
    validation?.document_type?.replace(/_/g, " ") ||
    "Academic Credential";

  const predictionConfidence = Math.round(prediction.confidence_score * 100);
  const trustScoreValue = trustScore?.score !== undefined ? `${trustScore.score}/100` : null;
  const fraudProbabilityValue =
    fraud?.fraud_probability !== undefined
      ? `${(fraud.fraud_probability * 100).toFixed(1)}%`
      : prediction.fraud_probability !== undefined
      ? `${(prediction.fraud_probability * 100).toFixed(1)}%`
      : null;
  const ocrAccuracyValue =
    ocrData?.ocr_accuracy !== undefined ? `${Math.round(ocrData.ocr_accuracy * 100)}%` : null;

  const qrStatus = verification?.evidence?.qr?.status || (verification?.verification_summary?.qr_checked ? "CHECKED" : "UNAVAILABLE");
  const blockchainStatus = verification?.evidence?.blockchain?.status || (verification?.verification_summary?.blockchain_checked ? "CHECKED" : "NOT_REGISTERED");

  const rawTamperStatus =
    verification?.tampering_status ||
    verification?.evidence?.tampering?.status ||
    (prediction?.evidence_breakdown?._tampering as any)?.status ||
    (trustScore?.breakdown?.evidence_breakdown?._tampering as any)?.status;

  const formatTamperingText = () => {
    if (!rawTamperStatus) {
      if (verification?.tampering_score !== undefined && verification?.tampering_score !== null) {
        return `Analyzed (${Math.round(verification.tampering_score)}/100)`;
      }
      return "Not run";
    }
    if (rawTamperStatus === "analyzed") {
      return verification?.tampering_score != null
        ? `Analyzed (${Math.round(verification.tampering_score)}/100)`
        : "Analyzed";
    }
    if (rawTamperStatus === "not_applicable_for_pdf_text_layer") {
      return "Not applicable (PDF text layer)";
    }
    if (rawTamperStatus.startsWith("failed:")) {
      return `Failed (${rawTamperStatus.replace(/^failed:\s*/, "")})`;
    }
    if (rawTamperStatus.startsWith("skipped:")) {
      return `Skipped (${rawTamperStatus.replace(/^skipped:\s*/, "")})`;
    }
    if (rawTamperStatus === "CLEAN" || rawTamperStatus === "PASS" || rawTamperStatus === "NOT_DETECTED") {
      return "Not detected";
    }
    if (rawTamperStatus === "TAMPERED" || rawTamperStatus === "FAIL") {
      return `Tamper detected (${verification?.tampering_score != null ? Math.round(verification.tampering_score) : 0}/100)`;
    }
    return rawTamperStatus;
  };

  const duplicateStatus =
    verification?.evidence?.duplicate?.status === "UNIQUE" || verification?.evidence?.duplicate?.status === "NO_DUPLICATE" || verification?.evidence?.duplicate?.status === "PASS"
      ? "NOT_DETECTED"
      : verification?.evidence?.duplicate?.status || "UNAVAILABLE";

  return (
    <section 
      aria-label="Complete Certificate Verification Result"
      className={`bg-white border ${theme.border} rounded-xl p-6 shadow-sm space-y-6 relative overflow-hidden`}
    >
      {/* Top Banner & Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <div className={`p-2.5 rounded-lg ${theme.badgeBg} ${theme.badgeBorder} border shrink-0`}>
            <VerdictIcon size={24} className={theme.badgeText} />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-500">
                VERIFICATION RESULT
              </span>
              <Badge variant={theme.variant} size="md">
                {verdict === "genuine" ? "✓ " : verdict === "fake" ? "✕ " : "⚠ "}{theme.label}
              </Badge>
            </div>
            <p className="text-xs text-slate-500 font-mono mt-0.5">
              Certificate Type: <span className="text-slate-800 font-sans font-semibold capitalize">{certificateType}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {report && (
            <Button
              variant="primary"
              size="sm"
              onClick={onDownloadReport}
              disabled={downloadingReport}
              icon={downloadingReport ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
            >
              {downloadingReport ? "Downloading..." : "Download Report"}
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={onViewReport}
            icon={<FileText size={13} className="text-primary" />}
          >
            View Full Report
          </Button>
        </div>
      </div>

      {/* Core AI Verdict Explanation */}
      <div className={`p-4 rounded-lg ${theme.bannerBg} border ${theme.border} space-y-2`}>
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
            <VerdictIcon size={14} className={theme.badgeText} />
            {theme.statusText}
          </span>
          {prediction.recommended_action && (
            <span className="text-[11px] font-mono text-slate-500">
              Action: <span className="text-slate-800 font-semibold">{prediction.recommended_action}</span>
            </span>
          )}
        </div>
        <p className="text-xs text-slate-600 leading-relaxed">
          {prediction.explanation}
        </p>

        {/* Partial Verification / Missing Checks Detail */}
        {(() => {
          const partial = (prediction?.evidence?._partial_verification as any) || (prediction?.evidence_breakdown?._partial_verification as any);
          if (!partial && verdict !== "inconclusive" && !verdict.includes("inconclusive")) return null;
          return (
            <div className="pt-2 border-t border-amber-300/60 mt-2 space-y-1">
              <div className="flex items-center gap-2 font-semibold text-amber-950 flex-wrap">
                <span className="text-[11px] uppercase tracking-wider font-mono">Partial verification note:</span>
                {partial?.note && (
                  <span className="bg-amber-100 text-amber-900 px-2 py-0.5 rounded-full text-[11px] font-medium border border-amber-300">
                    {partial.note}
                  </span>
                )}
              </div>
              {partial?.missing_checks && partial.missing_checks.length > 0 && (
                <p className="text-amber-900 text-[11px] font-mono">
                  <span className="font-semibold font-sans">Missing verification checks: </span>
                  {partial.missing_checks.join(", ")}
                </p>
              )}
            </div>
          );
        })()}
      </div>

      {/* Exact Core Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5 space-y-1">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
            Prediction Confidence
          </span>
          <span className="text-xl font-mono font-bold text-slate-900">
            {predictionConfidence}%
          </span>
        </div>

        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5 space-y-1">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
            Trust Score
          </span>
          <span className="text-xl font-mono font-bold text-emerald-600">
            {trustScoreValue || "N/A"}
          </span>
        </div>

        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5 space-y-1">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
            Fraud Probability
          </span>
          <span className="text-xl font-mono font-bold text-amber-600">
            {fraudProbabilityValue || "N/A"}
          </span>
        </div>

        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5 space-y-1">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
            OCR Confidence
          </span>
          <span className="text-xl font-mono font-bold text-primary">
            {ocrAccuracyValue || "N/A"}
          </span>
        </div>
      </div>

      {/* 4-Vector Evidence Findings Summary */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider font-mono flex items-center gap-1.5">
          <Layers size={13} className="text-primary" />
          Verification Evidence Matrix
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {/* QR Code */}
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
            <span className="text-[10px] font-mono text-slate-500 uppercase flex items-center gap-1">
              <QrCode size={11} className="text-primary" />
              QR Verification
            </span>
            <div className="flex items-center justify-between pt-0.5">
              <span className={`text-xs font-mono font-semibold ${
                qrStatus === "VERIFIED" || qrStatus === "PASS"
                  ? "text-emerald-700"
                  : qrStatus === "NOT_FOUND"
                  ? "text-amber-700"
                  : "text-slate-500"
              }`}>
                {qrStatus === "VERIFIED" ? "Verified" : qrStatus === "NOT_FOUND" ? "Not Present" : qrStatus}
              </span>
            </div>
          </div>

          {/* Blockchain */}
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
            <span className="text-[10px] font-mono text-slate-500 uppercase flex items-center gap-1">
              <Link2 size={11} className="text-emerald-600" />
              Blockchain Proof
            </span>
            <div className="flex items-center justify-between pt-0.5">
              <span className={`text-xs font-mono font-semibold ${
                blockchainStatus === "VERIFIED" || blockchainStatus === "MATCH"
                  ? "text-emerald-700"
                  : "text-slate-500"
              }`}>
                {blockchainStatus === "VERIFIED" ? "Verified" : "Not Registered"}
              </span>
            </div>
          </div>

          {/* Tampering */}
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
            <span className="text-[10px] font-mono text-slate-500 uppercase flex items-center gap-1">
              <ShieldAlert size={11} className="text-amber-600" />
              Tampering Scan
            </span>
            <div className="flex items-center justify-between pt-0.5">
              <span className={`text-xs font-mono font-semibold ${
                rawTamperStatus === "CLEAN" || rawTamperStatus === "PASS" || rawTamperStatus === "analyzed"
                  ? "text-emerald-700"
                  : rawTamperStatus === "not_applicable_for_pdf_text_layer"
                  ? "text-amber-700"
                  : rawTamperStatus?.startsWith("failed:") || rawTamperStatus === "TAMPERED" || rawTamperStatus === "FAIL"
                  ? "text-rose-700"
                  : "text-slate-600"
              }`}>
                {formatTamperingText()}
              </span>
            </div>
          </div>

          {/* Duplicate */}
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
            <span className="text-[10px] font-mono text-slate-500 uppercase flex items-center gap-1">
              <Fingerprint size={11} className="text-primary" />
              Duplicate Check
            </span>
            <div className="flex items-center justify-between pt-0.5">
              <span className={`text-xs font-mono font-semibold ${
                duplicateStatus === "NOT_DETECTED"
                  ? "text-emerald-700"
                  : duplicateStatus === "DUPLICATE"
                  ? "text-rose-700"
                  : "text-slate-500"
              }`}>
                {duplicateStatus === "NOT_DETECTED" ? "Not Detected" : duplicateStatus}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Extracted Certificate Fields Summary */}
      {ocrData && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider font-mono flex items-center gap-1.5">
            <Sparkles size={13} className="text-primary" />
            Verified Certificate Fields
          </h3>

          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
            {ocrData.student_name && (
              <div>
                <span className="text-[10px] font-mono uppercase text-slate-500 block">Student Name</span>
                <span className="font-semibold text-slate-900">{ocrData.student_name}</span>
              </div>
            )}
            {ocrData.university_name && (
              <div>
                <span className="text-[10px] font-mono uppercase text-slate-500 block">University / Authority</span>
                <span className="font-semibold text-slate-900">{ocrData.university_name}</span>
              </div>
            )}
            {(ocrData.register_number || ocrData.roll_number) && (
              <div>
                <span className="text-[10px] font-mono uppercase text-slate-500 block">Registration / Roll No</span>
                <span className="font-mono text-slate-800 font-medium">{ocrData.register_number || ocrData.roll_number}</span>
              </div>
            )}
            {ocrData.date_of_issue && (
              <div>
                <span className="text-[10px] font-mono uppercase text-slate-500 block">Date of Issue</span>
                <span className="font-mono text-slate-800">{ocrData.date_of_issue}</span>
              </div>
            )}
            {(ocrData.cgpa || ocrData.percentage) && (
              <div>
                <span className="text-[10px] font-mono uppercase text-slate-500 block">Academic Score</span>
                <span className="font-mono text-slate-800">
                  {[ocrData.cgpa ? `CGPA: ${ocrData.cgpa}` : null, ocrData.percentage ? `${ocrData.percentage}%` : null].filter(Boolean).join(" • ")}
                </span>
              </div>
            )}
            {cert?.original_filename && (
              <div>
                <span className="text-[10px] font-mono uppercase text-slate-500 block">Ingested File</span>
                <span className="text-slate-600 truncate block">{cert.original_filename}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Navigation Footer Controls */}
      <div className="pt-3 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2">
          <Link
            href="/dashboard/certificates"
            className="text-xs text-slate-500 hover:text-slate-900 transition flex items-center gap-1 font-mono"
          >
            <span>← Certificate Registry</span>
          </Link>
          <span className="text-slate-300">|</span>
          <Link
            href="/dashboard"
            className="text-xs text-slate-500 hover:text-slate-900 transition font-mono"
          >
            Dashboard Overview
          </Link>
        </div>

        <div className="flex items-center gap-2">
          {report ? (
            <span className="text-[11px] font-mono text-emerald-700 flex items-center gap-1">
              <FileCheck size={12} />
              Dossier Ready ({report.verification_id})
            </span>
          ) : (
            <span className="text-[11px] font-mono text-slate-400">
              Report generation ready
            </span>
          )}
        </div>
      </div>
    </section>
  );
};
