"use client";

import React, { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Menu,
  Search,
  Bell,
  Upload,
  Building2,
  CheckCircle2,
  AlertTriangle,
  Info,
  X,
  ChevronDown,
} from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { orgApi, OrganizationResponse, getAccessToken } from "@/lib/api";

interface HeaderProps {
  onOpenMobileSidebar: () => void;
}

const ROUTE_BREADCRUMBS: Record<string, string> = {
  "/dashboard": "Overview Dashboard",
  "/dashboard/certificates": "Certificate Registry",
  "/dashboard/upload": "Upload Certificate",
  "/dashboard/jobs": "Verification Jobs",
  "/dashboard/evidence": "Evidence Explorer",
  "/dashboard/reports": "Verification Reports",
  "/dashboard/history": "Verification History",
  "/dashboard/organization": "Organization & Members",
  "/dashboard/api-keys": "API Keys Management",
  "/dashboard/webhooks": "Webhooks Engine",
  "/dashboard/audit-logs": "Audit Logs",
  "/dashboard/settings": "System Settings",
};

function getBreadcrumb(pathname: string): string {
  if (ROUTE_BREADCRUMBS[pathname]) return ROUTE_BREADCRUMBS[pathname];
  if (pathname.startsWith("/dashboard/certificates/")) return "Certificate Verification Cockpit";
  if (pathname.startsWith("/dashboard/jobs/")) return "Job Detail View";
  return "Enterprise Verification Platform";
}

export const Header: React.FC<HeaderProps> = ({ onOpenMobileSidebar }) => {
  const pathname = usePathname();
  const [org, setOrg] = useState<OrganizationResponse | null>(null);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showOrgDropdown, setShowOrgDropdown] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);
  const orgRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!getAccessToken()) return;
    orgApi
      .getMyOrg()
      .then((res) => setOrg(res.data))
      .catch(() => setOrg(null));
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifications(false);
      }
      if (orgRef.current && !orgRef.current.contains(e.target as Node)) {
        setShowOrgDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const notifications = [
    {
      id: "1",
      title: "Integrity Engine Online",
      description: "Forensic ELA and OCR fusion models loaded.",
      time: "Just now",
      icon: CheckCircle2,
      color: "text-emerald-600",
    },
    {
      id: "2",
      title: "Tamper Defense Active",
      description: "Metadata inspection and clone detection running.",
      time: "2m ago",
      icon: AlertTriangle,
      color: "text-amber-600",
    },
    {
      id: "3",
      title: "Smart Contract Connected",
      description: "SHA-256 batch anchor sync in progress.",
      time: "5m ago",
      icon: Info,
      color: "text-indigo-600",
    },
  ];

  return (
    <header className="h-[64px] bg-white border-b border-slate-200 px-4 sm:px-6 flex items-center justify-between shrink-0 sticky top-0 z-30">
      {/* Left: Mobile Toggle & Page Title / Breadcrumb */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onOpenMobileSidebar}
          className="lg:hidden p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors cursor-pointer"
          aria-label="Open sidebar navigation"
        >
          <Menu size={20} />
        </button>

        <div className="flex items-center gap-2 min-w-0">
          <div className="lg:hidden">
            <Logo size="sm" showText={false} />
          </div>
          <div className="flex flex-col min-w-0">
            <h1 className="text-sm font-semibold text-slate-900 truncate tracking-tight">
              {getBreadcrumb(pathname)}
            </h1>
            <span className="text-[10px] text-slate-400 font-medium hidden sm:block">
              CertiVerify AI Forensic Platform
            </span>
          </div>
        </div>
      </div>

      {/* Right: Quick Ingestion, Search, Notifications, Organization */}
      <div className="flex items-center gap-2.5">
        {/* Quick Ingest Button */}
        <Link
          href="/dashboard/upload"
          className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors cursor-pointer"
        >
          <Upload size={14} />
          <span>Upload</span>
        </Link>

        {/* Global Search Mock */}
        <div className="hidden md:flex items-center relative">
          <Search size={14} className="absolute left-3 text-slate-400 pointer-events-none" />
          <input
            type="text"
            placeholder="Search certificates..."
            className="w-48 lg:w-64 pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-800 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 transition-colors"
          />
        </div>

        {/* Organization Switcher */}
        {org && (
          <div className="relative" ref={orgRef}>
            <button
              onClick={() => setShowOrgDropdown(!showOrgDropdown)}
              className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg hover:bg-slate-100 text-slate-700 transition-colors cursor-pointer"
              aria-expanded={showOrgDropdown}
              aria-label="Organization options"
            >
              <Building2 size={13} className="text-indigo-600" />
              <span className="font-medium truncate max-w-[110px]">{org.name}</span>
              <ChevronDown size={12} className="text-slate-400" />
            </button>

            {showOrgDropdown && (
              <div className="absolute right-0 mt-2 w-56 bg-white border border-slate-200 rounded-xl shadow-lg p-2 z-50 animate-in fade-in zoom-in-95">
                <div className="p-2 border-b border-slate-100">
                  <p className="text-xs font-semibold text-slate-900">{org.name}</p>
                  <p className="text-[10px] text-slate-500 font-mono">Tenant ID: {org.id.slice(0, 8)}</p>
                </div>
                <div className="pt-1">
                  <Link
                    href="/dashboard/organization"
                    onClick={() => setShowOrgDropdown(false)}
                    className="block px-2.5 py-1.5 text-xs text-slate-600 hover:text-indigo-600 hover:bg-indigo-50/60 rounded-md transition-colors"
                  >
                    Manage Organization
                  </Link>
                  <Link
                    href="/dashboard/api-keys"
                    onClick={() => setShowOrgDropdown(false)}
                    className="block px-2.5 py-1.5 text-xs text-slate-600 hover:text-indigo-600 hover:bg-indigo-50/60 rounded-md transition-colors"
                  >
                    API Credentials
                  </Link>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Notifications Dropdown */}
        <div className="relative" ref={notifRef}>
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg relative transition-colors cursor-pointer"
            aria-label="View notifications"
          >
            <Bell size={18} />
            <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-indigo-600" />
          </button>

          {showNotifications && (
            <div className="absolute right-0 mt-2 w-80 bg-white border border-slate-200 rounded-xl shadow-xl overflow-hidden z-50 animate-in fade-in zoom-in-95">
              <div className="p-3.5 border-b border-slate-100 flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-900">System Notifications</span>
                <button
                  onClick={() => setShowNotifications(false)}
                  className="p-1 text-slate-400 hover:text-slate-600 rounded"
                >
                  <X size={14} />
                </button>
              </div>

              <div className="max-h-72 overflow-y-auto divide-y divide-slate-100">
                {notifications.map((n) => {
                  const Icon = n.icon;
                  return (
                    <div key={n.id} className="p-3 hover:bg-slate-50 flex items-start gap-2.5 transition-colors">
                      <Icon size={16} className={`${n.color} mt-0.5 shrink-0`} />
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-semibold text-slate-800 leading-tight">{n.title}</p>
                        <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">{n.description}</p>
                        <span className="text-[10px] text-slate-400 mt-1 block">{n.time}</span>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="p-2.5 bg-slate-50 border-t border-slate-100 text-center">
                <Link
                  href="/dashboard/jobs"
                  onClick={() => setShowNotifications(false)}
                  className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-700 hover:underline"
                >
                  View all pipeline tasks →
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
