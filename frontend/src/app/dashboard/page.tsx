"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  FileText,
  ShieldCheck,
  AlertTriangle,
  ShieldAlert,
  UploadCloud,
  Cpu,
  Search,
  RefreshCw,
  Clock,
  Download,
  ExternalLink,
  CheckCircle2,
  ArrowRight,
  TrendingUp,
} from "lucide-react";
import {
  dashboardApi,
  analyticsApi,
  auditLogApi,
  reportApi,
  getAccessToken,
  DashboardStatsResponse,
  AnalyticsOverview,
  AuditLogResponse,
  RecentCertificate,
} from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";

export default function EnterpriseDashboardPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<DashboardStatsResponse | null>(null);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogResponse[]>([]);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const fetchDashboardData = useCallback(async () => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const [statsRes, overviewRes, auditRes] = await Promise.allSettled([
        dashboardApi.stats(),
        analyticsApi.overview(),
        auditLogApi.list({ limit: 8 }),
      ]);

      if (statsRes.status === "fulfilled") {
        setStats(statsRes.value.data);
      } else {
        console.warn("Failed to fetch dashboard stats:", statsRes.reason);
      }

      if (overviewRes.status === "fulfilled") {
        setOverview(overviewRes.value.data);
      } else {
        console.warn("Failed to fetch analytics overview:", overviewRes.reason);
      }

      if (auditRes.status === "fulfilled") {
        setAuditLogs(auditRes.value.data || []);
      } else {
        console.warn("Failed to fetch audit logs:", auditRes.reason);
      }
    } catch (err: unknown) {
      const apiErr = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(apiErr?.response?.data?.detail || apiErr?.message || "Failed to load dashboard statistics.");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const handleDownloadReport = async (certId: string) => {
    setDownloadingId(certId);
    try {
      const url = reportApi.downloadUrl(certId);
      const token = getAccessToken();
      const directUrl = token ? `${url}?token=${encodeURIComponent(token)}` : url;
      window.open(directUrl, "_blank");
    } catch (err) {
      console.error("Failed to download report:", err);
    } finally {
      setDownloadingId(null);
    }
  };

  if (loading) {
    return (
      <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-7xl mx-auto">
        <div className="flex justify-between items-center bg-white p-6 rounded-xl border border-slate-200">
          <div className="space-y-2">
            <Skeleton className="h-7 w-64" />
            <Skeleton className="h-4 w-96" />
          </div>
          <Skeleton className="h-10 w-36" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Skeleton className="h-36 rounded-xl" />
          <Skeleton className="h-36 rounded-xl" />
          <Skeleton className="h-36 rounded-xl" />
          <Skeleton className="h-36 rounded-xl" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Skeleton className="h-72 rounded-xl lg:col-span-2" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <Card className="border-rose-200 bg-rose-50/50">
          <CardContent className="p-6 space-y-4">
            <div className="flex items-center gap-3 text-rose-700">
              <AlertTriangle size={24} />
              <h2 className="text-base font-semibold">Dashboard Loading Error</h2>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">{error}</p>
            <Button
              onClick={fetchDashboardData}
              variant="primary"
              size="sm"
              icon={<RefreshCw size={14} />}
            >
              Retry Connection
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const totalCerts = stats?.total_certificates ?? 0;
  const genuineCount = stats?.prediction_distribution?.genuine ?? overview?.genuine_count ?? 0;
  const suspiciousCount = stats?.prediction_distribution?.suspicious ?? overview?.suspicious_count ?? 0;
  const inconclusiveCount = stats?.prediction_distribution?.inconclusive ?? 0;
  const fakeCount = stats?.prediction_distribution?.fake ?? overview?.fake_count ?? 0;
  const pendingCount = stats?.prediction_distribution?.not_run ?? 0;
  const avgTrust =
    stats?.avg_trust_score != null
      ? Math.round(stats.avg_trust_score)
      : overview?.avg_trust_score != null
      ? Math.round(overview.avg_trust_score)
      : null;
  const fraudAlerts = (stats?.tampered_count ?? 0) + (stats?.duplicate_count ?? 0) + fakeCount;

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-7xl mx-auto">
      {/* Header & Quick Action Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white border border-slate-200 p-6 rounded-xl shadow-sm">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">
            Enterprise Verification Cockpit
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Real-time credential ingestion ledger, AI tamper detection, and cryptographic provenance telemetry.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            onClick={fetchDashboardData}
            variant="ghost"
            size="sm"
            aria-label="Refresh statistics"
            title="Refresh statistics"
          >
            <RefreshCw size={14} />
          </Button>

          <Link href="/dashboard/upload">
            <Button variant="primary" size="sm" icon={<UploadCloud size={15} />}>
              Upload Certificate
            </Button>
          </Link>
        </div>
      </div>

      {/* Primary KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Certificates */}
        <Card className="hover:shadow-md transition-shadow">
          <CardContent className="p-5 flex flex-col justify-between h-full">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Total Certificates
              </span>
              <span className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
                <FileText size={18} />
              </span>
            </div>
            <div className="my-3">
              <div className="text-3xl font-bold text-slate-900">
                {totalCerts.toLocaleString()}
              </div>
              <span className="text-xs text-slate-500 block mt-1">
                Ingested in tenant database
              </span>
            </div>
            <div className="text-[11px] font-mono text-indigo-600 pt-3 border-t border-slate-100 flex items-center justify-between">
              <span>REGISTRY LEDGER</span>
              <span className="font-semibold px-2 py-0.5 bg-indigo-50 rounded-full text-indigo-700">ACTIVE</span>
            </div>
          </CardContent>
        </Card>

        {/* Completed / Genuine Verifications */}
        <Card className="border-emerald-100 hover:shadow-md transition-shadow">
          <CardContent className="p-5 flex flex-col justify-between h-full">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Genuine Verified
              </span>
              <span className="p-2 bg-emerald-50 text-emerald-600 rounded-lg">
                <ShieldCheck size={18} />
              </span>
            </div>
            <div className="my-3">
              <div className="text-3xl font-bold text-emerald-700">
                {genuineCount.toLocaleString()}
              </div>
              <span className="text-xs text-emerald-600 font-medium block mt-1">
                {totalCerts ? Math.round((genuineCount / totalCerts) * 100) : 0}% authentic rate
              </span>
            </div>
            <div className="text-[11px] font-mono text-emerald-700 pt-3 border-t border-slate-100 flex items-center justify-between">
              <span>PASSED ALL CHECKS</span>
              <CheckCircle2 size={14} className="text-emerald-600" />
            </div>
          </CardContent>
        </Card>

        {/* Pending & Review Jobs */}
        <Card className="border-amber-100 hover:shadow-md transition-shadow">
          <CardContent className="p-5 flex flex-col justify-between h-full">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Pending / Suspicious
              </span>
              <span className="p-2 bg-amber-50 text-amber-600 rounded-lg">
                <AlertTriangle size={18} />
              </span>
            </div>
            <div className="my-3">
              <div className="text-3xl font-bold text-amber-700">
                {(suspiciousCount + pendingCount).toLocaleString()}
              </div>
              <span className="text-xs text-amber-600 font-medium block mt-1">
                {suspiciousCount} flagged for review, {pendingCount} pending
              </span>
            </div>
            <div className="text-[11px] font-mono text-amber-700 pt-3 border-t border-slate-100 flex items-center justify-between">
              <span>NEEDS ATTENTION</span>
              <Link
                href="/dashboard/certificates?status=suspicious"
                className="hover:underline flex items-center gap-1 font-semibold"
              >
                View <ArrowRight size={10} />
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Fraud & Tamper Alerts */}
        <Card className="border-rose-100 hover:shadow-md transition-shadow">
          <CardContent className="p-5 flex flex-col justify-between h-full">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Fraud & Tamper Alerts
              </span>
              <span className="p-2 bg-rose-50 text-rose-600 rounded-lg">
                <ShieldAlert size={18} />
              </span>
            </div>
            <div className="my-3">
              <div className="text-3xl font-bold text-rose-700">
                {fraudAlerts.toLocaleString()}
              </div>
              <span className="text-xs text-rose-600 font-medium block mt-1">
                {fakeCount} fraudulent, {stats?.tampered_count ?? 0} tampered
              </span>
            </div>
            <div className="text-[11px] font-mono text-rose-700 pt-3 border-t border-slate-100 flex items-center justify-between">
              <span>HIGH RISK DETECTED</span>
              <Link
                href="/dashboard/evidence"
                className="hover:underline flex items-center gap-1 font-semibold"
              >
                Evidence <ArrowRight size={10} />
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Secondary Metrics & Launchpad */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Verification Verdict Breakdown */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between pb-4 border-b border-slate-100">
            <div>
              <CardTitle className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                <TrendingUp size={16} className="text-indigo-600" />
                Verification Outcome Distribution
              </CardTitle>
              <CardDescription className="text-xs text-slate-500 mt-0.5">
                Real AI verification verdict telemetry across current tenant.
              </CardDescription>
            </div>
            {avgTrust != null && (
              <div className="text-right">
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                  AVG TRUST SCORE
                </span>
                <div className="text-lg font-bold font-mono text-emerald-600">
                  {avgTrust} / 100
                </div>
              </div>
            )}
          </CardHeader>

          <CardContent className="p-6">
            {totalCerts === 0 ? (
              <EmptyState
                icon={<FileText size={28} className="text-slate-400" />}
                title="No verification results recorded yet"
                description="Upload a certificate to view live telemetry and breakdown stats."
                action={
                  <Link href="/dashboard/upload">
                    <Button variant="primary" size="sm" icon={<UploadCloud size={14} />}>
                      Upload Certificate
                    </Button>
                  </Link>
                }
              />
            ) : (
              <div className="space-y-5">
                {/* Stacked Progress Bar */}
                <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden flex border border-slate-200">
                  <div
                    style={{ width: `${(genuineCount / totalCerts) * 100}%` }}
                    className="bg-emerald-500 h-full transition-all"
                    title={`Genuine: ${genuineCount}`}
                  />
                  <div
                    style={{ width: `${(inconclusiveCount / totalCerts) * 100}%` }}
                    className="bg-amber-400 h-full transition-all"
                    title={`Needs Review: ${inconclusiveCount}`}
                  />
                  <div
                    style={{ width: `${(suspiciousCount / totalCerts) * 100}%` }}
                    className="bg-amber-600 h-full transition-all"
                    title={`Suspicious: ${suspiciousCount}`}
                  />
                  <div
                    style={{ width: `${(fakeCount / totalCerts) * 100}%` }}
                    className="bg-rose-500 h-full transition-all"
                    title={`Fake: ${fakeCount}`}
                  />
                  <div
                    style={{ width: `${(pendingCount / totalCerts) * 100}%` }}
                    className="bg-indigo-300 h-full transition-all"
                    title={`Pending: ${pendingCount}`}
                  />
                </div>

                {/* Legend Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="flex items-center gap-1.5 text-emerald-700 font-semibold">
                      <span className="w-2 h-2 rounded-full bg-emerald-500" />
                      Genuine
                    </div>
                    <div className="font-mono text-lg font-bold text-slate-900 mt-1">
                      {genuineCount}
                    </div>
                  </div>

                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="flex items-center gap-1.5 text-amber-700 font-semibold">
                      <span className="w-2 h-2 rounded-full bg-amber-400" />
                      Needs Review
                    </div>
                    <div className="font-mono text-lg font-bold text-slate-900 mt-1">
                      {inconclusiveCount}
                    </div>
                  </div>

                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="flex items-center gap-1.5 text-amber-800 font-semibold">
                      <span className="w-2 h-2 rounded-full bg-amber-600" />
                      Suspicious
                    </div>
                    <div className="font-mono text-lg font-bold text-slate-900 mt-1">
                      {suspiciousCount}
                    </div>
                  </div>

                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="flex items-center gap-1.5 text-rose-700 font-semibold">
                      <span className="w-2 h-2 rounded-full bg-rose-500" />
                      Forgery / Fake
                    </div>
                    <div className="font-mono text-lg font-bold text-slate-900 mt-1">
                      {fakeCount}
                    </div>
                  </div>

                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <div className="flex items-center gap-1.5 text-indigo-700 font-semibold">
                      <span className="w-2 h-2 rounded-full bg-indigo-500" />
                      Pending
                    </div>
                    <div className="font-mono text-lg font-bold text-slate-900 mt-1">
                      {pendingCount}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Quick Operations Launchpad */}
        <Card>
          <CardHeader className="pb-3 border-b border-slate-100">
            <CardTitle className="text-sm font-semibold text-slate-900">
              Forensic Launchpad
            </CardTitle>
          </CardHeader>

          <CardContent className="p-4 space-y-3">
            <Link
              href="/dashboard/upload"
              className="flex items-center justify-between p-3 bg-slate-50 hover:bg-indigo-50/60 border border-slate-200 hover:border-indigo-200 rounded-lg transition-colors group"
            >
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-100 text-indigo-600 rounded-md">
                  <UploadCloud size={16} />
                </div>
                <div>
                  <div className="text-xs font-semibold text-slate-900">
                    Upload New Certificate
                  </div>
                  <div className="text-[11px] text-slate-500">
                    Ingest PDF/Image for instant AI analysis
                  </div>
                </div>
              </div>
              <ArrowRight
                size={14}
                className="text-slate-400 group-hover:text-indigo-600 transition-transform group-hover:translate-x-0.5"
              />
            </Link>

            <Link
              href="/dashboard/jobs"
              className="flex items-center justify-between p-3 bg-slate-50 hover:bg-indigo-50/60 border border-slate-200 hover:border-indigo-200 rounded-lg transition-colors group"
            >
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-100 text-indigo-600 rounded-md">
                  <Cpu size={16} />
                </div>
                <div>
                  <div className="text-xs font-semibold text-slate-900">
                    Async Verification Jobs
                  </div>
                  <div className="text-[11px] text-slate-500">
                    Monitor job queues & execution status
                  </div>
                </div>
              </div>
              <ArrowRight
                size={14}
                className="text-slate-400 group-hover:text-indigo-600 transition-transform group-hover:translate-x-0.5"
              />
            </Link>

            <Link
              href="/dashboard/evidence"
              className="flex items-center justify-between p-3 bg-slate-50 hover:bg-indigo-50/60 border border-slate-200 hover:border-indigo-200 rounded-lg transition-colors group"
            >
              <div className="flex items-center gap-3">
                <div className="p-2 bg-emerald-100 text-emerald-600 rounded-md">
                  <Search size={16} />
                </div>
                <div>
                  <div className="text-xs font-semibold text-slate-900">
                    Evidence Explorer
                  </div>
                  <div className="text-[11px] text-slate-500">
                    Inspect explainable AI evidence logs
                  </div>
                </div>
              </div>
              <ArrowRight
                size={14}
                className="text-slate-400 group-hover:text-emerald-600 transition-transform group-hover:translate-x-0.5"
              />
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* Recent Certificate Registry & Recent Audit Events */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Certificates Table (2 cols) */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <CardTitle className="text-sm font-semibold text-slate-900">
                Recent Certificate Activity
              </CardTitle>
              <CardDescription className="text-xs text-slate-500">
                Latest certificates ingested and analyzed.
              </CardDescription>
            </div>
            <Link
              href="/dashboard/certificates"
              className="text-xs text-indigo-600 hover:text-indigo-700 font-medium flex items-center gap-1"
            >
              View All <ArrowRight size={12} />
            </Link>
          </CardHeader>

          <CardContent className="p-0">
            {!stats?.recent_certificates || stats.recent_certificates.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  icon={<FileText size={28} className="text-slate-400" />}
                  title="No certificates ingested yet"
                  description="Upload your first certificate to start automated verification."
                  action={
                    <Link href="/dashboard/upload">
                      <Button variant="primary" size="sm" icon={<UploadCloud size={14} />}>
                        Upload Certificate
                      </Button>
                    </Link>
                  }
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 text-[10px] uppercase font-mono">
                    <tr>
                      <th className="px-5 py-3">Filename</th>
                      <th className="px-5 py-3">Uploaded At</th>
                      <th className="px-5 py-3">Trust Score</th>
                      <th className="px-5 py-3">Verdict</th>
                      <th className="px-5 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {stats.recent_certificates.slice(0, 6).map((cert: RecentCertificate) => {
                      const isInc = cert.prediction_label === "inconclusive" || cert.prediction_label === "inconclusive / needs review";
                      const verdictVariant =
                        cert.prediction_label === "genuine"
                          ? "genuine"
                          : isInc
                          ? "inconclusive"
                          : cert.prediction_label === "suspicious"
                          ? "suspicious"
                          : cert.prediction_label === "fake"
                          ? "fake"
                          : "neutral";

                      return (
                        <tr key={cert.id} className="hover:bg-slate-50/70 transition-colors">
                          <td className="px-5 py-3.5">
                            <div className="font-medium text-slate-900 truncate max-w-[200px]">
                              {cert.original_filename}
                            </div>
                            <div className="font-mono text-[10px] text-slate-400 uppercase">
                              {cert.file_type}
                            </div>
                          </td>
                          <td className="px-5 py-3.5 font-mono text-[11px] text-slate-500">
                            {new Date(cert.uploaded_at).toLocaleString([], {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </td>
                          <td className="px-5 py-3.5 font-mono text-xs">
                            {cert.trust_score != null ? (
                              <span
                                className={
                                  cert.trust_score >= 70
                                    ? "text-emerald-700 font-semibold"
                                    : cert.trust_score >= 40
                                    ? "text-amber-700 font-semibold"
                                    : "text-rose-700 font-semibold"
                                }
                              >
                                {Math.round(cert.trust_score)} / 100
                              </span>
                            ) : (
                              <span className="text-slate-400">Pending</span>
                            )}
                          </td>
                          <td className="px-5 py-3.5">
                            <Badge variant={verdictVariant} size="sm">
                              {isInc ? "NEEDS REVIEW" : (cert.prediction_label || "PENDING")}
                            </Badge>
                          </td>
                          <td className="px-5 py-3.5 text-right whitespace-nowrap">
                            <div className="inline-flex items-center gap-1.5">
                              {cert.has_report && (
                                <button
                                  onClick={() => handleDownloadReport(cert.id)}
                                  disabled={downloadingId === cert.id}
                                  title="Download PDF Report"
                                  className="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded transition-colors"
                                >
                                  <Download size={13} />
                                </button>
                              )}
                              <Link
                                href={`/dashboard/certificates/${cert.id}`}
                                className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
                                title="Inspect Certificate"
                              >
                                <ExternalLink size={13} />
                              </Link>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Audit Log Stream (1 col) */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-slate-100">
            <CardTitle className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
              <Clock size={14} className="text-indigo-600" />
              Audit Event Stream
            </CardTitle>
            <Link
              href="/dashboard/audit-logs"
              className="text-[11px] text-indigo-600 hover:underline font-mono"
            >
              View All
            </Link>
          </CardHeader>

          <CardContent className="p-4">
            {auditLogs.length === 0 ? (
              <p className="py-8 text-center text-xs text-slate-400">
                No audit events recorded yet or permission not granted.
              </p>
            ) : (
              <div className="space-y-2.5 max-h-[340px] overflow-y-auto pr-1">
                {auditLogs.map((log) => (
                  <div
                    key={log.id}
                    className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[11px] font-semibold text-indigo-700">
                        {log.action}
                      </span>
                      <span className="font-mono text-[10px] text-slate-400">
                        {new Date(log.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <span>Entity: {log.entity_type}</span>
                      <span className="font-mono">
                        {log.actor_user_id ? `User:${log.actor_user_id.slice(0, 6)}` : "System"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
