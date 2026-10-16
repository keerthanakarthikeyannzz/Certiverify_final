import React from "react";
import { cn } from "@/lib/utils";

export interface TabItem {
  id: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
  disabled?: boolean;
}

export interface TabsProps {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  className?: string;
  variant?: "pill" | "underline";
}

export const Tabs: React.FC<TabsProps> = ({
  items,
  activeId,
  onChange,
  className,
  variant = "pill",
}) => {
  return (
    <div
      className={cn(
        variant === "pill"
          ? "inline-flex p-1 bg-slate-100 rounded-lg border border-slate-200/60 gap-1"
          : "flex border-b border-slate-200 space-x-6",
        className
      )}
      role="tablist"
    >
      {items.map((tab) => {
        const isActive = tab.id === activeId;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            disabled={tab.disabled}
            onClick={() => !tab.disabled && onChange(tab.id)}
            className={cn(
              "flex items-center gap-2 text-sm font-medium transition-all duration-150 select-none cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600 focus-visible:ring-offset-1 rounded-md disabled:opacity-40 disabled:cursor-not-allowed",
              variant === "pill" && [
                "px-3.5 py-1.5",
                isActive
                  ? "bg-white text-slate-900 font-semibold shadow-sm"
                  : "text-slate-600 hover:text-slate-900 hover:bg-white/50",
              ],
              variant === "underline" && [
                "pb-3 -mb-px border-b-2",
                isActive
                  ? "border-indigo-600 text-indigo-600 font-semibold"
                  : "border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300",
              ]
            )}
          >
            {tab.icon && <span className="shrink-0">{tab.icon}</span>}
            <span>{tab.label}</span>
            {tab.badge && <span className="shrink-0">{tab.badge}</span>}
          </button>
        );
      })}
    </div>
  );
};

export default Tabs;
