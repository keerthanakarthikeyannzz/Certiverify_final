import React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";

export interface LogoProps {
  className?: string;
  size?: "sm" | "md" | "lg" | "xl";
  showText?: boolean;
  showWordmark?: boolean;
  isDark?: boolean;
  href?: string;
  onClick?: () => void;
  ariaLabel?: string;
}

export const MonogramIcon: React.FC<{ sizePx?: number; className?: string }> = ({
  sizePx = 32,
  className,
}) => (
  <svg
    width={sizePx}
    height={sizePx}
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={cn("shrink-0", className)}
    aria-label="CertiVerify Monogram"
  >
    <rect width="32" height="32" rx="8" fill="#4F46E5" />
    <path
      d="M21 11.5C19.7 10.3 17.8 9.5 15.5 9.5C11.9 9.5 9 12.4 9 16C9 19.6 11.9 22.5 15.5 22.5C17.8 22.5 19.7 21.7 21 20.5"
      stroke="#FFFFFF"
      strokeWidth="2.5"
      strokeLinecap="round"
    />
    <path
      d="M14 16L16.5 18.5L22 13"
      stroke="#FFFFFF"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export const Logo: React.FC<LogoProps> = ({
  className,
  size = "md",
  showText = true,
  showWordmark = true,
  href,
  onClick,
  ariaLabel = "CertiVerify AI",
}) => {
  const sizeMap = {
    sm: { px: 24, text: "text-sm", sub: "text-[10px]" },
    md: { px: 32, text: "text-base", sub: "text-xs" },
    lg: { px: 40, text: "text-xl", sub: "text-xs" },
    xl: { px: 48, text: "text-2xl", sub: "text-sm" },
  };

  const current = sizeMap[size];
  const shouldShowText = showText && showWordmark;

  const content = (
    <div
      onClick={onClick}
      className={cn("inline-flex items-center gap-2.5 select-none", className)}
      aria-label={ariaLabel}
    >
      <MonogramIcon sizePx={current.px} />
      {shouldShowText && (
        <div className="flex flex-col leading-none">
          <span className={cn("font-bold tracking-tight text-slate-900 font-sans", current.text)}>
            CertiVerify <span className="text-indigo-600">AI</span>
          </span>
          <span className={cn("text-slate-500 font-medium tracking-normal mt-0.5", current.sub)}>
            Trust & Provenance
          </span>
        </div>
      )}
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="inline-block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600 rounded-lg">
        {content}
      </Link>
    );
  }

  return content;
};

export default Logo;
