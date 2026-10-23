"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
import axios from "axios";
import { BACKEND_URL, isBackendLoopingToFrontend } from "@/lib/api";
import { RefreshCw } from "lucide-react";

export type ConnectionState = "online" | "offline" | "checking";

interface ConnectionStatusProps {
  className?: string;
  showText?: boolean;
}

export const ConnectionStatus: React.FC<ConnectionStatusProps> = ({
  className = "",
  showText = true,
}) => {
  const [status, setStatus] = useState<ConnectionState>("checking");
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);
  const [loopDetected, setLoopDetected] = useState(false);
  const [retriesExhausted, setRetriesExhausted] = useState(false);

  // Configuration with documented defaults and sane minimum bounds
  const healthPath = process.env.NEXT_PUBLIC_HEALTH_PATH || "/health";
  const SANE_MIN_POLL_INTERVAL_MS = 2000;
  const pollIntervalMs = Math.max(
    parseInt(process.env.NEXT_PUBLIC_HEALTH_POLL_INTERVAL_MS || "10000", 10) || 10000,
    SANE_MIN_POLL_INTERVAL_MS
  );
  const timeoutMs = Math.max(
    parseInt(process.env.NEXT_PUBLIC_HEALTH_TIMEOUT_MS || "3500", 10) || 3500,
    500
  );
  const maxRetries = Math.max(
    parseInt(process.env.NEXT_PUBLIC_HEALTH_MAX_RETRIES || "5", 10) || 5,
    1
  );
  const retryBackoffMs = Math.max(
    parseInt(process.env.NEXT_PUBLIC_HEALTH_RETRY_BACKOFF_MS || "1000", 10) || 1000,
    200
  );
  const retryBackoffFactor = Math.max(
    parseFloat(process.env.NEXT_PUBLIC_HEALTH_RETRY_BACKOFF_FACTOR || "1.5") || 1.5,
    1.0
  );

  const retryCountRef = useRef(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const clearScheduledTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const checkHealth = useCallback(async () => {
    clearScheduledTimer();

    // 1. Loop guard check: fail fast if backend points to frontend itself
    if (isBackendLoopingToFrontend(BACKEND_URL)) {
      setLoopDetected(true);
      setStatus("offline");
      setRetriesExhausted(true);
      setIsRetrying(false);
      setLastChecked(new Date());
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("backend-status-change", {
            detail: { online: false, loopDetected: true, url: BACKEND_URL },
          })
        );
      }
      return;
    }

    setLoopDetected(false);

    try {
      // Call backend through configured target/rewrite path only with env timeout
      const res = await axios.get(healthPath, { timeout: timeoutMs });
      if (res.status === 200 && res.data?.status === "ok") {
        setStatus("online");
        retryCountRef.current = 0;
        setRetriesExhausted(false);
        if (typeof window !== "undefined") {
          window.dispatchEvent(
            new CustomEvent("backend-status-change", { detail: { online: true } })
          );
        }
        // Schedule next periodic poll
        timerRef.current = setTimeout(checkHealth, pollIntervalMs);
      } else {
        throw new Error(`Unexpected health status: ${res.status}`);
      }
    } catch {
      setStatus("offline");
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("backend-status-change", { detail: { online: false } })
        );
      }

      retryCountRef.current += 1;
      if (retryCountRef.current < maxRetries) {
        setRetriesExhausted(false);
        // Exponential backoff
        const backoffDelay = Math.min(
          retryBackoffMs * Math.pow(retryBackoffFactor, retryCountRef.current - 1),
          pollIntervalMs * 3
        );
        timerRef.current = setTimeout(checkHealth, backoffDelay);
      } else {
        // Exceeded max retries: STOP retrying to prevent hammering the server
        setRetriesExhausted(true);
      }
    } finally {
      setLastChecked(new Date());
      setIsRetrying(false);
    }
  }, [
    healthPath,
    pollIntervalMs,
    timeoutMs,
    maxRetries,
    retryBackoffMs,
    retryBackoffFactor,
  ]);

  useEffect(() => {
    checkHealth();
    return () => clearScheduledTimer();
  }, [checkHealth]);

  const handleManualCheck = (e: React.MouseEvent) => {
    e.stopPropagation();
    retryCountRef.current = 0;
    setRetriesExhausted(false);
    setIsRetrying(true);
    setStatus("checking");
    checkHealth();
  };

  const isOnline = status === "online";
  const isChecking = status === "checking";

  // Build helpful tooltip and indicator text
  let tooltipText = "";
  if (loopDetected) {
    tooltipText = `Configuration error: BACKEND_URL points to the frontend itself (${BACKEND_URL}). Please set BACKEND_PORT to 8000.`;
  } else if (isOnline) {
    tooltipText = `Backend: ${BACKEND_URL}${lastChecked ? ` (Checked ${lastChecked.toLocaleTimeString()})` : ""}`;
  } else {
    tooltipText = `Backend: ${BACKEND_URL}${lastChecked ? ` (Checked ${lastChecked.toLocaleTimeString()})` : ""}${
      retriesExhausted ? " [Retries paused. Click refresh icon to retry]" : ""
    }`;
  }

  return (
    <div
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-medium transition-all duration-200 border ${
        isOnline
          ? "bg-emerald-50/80 text-emerald-800 border-emerald-200"
          : isChecking
          ? "bg-amber-50/80 text-amber-800 border-amber-200"
          : "bg-rose-50/80 text-rose-800 border-rose-200"
      } ${className}`}
      title={tooltipText}
    >
      <span className="relative flex h-2 w-2">
        {isOnline && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
        )}
        {!isOnline && !isChecking && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
        )}
        <span
          className={`relative inline-flex rounded-full h-2 w-2 ${
            isOnline ? "bg-emerald-500" : isChecking ? "bg-amber-500" : "bg-rose-500"
          }`}
        />
      </span>

      {showText && (
        <span className="tracking-tight text-[11px] font-medium">
          {loopDetected
            ? "Config Error"
            : isOnline
            ? "Backend Online"
            : isChecking
            ? "Connecting..."
            : "Backend Offline"}
        </span>
      )}

      {!isOnline && (
        <button
          type="button"
          onClick={handleManualCheck}
          className="p-0.5 hover:bg-rose-100 rounded text-rose-600 transition-colors ml-0.5"
          title="Retry connection"
          disabled={isRetrying}
        >
          <RefreshCw className={`w-3 h-3 ${isRetrying ? "animate-spin" : ""}`} />
        </button>
      )}
    </div>
  );
};
