"use client";

import React, { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  ShieldCheck,
  UploadCloud,
  Cpu,
  Search,
  FileText,
  History,
  Building2,
  Key,
  Webhook,
  ScrollText,
  Settings,
  X,
  LucideIcon,
  ChevronRight,
} from "lucide-react";
import { UserProfile } from "./UserProfile";
import { Logo } from "@/components/ui/Logo";
import { authApi, getAccessToken } from "@/lib/api";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  badge?: string;
  badgeVariant?: "brand" | "success" | "neutral";
}

const SIDEBAR_SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Overview & Ingestion",
    items: [
      { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
      { label: "Upload Certificate", href: "/dashboard/upload", icon: UploadCloud, badge: "+ New", badgeVariant: "brand" },
      { label: "Certificates", href: "/dashboard/certificates", icon: ShieldCheck },
    ],
  },
  {
    title: "Pipeline & Forensics",
    items: [
      { label: "Verification Jobs", href: "/dashboard/jobs", icon: Cpu },
      { label: "Evidence Explorer", href: "/dashboard/evidence", icon: Search, badge: "AI Provenance", badgeVariant: "success" },
      { label: "Reports", href: "/dashboard/reports", icon: FileText },
      { label: "Verification History", href: "/dashboard/history", icon: History },
    ],
  },
  {
    title: "Enterprise & Admin",
    items: [
      { label: "Organizations & Members", href: "/dashboard/organization", icon: Building2 },
      { label: "API Keys", href: "/dashboard/api-keys", icon: Key },
      { label: "Webhooks", href: "/dashboard/webhooks", icon: Webhook },
      { label: "Audit Logs", href: "/dashboard/audit-logs", icon: ScrollText },
      { label: "Settings", href: "/dashboard/settings", icon: Settings },
    ],
  },
];

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const pathname = usePathname();

  return (
    <Suspense fallback={<SidebarShell isOpen={isOpen} onClose={onClose} />}>
      <SidebarContent isOpen={isOpen} onClose={onClose} pathname={pathname} />
    </Suspense>
  );
};

interface SidebarContentProps {
  isOpen: boolean;
  onClose: () => void;
  pathname?: string;
}

function SidebarShell({ isOpen, onClose }: SidebarContentProps) {
  return (
    <>
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-40 lg:hidden"
          aria-hidden="true"
        />
      )}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 w-[288px] bg-white border-r border-slate-200 flex flex-col transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          isOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full"
        }`}
      >
        <div className="h-[64px] px-4 flex items-center justify-between border-b border-slate-200 shrink-0">
          <div className="w-[120px] h-[28px] bg-slate-100 rounded-lg animate-pulse" />
          <button onClick={onClose} className="lg:hidden p-1.5 text-slate-400 rounded-lg">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 px-3 py-3 space-y-4 overflow-y-auto">
          <div className="h-4 w-24 bg-slate-100 rounded animate-pulse" />
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-8 bg-slate-100 rounded-lg animate-pulse" />
            ))}
          </div>
        </div>
        <div className="h-[64px] px-3 flex items-center border-t border-slate-200 shrink-0">
          <div className="w-8 h-8 rounded-full bg-slate-100 animate-pulse" />
        </div>
      </aside>
    </>
  );
}

function SidebarContent({ isOpen, onClose, pathname = "" }: SidebarContentProps) {
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) return;
    authApi
      .me()
      .then((res) => setRole(res.data.role.toLowerCase()))
      .catch(() => {});
  }, []);

  const isLinkActive = (href: string): boolean => {
    if (href === "/dashboard") {
      return pathname === "/dashboard";
    }
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  const sections = SIDEBAR_SECTIONS.map((section) => {
    if (section.title === "Enterprise & Admin" && role === "student") {
      return {
        ...section,
        items: section.items.filter((item) => item.href === "/dashboard/settings"),
      };
    }
    return section;
  });

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-40 lg:hidden"
          aria-hidden="true"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 w-[288px] bg-white border-r border-slate-200 flex flex-col transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          isOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full"
        }`}
      >
        {/* Branding Header */}
        <div className="h-[64px] px-4 flex items-center justify-between border-b border-slate-200 shrink-0">
          <Logo size="sm" href="/dashboard" onClick={onClose} ariaLabel="CertiVerify Home" />

          <div className="flex items-center gap-2">
            <span className="text-[10px] bg-indigo-50 text-indigo-700 border border-indigo-100 px-2 py-0.5 rounded-md font-semibold tracking-wide hidden sm:inline-block">
              ENTERPRISE
            </span>

            {/* Mobile close trigger */}
            <button
              onClick={onClose}
              className="lg:hidden p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
              aria-label="Close sidebar"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Navigation Content */}
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
          {sections.map((section) => (
            <div key={section.title}>
              <div className="px-3 pb-2 text-[10px] uppercase tracking-wider text-slate-400 font-bold">
                {section.title}
              </div>
              <nav className="space-y-0.5">
                {section.items.map((item) => {
                  const active = isLinkActive(item.href);
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.label}
                      href={item.href}
                      onClick={onClose}
                      className={`flex items-center justify-between px-3 py-2 text-xs font-medium rounded-lg transition-colors group cursor-pointer ${
                        active
                          ? "bg-indigo-50 text-indigo-700 font-semibold border-l-2 border-indigo-600 shadow-xs"
                          : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <Icon
                          size={16}
                          className={active ? "text-indigo-600" : "text-slate-400 group-hover:text-slate-600"}
                        />
                        <span className="truncate">{item.label}</span>
                      </div>

                      {item.badge ? (
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-md font-semibold tracking-tight ${
                            item.badgeVariant === "brand"
                              ? "bg-indigo-600 text-white"
                              : item.badgeVariant === "success"
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : "bg-slate-100 text-slate-600 border border-slate-200"
                          }`}
                        >
                          {item.badge}
                        </span>
                      ) : active ? (
                        <ChevronRight size={14} className="text-indigo-600" />
                      ) : null}
                    </Link>
                  );
                })}
              </nav>
            </div>
          ))}

          {/* Engine Telemetry Footer Card */}
          <div className="mx-1 p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                PIPELINE STATUS
              </span>
              <span className="inline-flex items-center gap-1.5 text-[10px] text-emerald-700 font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                ONLINE
              </span>
            </div>
            <p className="text-[11px] text-slate-500 leading-snug">
              OCR, Tamper ELA, Blockchain & AI Provenance operational.
            </p>
          </div>
        </div>

        {/* User Profile Footer */}
        <UserProfile />
      </aside>
    </>
  );
}

export default Sidebar;
