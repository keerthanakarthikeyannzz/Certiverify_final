"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import { Logo } from "./Logo";

interface SplashScreenProps {
  onComplete?: () => void;
  minimumDurationMs?: number;
}

export const SplashScreen: React.FC<SplashScreenProps> = ({
  onComplete,
  minimumDurationMs = 1800,
}) => {
  const [visible, setVisible] = useState(true);
  const [fadingOut, setFadingOut] = useState(false);

  useEffect(() => {
    // Check if splash screen was already shown in this session
    const hasShown = typeof window !== "undefined" && sessionStorage.getItem("certiverify_splash_shown");
    
    if (hasShown) {
      setVisible(false);
      if (onComplete) onComplete();
      return;
    }

    const timer = setTimeout(() => {
      setFadingOut(true);
      const exitTimer = setTimeout(() => {
        setVisible(false);
        if (typeof window !== "undefined") {
          sessionStorage.setItem("certiverify_splash_shown", "1");
        }
        if (onComplete) onComplete();
      }, 500); // 500ms fade-out transition duration

      return () => clearTimeout(exitTimer);
    }, minimumDurationMs);

    return () => clearTimeout(timer);
  }, [minimumDurationMs, onComplete]);

  if (!visible) return null;

  return (
    <div
      className={`fixed inset-0 z-[99999] bg-[#fafafa] flex flex-col items-center justify-center p-6 transition-opacity duration-500 ease-out select-none ${
        fadingOut ? "opacity-0 pointer-events-none" : "opacity-100"
      }`}
      aria-label="CertiVerify AI Initialization Splash Screen"
    >
      {/* Dynamic Background Glow Effect */}
      <div className="absolute w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none animate-pulse" />

      <div className="relative z-10 flex flex-col items-center text-center max-w-md animate-splash-scale space-y-4">
        {/* Logo Icon Entry */}
        <Logo size="lg" showWordmark={true} isDark={false} />
        <p className="text-xs font-mono text-indigo-600 font-semibold tracking-widest uppercase mt-1">
          VERIFY TODAY • TRUST TOMORROW
        </p>

        {/* Loading Indicator */}
        <div className="flex flex-col items-center gap-2.5 w-64 pt-2">
          <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden">
            <div className="bg-indigo-600 h-full rounded-full animate-pulse w-3/4 transition-all duration-1000" />
          </div>
          <span className="font-mono text-xs text-slate-400 tracking-wider uppercase font-semibold">
            Initializing AI Verification Engine...
          </span>
        </div>
      </div>
    </div>
  );
};
