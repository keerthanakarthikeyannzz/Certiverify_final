import React from "react";
import { cn } from "@/lib/utils";

export interface ProgressBarProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number; // 0 to 100
  max?: number;
  indeterminate?: boolean;
  variant?: "brand" | "emerald" | "amber" | "rose" | "gradient";
  size?: "xs" | "sm" | "md" | "lg";
  showLabel?: boolean;
  label?: string;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  className,
  value = 0,
  max = 100,
  indeterminate = false,
  variant = "brand",
  size = "sm",
  showLabel = false,
  label,
  ...props
}) => {
  const percentage = Math.min(Math.max(0, (value / max) * 100), 100);

  const sizeStyles = {
    xs: "h-1",
    sm: "h-1.5",
    md: "h-2",
    lg: "h-3",
  };

  const variantStyles = {
    brand: "bg-indigo-600",
    emerald: "bg-emerald-500",
    amber: "bg-amber-500",
    rose: "bg-rose-500",
    gradient: "bg-gradient-to-r from-indigo-600 via-blue-500 to-emerald-500",
  };

  return (
    <div className="w-full space-y-1.5" {...props}>
      {(showLabel || label) && (
        <div className="flex justify-between items-center text-xs">
          <span className="text-slate-600 font-medium">{label}</span>
          {showLabel && (
            <span className="font-mono text-slate-900 font-semibold">
              {Math.round(percentage)}%
            </span>
          )}
        </div>
      )}
      <div
        className={cn(
          "w-full bg-slate-100 rounded-full overflow-hidden border border-slate-200/60",
          sizeStyles[size],
          className
        )}
      >
        {indeterminate ? (
          <div
            className={cn(
              "h-full w-2/5 rounded-full",
              variantStyles[variant]
            )}
            style={{
              animation: "indeterminate 1.5s cubic-bezier(0.4, 0, 0.2, 1) infinite",
            }}
          />
        ) : (
          <div
            className={cn("h-full rounded-full transition-all duration-300 ease-out", variantStyles[variant])}
            style={{ width: `${percentage}%` }}
          />
        )}
      </div>
    </div>
  );
};

