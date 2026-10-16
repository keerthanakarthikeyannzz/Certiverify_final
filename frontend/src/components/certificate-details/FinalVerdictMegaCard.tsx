"use client";

import React from "react";
import {
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  Sparkles,
  Activity,
  ArrowRight,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import {
  FinalPredictionResponse,
  TrustScoreResponse,
  FraudAnalysisResponse,
} from "@/lib/api";
import { ScoreGauge } from "@/components/ui/ScoreGauge";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";

interface FinalVerdictMegaCardProps {
  prediction: FinalPredictionResponse | null;
  trustScore: TrustScoreResponse | null;
  fraud: FraudAnalysisResponse | null;
  onPredict: () => void;
  onComputeTrust: () => void;
  predicting: boolean;
  computingTrust: boolean;
}

export const FinalVerdictMegaCard: React.FC<FinalVerdictMegaCardProps> = ({
  prediction,
  trustScore,
  fraud,
  onPredict,
  onComputeTrust,
  predicting,
  computingTrust,
}) => {
  const label = (prediction?.label || "pending").toLowerCase();
  const isInc = label === "inconclusive" || label.includes("inconclusive");

  const themeConfig = {
    genuine: {
      cardBg: "bg-emerald-50/40 border-emerald-200",
      iconBg: "bg-emerald-100 text-emerald-700",
      titleColor: "text-emerald-900",
      badgeVariant: "genuine" as const,
      icon: ShieldCheck,
      title: "Genuine Credential Verified",
    },
    suspicious: {
      cardBg: "bg-amber-50/40 border-amber-200",
      iconBg: "bg-amber-100 text-amber-700",
      titleColor: "text-amber-900",
      badgeVariant: "suspicious" as const,
      icon: ShieldAlert,
      title: "Suspicious Indicators Detected",
    },
    inconclusive: {
      cardBg: "bg-amber-50/50 border-amber-300",
      iconBg: "bg-amber-100 text-amber-800",
      titleColor: "text-amber-950",
      badgeVariant: "inconclusive" as const,
      icon: ShieldAlert,
      title: "Needs Review — Verification Inconclusive",
    },
    fake: {
      cardBg: "bg-red-50/40 border-red-200",
      iconBg: "bg-red-100 text-red-700",
      titleColor: "text-red-900",
      badgeVariant: "fake" as const,
      icon: ShieldX,
      title: "High-Confidence Forgery / Fake",
    },
    pending: {
      cardBg: "bg-slate-50 border-slate-200",
      iconBg: "bg-slate-100 text-slate-700",
      titleColor: "text-slate-900",
      badgeVariant: "neutral" as const,
      icon: Activity,
      title: "Forensic Analysis Pending",
    },
  };

  const themeKey = isInc ? "inconclusive" : label;
  const theme = themeConfig[themeKey as keyof typeof themeConfig] || themeConfig.pending;
  const IconComponent = theme.icon;

  const fraudProbability = fraud?.fraud_probability ?? prediction?.fraud_probability ?? null;
  const fraudPercent = fraudProbability != null ? Math.round(fraudProbability * 100) : null;
  const scoreValue = trustScore?.score ?? 0;

  return (
    <div className={`border rounded-2xl p-6 sm:p-8 shadow-sm transition-all duration-200 ${theme.cardBg}`}>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
        {/* Left Column: Verdict, Explanation & Recommendation */}
        <div className="lg:col-span-7 space-y-5">
          <div className="flex items-start gap-4">
            <div className={`w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 shadow-xs ${theme.iconBg}`}>
              <IconComponent size={28} />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  Integrity Verdict
                </span>
                {prediction && (
                  <Badge variant={theme.badgeVariant} size="sm">
                    {isInc ? "Needs Review" : prediction.label} • {Math.round(prediction.confidence_score * 100)}% Confidence
                  </Badge>
                )}
              </div>
              <h2 className={`text-2xl font-bold tracking-tight mt-1 ${theme.titleColor}`}>
                {prediction ? theme.title : "Forensic Verification Pending"}
              </h2>
            </div>
          </div>

          <p className="text-sm text-slate-600 leading-relaxed">
            {prediction?.explanation ||
              "Run the AI forensic engine to synthesize OCR extractions, cryptographic records, digital QR signatures, noise analysis, and duplicate detection into a unified verdict."}
          </p>

          {(() => {
            const partial = (prediction?.evidence?._partial_verification as any) || (prediction?.evidence_breakdown?._partial_verification as any);
            if (!partial) return null;
            return (
              <div className="p-3 bg-amber-50/90 border border-amber-300 rounded-xl space-y-1.5 text-xs text-amber-950">
                <div className="flex items-center gap-2 font-semibold flex-wrap">
                  <ShieldAlert size={15} className="text-amber-600 shrink-0" />
                  <span>Partial Verification Incomplete</span>
                  {partial?.note && (
                    <span className="font-mono text-[11px] font-medium bg-amber-100 text-amber-900 px-2 py-0.5 rounded-full border border-amber-300">
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

          {prediction?.recommended_action && (
            <div className="p-4 bg-white/80 border border-slate-200/80 rounded-xl space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Recommended Operational Action
              </span>
              <p className="text-xs font-medium text-slate-800 leading-relaxed">
                {prediction.recommended_action}
              </p>
            </div>
          )}

          {/* Action Triggers */}
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Button
              onClick={onPredict}
              loading={predicting}
              icon={<Sparkles size={15} />}
            >
              Run AI Verdict Synthesis
            </Button>
            <Button
              variant="secondary"
              onClick={onComputeTrust}
              loading={computingTrust}
            >
              Recalculate Trust Score
            </Button>
          </div>
        </div>

        {/* Right Column: Trust Score Gauge & Signals */}
        <div className="lg:col-span-5 flex flex-col sm:flex-row items-center justify-center gap-6 p-6 bg-white border border-slate-200 rounded-2xl shadow-xs">
          {/* Circular Score Gauge */}
          <div className="flex flex-col items-center">
            <ScoreGauge score={scoreValue} size="md" />
            <span className="text-xs text-slate-500 font-medium mt-1">
              Weighted AI Trust Metric
            </span>
          </div>

          {/* Secondary Risk Stat */}
          {fraudPercent !== null && (
            <div className="flex flex-col items-center sm:items-start space-y-2 border-t sm:border-t-0 sm:border-l border-slate-100 pt-4 sm:pt-0 sm:pl-6">
              <span className="text-[11px] uppercase font-semibold text-slate-400 tracking-wider">
                Fraud Risk Index
              </span>
              <div className="flex items-baseline gap-1.5">
                <span className={`text-3xl font-extrabold ${fraudPercent > 50 ? "text-red-600" : "text-slate-800"}`}>
                  {fraudPercent}%
                </span>
                {fraudPercent > 50 ? (
                  <TrendingUp className="w-4 h-4 text-red-500" />
                ) : (
                  <TrendingDown className="w-4 h-4 text-emerald-500" />
                )}
              </div>
              <div className="w-28 h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    fraudPercent > 60 ? "bg-red-500" : fraudPercent > 30 ? "bg-amber-500" : "bg-emerald-500"
                  }`}
                  style={{ width: `${fraudPercent}%` }}
                />
              </div>
              <span className="text-[11px] text-slate-500 font-medium">
                {fraudPercent > 60 ? "High Risk Detected" : "Within Expected Bounds"}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default FinalVerdictMegaCard;
