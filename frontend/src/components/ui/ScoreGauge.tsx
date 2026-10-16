import React from "react";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";

export interface ScoreGaugeProps {
  score: number; // 0 - 100
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  className?: string;
}

export const ScoreGauge: React.FC<ScoreGaugeProps> = ({
  score,
  size = "md",
  showLabel = true,
  className,
}) => {
  const clampedScore = Math.max(0, Math.min(100, Math.round(score)));

  // Semantic category and color mapping
  let color = "#059669"; // Genuine
  let bgColor = "#ECFDF5";
  let label = "Genuine";

  if (clampedScore < 40) {
    color = "#DC2626"; // Fake
    bgColor = "#FEF2F2";
    label = "High Risk (Fake)";
  } else if (clampedScore < 75) {
    color = "#D97706"; // Suspicious
    bgColor = "#FFFBEB";
    label = "Suspicious";
  }

  const dimensionMap = {
    sm: { width: 80, stroke: 7, radius: 32, text: "text-lg", labelText: "text-[10px]" },
    md: { width: 120, stroke: 10, radius: 48, text: "text-2xl", labelText: "text-xs" },
    lg: { width: 160, stroke: 12, radius: 64, text: "text-4xl", labelText: "text-sm" },
  };

  const current = dimensionMap[size];
  const circumference = 2 * Math.PI * current.radius;
  const strokeDashoffset = circumference - (clampedScore / 100) * circumference;

  return (
    <div className={cn("inline-flex flex-col items-center justify-center font-sans", className)}>
      <div
        className="relative flex items-center justify-center"
        style={{ width: current.width, height: current.width }}
        role="meter"
        aria-valuenow={clampedScore}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Trust Score: ${clampedScore} out of 100 (${label})`}
      >
        <svg
          width={current.width}
          height={current.width}
          className="transform -rotate-90"
        >
          {/* Background circle track */}
          <circle
            cx={current.width / 2}
            cy={current.width / 2}
            r={current.radius}
            stroke="#E2E8F0"
            strokeWidth={current.stroke}
            fill="transparent"
          />
          {/* Animated active stroke */}
          <motion.circle
            cx={current.width / 2}
            cy={current.width / 2}
            r={current.radius}
            stroke={color}
            strokeWidth={current.stroke}
            strokeLinecap="round"
            fill="transparent"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          />
        </svg>

        {/* Center score readout */}
        <div className="absolute flex flex-col items-center justify-center text-center">
          <span className={cn("font-bold text-slate-900 leading-none", current.text)}>
            {clampedScore}
          </span>
          <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider mt-0.5">
            /100
          </span>
        </div>
      </div>

      {showLabel && (
        <span
          className={cn(
            "mt-2 font-semibold px-2.5 py-0.5 rounded-full border text-center select-none",
            current.labelText
          )}
          style={{ backgroundColor: bgColor, color, borderColor: `${color}40` }}
        >
          {label}
        </span>
      )}
    </div>
  );
};

export default ScoreGauge;
