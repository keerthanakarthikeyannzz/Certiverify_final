import React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "genuine" | "suspicious" | "fake" | "inconclusive" | "neutral" | "brand" | "info";
  size?: "sm" | "md" | "lg";
  dot?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({
  className,
  variant = "neutral",
  size = "md",
  dot = false,
  children,
  ...props
}) => {
  const variantStyles = {
    genuine: "bg-emerald-50 text-emerald-700 border-emerald-200",
    suspicious: "bg-amber-50 text-amber-700 border-amber-200",
    fake: "bg-red-50 text-red-700 border-red-200",
    inconclusive: "bg-amber-50 text-amber-800 border-amber-300",
    neutral: "bg-slate-100 text-slate-700 border-slate-200",
    brand: "bg-indigo-50 text-indigo-700 border-indigo-200",
    info: "bg-sky-50 text-sky-700 border-sky-200",
  };

  const dotColors = {
    genuine: "bg-emerald-500",
    suspicious: "bg-amber-500",
    fake: "bg-red-500",
    inconclusive: "bg-amber-500",
    neutral: "bg-slate-400",
    brand: "bg-indigo-500",
    info: "bg-sky-500",
  };

  const sizeStyles = {
    sm: "text-[11px] px-2 py-0.5 rounded-md gap-1 font-medium",
    md: "text-xs px-2.5 py-0.5 rounded-md gap-1.5 font-medium",
    lg: "text-sm px-3 py-1 rounded-lg gap-2 font-semibold",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center select-none border font-sans tracking-tight leading-none",
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
      {...props}
    >
      {dot && (
        <span
          className={cn("w-1.5 h-1.5 rounded-full shrink-0", dotColors[variant])}
          aria-hidden="true"
        />
      )}
      {children}
    </span>
  );
};

export default Badge;
