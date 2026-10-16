"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Settings,
  User,
  Shield,
  Database,
  CheckCircle2,
} from "lucide-react";
import { authApi, getAccessToken, UserResponse } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    authApi.me().then((res) => setUser(res.data)).catch(() => null);
  }, [router]);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between bg-white border border-slate-200 p-6 rounded-xl shadow-sm">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1.5">
            <Link href="/dashboard" className="hover:text-indigo-600 transition-colors">
              Dashboard
            </Link>
            <span>/</span>
            <span className="text-indigo-600 font-semibold">System Settings</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2 tracking-tight">
            <Settings size={22} className="text-indigo-600" />
            Enterprise Platform Settings & Preferences
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            User account, verification engine rules, security policy, and UI theme preferences.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* User Account Settings */}
        <Card>
          <CardHeader className="flex flex-row items-center gap-2 pb-3 border-b border-slate-100">
            <User size={16} className="text-indigo-600" />
            <CardTitle className="text-sm font-semibold text-slate-900">
              Authenticated User Account
            </CardTitle>
          </CardHeader>

          <CardContent className="p-5 space-y-4 font-mono text-xs">
            <div>
              <span className="text-[10px] text-slate-400 uppercase font-semibold block font-sans">
                Full Name
              </span>
              <div className="text-sm font-bold text-slate-900 font-sans mt-0.5">
                {user?.full_name || "Enterprise User"}
              </div>
            </div>

            <div>
              <span className="text-[10px] text-slate-400 uppercase font-semibold block font-sans">
                Email Address
              </span>
              <div className="text-xs text-indigo-700 font-bold mt-0.5">
                {user?.email || "user@certiverify.io"}
              </div>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-slate-100">
              <div>
                <span className="text-[10px] text-slate-400 uppercase font-semibold block font-sans">
                  Role
                </span>
                <Badge variant="neutral" size="sm" className="mt-1">
                  {user?.role || "ADMIN"}
                </Badge>
              </div>
              <div className="text-right">
                <span className="text-[10px] text-slate-400 uppercase font-semibold block font-sans">
                  Email Status
                </span>
                <Badge variant="genuine" size="sm" className="mt-1">
                  <CheckCircle2 size={10} className="mr-1" />
                  VERIFIED
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Verification Engine Security Rules */}
        <Card>
          <CardHeader className="flex flex-row items-center gap-2 pb-3 border-b border-slate-100">
            <Shield size={16} className="text-emerald-600" />
            <CardTitle className="text-sm font-semibold text-slate-900">
              Verification Engine Rules
            </CardTitle>
          </CardHeader>

          <CardContent className="p-5 space-y-3 text-xs text-slate-700">
            <div className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="font-medium">Automatic ELA Tamper Analysis</span>
              <Badge variant="genuine" size="sm">
                ENABLED
              </Badge>
            </div>

            <div className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="font-medium">QR Cross-Validation & Hash Matching</span>
              <Badge variant="genuine" size="sm">
                ENABLED
              </Badge>
            </div>

            <div className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="font-medium">Blockchain On-Chain Hash Registry</span>
              <Badge variant="genuine" size="sm">
                ACTIVE
              </Badge>
            </div>
          </CardContent>
        </Card>

        {/* System Information */}
        <Card className="md:col-span-2">
          <CardHeader className="flex flex-row items-center gap-2 pb-3 border-b border-slate-100">
            <Database size={16} className="text-indigo-600" />
            <CardTitle className="text-sm font-semibold text-slate-900">
              System Information & Telemetry
            </CardTitle>
          </CardHeader>

          <CardContent className="p-5">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                <span className="text-[10px] text-slate-400 block font-semibold">VERSION</span>
                <span className="text-slate-900 font-bold font-sans">CertiVerify v2.0 Enterprise</span>
              </div>
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                <span className="text-[10px] text-slate-400 block font-semibold">FRAMEWORK</span>
                <span className="text-indigo-700 font-bold">Next.js 14 / FastAPI</span>
              </div>
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                <span className="text-[10px] text-slate-400 block font-semibold">THEME</span>
                <span className="text-emerald-700 font-bold">Enterprise Light Indigo</span>
              </div>
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                <span className="text-[10px] text-slate-400 block font-semibold">SECURITY</span>
                <span className="text-emerald-700 font-bold">Tenant Isolated</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
