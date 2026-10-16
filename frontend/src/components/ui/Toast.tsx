import React from "react";
import { cn } from "@/lib/utils";
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export type ToastType = "success" | "warning" | "error" | "info";

export interface ToastProps {
  id?: string;
  type?: ToastType;
  title: string;
  message?: string;
  onClose?: () => void;
  className?: string;
}

export const Toast: React.FC<ToastProps> = ({
  type = "info",
  title,
  message,
  onClose,
  className,
}) => {
  const icons = {
    success: <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />,
    warning: <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />,
    error: <AlertCircle className="w-5 h-5 text-red-600 shrink-0" />,
    info: <Info className="w-5 h-5 text-indigo-600 shrink-0" />,
  };

  const borders = {
    success: "border-emerald-200 bg-white",
    warning: "border-amber-200 bg-white",
    error: "border-red-200 bg-white",
    info: "border-indigo-200 bg-white",
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 12, scale: 0.98 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "flex items-start gap-3 p-4 rounded-xl border shadow-lg max-w-sm w-full select-none",
        borders[type],
        className
      )}
      role="alert"
    >
      {icons[type]}
      <div className="flex-1 space-y-0.5 pr-2">
        <p className="text-sm font-semibold text-slate-900 leading-tight">{title}</p>
        {message && <p className="text-xs text-slate-600 leading-normal">{message}</p>}
      </div>
      {onClose && (
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-600 p-1 rounded-md hover:bg-slate-100 transition-colors cursor-pointer"
          aria-label="Dismiss toast"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </motion.div>
  );
};

export default Toast;
