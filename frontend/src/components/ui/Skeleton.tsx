import React from "react";
import { cn } from "@/lib/utils";

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "text" | "rectangular" | "circular";
}

export const Skeleton: React.FC<SkeletonProps> = ({
  className,
  variant = "rectangular",
  ...props
}) => {
  const variantStyles = {
    text: "h-4 rounded",
    rectangular: "rounded-lg",
    circular: "rounded-full",
  };

  return (
    <div
      className={cn(
        "animate-pulse bg-slate-200/80",
        variantStyles[variant],
        className
      )}
      aria-hidden="true"
      {...props}
    />
  );
};

export default Skeleton;
