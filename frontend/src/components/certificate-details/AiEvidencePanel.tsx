"use client";

import React from "react";
import {
  ListChecks,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  Activity,
  Gauge,
} from "lucide-react";
import {
  FinalPredictionResponse,
  EvidenceBreakdown,
  FraudAnalysisResponse,
  TrustScoreResponse,
} from "@/lib/api";

const FORENSIC_FACTORS: Array<{ key: keyof EvidenceBreakdown; label: string }> = [
  { key: "ocr", label: "OCR Extraction Quality" },
  { key: "classification", label: "Document Classification" },
  { key: "field_extraction", label: "Field Schema Integrity" },
  { key: "comparison", label: "Multi-Document Consistency" },
  { key: "qr", label: "Digital QR Cryptography" },
  { key: "blockchain", label: "Distributed Ledger Proof" },
  { key: "tampering", label: "Pixel & ELA Tampering" },
  { key: "duplicate", label: "Registry Duplicate Match" },
  { key: "metadata", label: "File Metadata Integrity" },
];

interface AiEvidencePanelProps {
  prediction: FinalPredictionResponse | null;
  fraud: FraudAnalysisResponse | null;
  trustScore: TrustScoreResponse | null;
}

export const AiEvidencePanel: React.FC<AiEvidencePanelProps> = ({
  prediction,
  fraud,
  trustScore,
}) => {
  const evidence = prediction?.evidence;
  const reasons = prediction?.reasons ?? [];

  const getStatusConfig = (status?: string) => {
    const s = (status || "").toUpperCase();
    if (["PASS", "VERIFIED", "MATCH", "NOT_FOUND", "LOW_RISK", "CLEAN"].includes(s)) {
      return {
        color: "text-emerald-700",
        bg: "bg-emerald-50 border-emerald-200",
        icon: CheckCircle2,
      };
    }
    if (["WARN", "NOT_REGISTERED", "MEDIUM_RISK", "FLAGGED"].includes(s)) {
      return {
        color: "text-amber-700",
        bg: "bg-amber-50 border-amber-200",
        icon: AlertTriangle,
      };
    }
    if (["FAIL", "INVALID", "MISMATCH", "HIGH_RISK", "DUPLICATE"].includes(s)) {
      return {
        color: "text-red-700",
        bg: "bg-red-50 border-red-200",
        icon: XCircle,
      };
    }
    return {
      color: "text-slate-600",
      bg: "bg-slate-50 border-slate-200",
      icon: HelpCircle,
    };
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 shadow-sm space-y-5">
      {/* Panel Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 tracking-tight flex items-center gap-2">
            <ListChecks size={16} className="text-indigo-600" />
            AI Evidence Matrix & Synthesis
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Holistic cross-evaluation of forensic telemetry, Bayesian risk weights, and decision rules.
          </p>
        </div>
        {fraud?.fraud_probability != null && (
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-slate-500">Statistical Risk:</span>
            <span
              className={`font-semibold ${
                fraud.fraud_probability < 0.3
                  ? "text-emerald-700"
                  : fraud.fraud_probability < 0.6
                  ? "text-amber-700"
                  : "text-red-700"
              }`}
            >
              {Math.round(fraud.fraud_probability * 100)}%
            </span>
          </div>
        )}
      </div>

      {/* Grid of Forensic Evidence Factors */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
        {FORENSIC_FACTORS.map(({ key, label }) => {
          const factor = evidence ? evidence[key] : undefined;
          const status = factor?.display_status || factor?.status || "UNAVAILABLE";
          const score = factor?.score != null ? `${Math.round(factor.score as number)}%` : null;
          const cfg = getStatusConfig(status);
          const Icon = cfg.icon;

          return (
            <div
              key={key}
              className={`flex items-center justify-between rounded-xl px-3.5 py-2.5 border transition ${cfg.bg}`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <Icon size={14} className={`${cfg.color} shrink-0`} />
                <span className="text-xs font-medium text-slate-800 truncate">{label}</span>
              </div>
              <div className="flex items-center gap-1.5 shrink-0 ml-2">
                {score && <span className="text-[11px] font-mono text-slate-500">{score}</span>}
                <span className={`text-[10px] font-semibold uppercase ${cfg.color}`}>
                  {status.replace(/_/g, " ")}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Trust Score Factor Contributions & Fraud Weights */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-slate-100">
        {/* Factor Trust Contributions & Monotonic Component Breakdown */}
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3 col-span-1 md:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-2.5">
            <div className="flex items-center gap-2">
              <Activity size={16} className="text-indigo-600" />
              <span className="text-sm font-bold text-slate-900">Trust Score Breakdown & Evidence Coverage</span>
            </div>
            {trustScore && (
              <div className="flex items-center gap-2">
                <span
                  className={`text-xs px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider ${
                    (trustScore.band || "").toUpperCase() === "HIGH" || trustScore.score >= 80
                      ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                      : (trustScore.band || "").toUpperCase() === "MEDIUM" || trustScore.score >= 50
                      ? "bg-amber-100 text-amber-800 border border-amber-300"
                      : "bg-red-100 text-red-800 border border-red-300"
                  }`}
                >
                  {trustScore.band_label || `${trustScore.band || "SCORE"} BAND`}
                </span>
                <span className="text-xs font-mono font-extrabold text-slate-800 bg-white border border-slate-200 px-2.5 py-0.5 rounded-lg shadow-sm">
                  {Math.round(trustScore.score)} / 100
                </span>
              </div>
            )}
          </div>

          {trustScore ? (
            <div className="space-y-3">
              {/* Coverage Progress Bar */}
              <div className="bg-white border border-slate-200 rounded-lg p-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div>
                  <span className="font-semibold text-slate-700">Verification Evidence Coverage: </span>
                  <span className="font-bold text-indigo-700">
                    {trustScore.coverage_percentage ??
                      (trustScore.coverage ? Math.round(trustScore.coverage * 100) : 100)}
                    %
                  </span>
                  <span className="text-slate-500 ml-1">
                    ({trustScore.checks_evaluated ?? (trustScore.components?.filter((c) => c.status !== "not evaluated").length || 8)} of{" "}
                    {trustScore.checks_total ?? 8} verification checks evaluated)
                  </span>
                </div>
                <div className="w-full sm:w-36 bg-slate-100 h-2 rounded-full overflow-hidden shrink-0 border border-slate-200">
                  <div
                    className="bg-indigo-600 h-full rounded-full transition-all"
                    style={{
                      width: `${
                        trustScore.coverage_percentage ??
                        (trustScore.coverage ? Math.round(trustScore.coverage * 100) : 100)
                      }%`,
                    }}
                  />
                </div>
              </div>

              {/* Itemized Component Breakdown List */}
              {trustScore.components && trustScore.components.length > 0 ? (
                <div className="space-y-2">
                  {trustScore.components.map((comp) => {
                    const isPass = comp.status === "PASS";
                    const isWarn = comp.status === "WARN";
                    const isFail = comp.status === "FAIL";
                    const isNotEval = comp.status === "not evaluated";

                    const badgeClass = isPass
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : isWarn
                      ? "bg-amber-50 text-amber-700 border-amber-200"
                      : isFail
                      ? "bg-red-50 text-red-700 border-red-200"
                      : "bg-slate-100 text-slate-500 border-slate-200";

                    return (
                      <div
                        key={comp.component}
                        className={`p-2.5 rounded-lg border text-xs flex flex-col gap-1 transition-all ${
                          isNotEval ? "bg-slate-50/60 border-slate-200 opacity-75" : "bg-white border-slate-200 shadow-2xs"
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-1">
                          <span className="font-semibold text-slate-800">{comp.label}</span>
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold border uppercase ${badgeClass}`}>
                              {comp.status}
                            </span>
                            {!isNotEval && (
                              <span className="font-mono text-slate-700">
                                Value: <b>{comp.value !== null ? Math.round(comp.value) : "—"}</b>
                              </span>
                            )}
                            <span className="text-[11px] text-slate-500">
                              Weight: <b>{Math.round(comp.weight * 100)}%</b>
                            </span>
                            <span className="text-[11px] text-indigo-700 font-semibold">
                              +{comp.contribution.toFixed(1)} pts
                            </span>
                          </div>
                        </div>
                        <p className="text-[11px] text-slate-500 italic">{comp.reason}</p>
                      </div>
                    );
                  })}
                </div>
              ) : trustScore?.breakdown?.factor_trust_values &&
                Object.keys(trustScore.breakdown.factor_trust_values).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(trustScore.breakdown.factor_trust_values).map(([factor, val]) => (
                    <div key={factor} className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-600 capitalize">{factor.replace(/_/g, " ")}</span>
                        <span className="font-semibold text-slate-900">{Math.round(val)}</span>
                      </div>
                      <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            val >= 80 ? "bg-emerald-500" : val >= 50 ? "bg-amber-500" : "bg-red-500"
                          }`}
                          style={{ width: `${val}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-slate-400 italic">
              Compute Trust Score above to generate itemized factor weights and coverage analysis.
            </p>
          )}
        </div>


        {/* Bayesian Fraud Weights */}
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
              <Gauge size={14} className="text-amber-600" /> Fraud Weights Distribution
            </span>
            <span className="text-[10px] text-slate-400">Active Weights</span>
          </div>
          {fraud ? (
            <div className="space-y-2 text-xs">
              {[
                ["OCR Accuracy", fraud.ocr_accuracy_weight],
                ["QR Verification", fraud.qr_weight],
                ["Blockchain Verification", fraud.blockchain_weight],
                ["Tampering Detection", fraud.tampering_weight],
                ["Duplicate Detection", fraud.duplicate_weight],
                ["Metadata Integrity", fraud.metadata_integrity_weight],
                ["Image Quality", fraud.image_quality_weight],
              ].map(([label, weight]) => (
                <div key={label as string} className="flex items-center justify-between">
                  <span className="text-slate-600">{label}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-20 bg-slate-200 h-1.5 rounded-full overflow-hidden">
                      <div
                        className="bg-indigo-600 h-full rounded-full"
                        style={{ width: `${(weight as number) * 100}%` }}
                      />
                    </div>
                    <span className="font-semibold text-slate-800 w-8 text-right">
                      {Math.round((weight as number) * 100)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-400 italic">
              Execute Fraud Analysis to view factor contribution weights.
            </p>
          )}
        </div>
      </div>

      {/* Decision Audit Log / Reasons List */}
      {reasons.length > 0 && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2">
          <span className="text-xs font-semibold text-slate-800 block">
            System Decision Log
          </span>
          <ul className="space-y-1.5 text-xs">
            {reasons.map((r, i) => {
              const isPass = r.startsWith("✓");
              const isFail = r.startsWith("✗");
              const color = isPass
                ? "text-emerald-700"
                : isFail
                ? "text-red-700"
                : "text-amber-700";
              return (
                <li key={i} className={`flex items-start gap-2 ${color} leading-relaxed`}>
                  <span className="font-bold shrink-0">{isPass ? "✓" : isFail ? "✗" : "•"}</span>
                  <span>{r.replace(/^[✓✗⚠]\s*/, "")}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
};

export default AiEvidencePanel;
