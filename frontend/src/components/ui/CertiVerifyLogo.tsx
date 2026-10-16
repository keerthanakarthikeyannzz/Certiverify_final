"use client";

import React from "react";
import { Logo, LogoProps } from "./Logo";

interface CertiVerifyLogoProps {
  variant?: "full" | "compact" | "icon";
  size?: "sm" | "md" | "lg" | "xl";
  showTagline?: boolean;
  isDark?: boolean;
  className?: string;
  onClick?: () => void;
  href?: string;
}

export const CertiVerifyLogo: React.FC<CertiVerifyLogoProps> = ({
  variant = "full",
  size = "md",
  showTagline = false,
  isDark = false,
  className = "",
  onClick,
  href,
}) => {
  const showWordmark = variant !== "icon";

  return (
    <div className={`inline-flex flex-col items-center ${className}`}>
      <Logo
        size={size}
        showWordmark={showWordmark}
        isDark={isDark}
        href={href}
        onClick={onClick}
      />
      {showTagline && variant === "full" && (
        <span className="font-mono text-[9px] font-bold tracking-widest text-indigo-400 uppercase mt-1">
          VERIFY TODAY • TRUST TOMORROW
        </span>
      )}
    </div>
  );
};

export default CertiVerifyLogo;
