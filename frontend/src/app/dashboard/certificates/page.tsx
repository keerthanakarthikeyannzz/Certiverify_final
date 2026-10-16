"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  FileText,
  Search,
  Download,
  ExternalLink,
  ShieldCheck,
  AlertTriangle,
  Clock,
  Loader2,
  RefreshCw,
  UploadCloud,
} from "lucide-react";
import {
  dashboardApi,
  DashboardStatsResponse,
  certificateApi,
  CertificateResponse,
  RecentCertificate,
  getAccessToken,
} from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableHeader,
  TableCell,
} from "@/components/ui/Table";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";

type FilterStatus = "all" | "genuine" | "suspicious" | "fake" | "inconclusive" | "not_run";

// ---- Authenticated PDF report downloader -------------------------------------
async function downloadReport(certId: string, verificationId?: string) {
  const token = getAccessToken();
  if (!token) {
    alert("Please log in first.");
    return;
  }

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const res = await fetch(`${API_URL}/api/v1/certificates/${certId}/download-report`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    alert(`Download failed (${res.status}). Verify that the report has been generated in the AI Cockpit.`);
    return;
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `CertiVerify_${verificationId ?? certId}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
// ------------------------------------------------------------------------------

export default function CertificateRegistryPage() {
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [stats, setStats] = useState<DashboardStatsResponse | null>(null);
  const [rawCertificates, setRawCertificates] = useState<CertificateResponse[]>([]);

  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);

    try {
      const [statsRes, certsRes] = await Promise.all([
        dashboardApi.stats().catch(() => null),
        certificateApi.list().catch(() => null),
      ]);

      if (statsRes) setStats(statsRes.data);
      if (certsRes) setRawCertificates(certsRes.data);
      setError(null);
    } catch {
      setError("Failed to synchronize certificate registry ledger.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (!getAccessToken()) {
      router.push("/login");
      return;
    }
    fetchData();
  }, [fetchData, router]);

  // Merge raw uploaded certificates with telemetry from dashboard stats
  const unifiedCertificates: RecentCertificate[] = useMemo(() => {
    const statsMap = new Map<string, RecentCertificate>();
    (stats?.recent_certificates ?? []).forEach((c) => {
      statsMap.set(c.id, c);
    });

    // Start with all raw certificates
    const merged: RecentCertificate[] = rawCertificates.map((rc) => {
      const telemetry = statsMap.get(rc.id);
      if (telemetry) return telemetry;

      return {
        id: rc.id,
        original_filename: rc.original_filename,
        file_type: rc.file_type,
        uploaded_at: rc.uploaded_at,
        has_report: false,
      };
    });

    // Also append any from stats that might not be in raw list
    (stats?.recent_certificates ?? []).forEach((sc) => {
      if (!merged.some((m) => m.id === sc.id)) {
        merged.push(sc);
      }
    });

    // Sort descending by upload timestamp
    return merged.sort(
      (a, b) => new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime()
    );
  }, [rawCertificates, stats]);

  // Filter based on search query and status selection
  const filteredCertificates = useMemo(() => {
    return unifiedCertificates.filter((c) => {
      const query = search.toLowerCase().trim();
      const matchSearch =
        !query ||
        c.original_filename.toLowerCase().includes(query) ||
        (c.verification_id ?? "").toLowerCase().includes(query) ||
        c.id.toLowerCase().includes(query);

      const label = c.prediction_label?.toLowerCase();
      let matchStatus = true;
      if (filterStatus === "genuine") {
        matchStatus = label === "genuine";
      } else if (filterStatus === "suspicious") {
        matchStatus = label === "suspicious";
      } else if (filterStatus === "fake") {
        matchStatus = label === "fake";
      } else if (filterStatus === "inconclusive") {
        matchStatus = label === "inconclusive" || label === "inconclusive / needs review";
      } else if (filterStatus === "not_run") {
        matchStatus = !label || label === "not_run" || label === "pending";
      }

      return matchSearch && matchStatus;
    });
  }, [unifiedCertificates, search, filterStatus]);

  const handleDownload = async (certId: string, verificationId?: string) => {
    setDownloadingId(certId);
    try {
      await downloadReport(certId, verificationId);
    } finally {
      setDownloadingId(null);
    }
  };

  // Counts for quick filter pills
  const counts = useMemo(() => {
    let genuine = 0;
    let suspicious = 0;
    let fake = 0;
    let inconclusive = 0;
    let pending = 0;

    unifiedCertificates.forEach((c) => {
      const l = c.prediction_label?.toLowerCase();
      if (l === "genuine") genuine++;
      else if (l === "suspicious") suspicious++;
      else if (l === "fake") fake++;
      else if (l === "inconclusive" || l === "inconclusive / needs review") inconclusive++;
      else pending++;
    });

    return { total: unifiedCertificates.length, genuine, suspicious, fake, inconclusive, pending };
  }, [unifiedCertificates]);

  return (
    <main className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-7xl mx-auto">
      {/* Top Header & Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white border border-slate-200 p-6 rounded-xl shadow-sm">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1.5">
            <Link href="/dashboard" className="hover:text-indigo-600 transition-colors">
              Dashboard
            </Link>
            <span>/</span>
            <span className="text-indigo-600 font-semibold">Certificate Registry</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2 tracking-tight">
            <FileText size={22} className="text-indigo-600" />
            Certificate Registry & Audit History Ledger
          </h1>
          <p className="text-xs text-slate-500">
            Institutional audit trail of all verified academic credentials, cryptographic hashes, and forensic outcomes.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Button
            onClick={() => fetchData(true)}
            disabled={refreshing || loading}
            variant="ghost"
            size="sm"
            aria-label="Synchronize registry ledger"
            title="Synchronize registry ledger"
          >
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            <span>{refreshing ? "Syncing..." : "Refresh"}</span>
          </Button>

          <Link href="/dashboard/upload">
            <Button variant="primary" size="sm" icon={<UploadCloud size={14} />}>
              Ingest Document
            </Button>
          </Link>
        </div>
      </div>

      {/* Metric Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
              Total Ingested
            </span>
            <span className="text-2xl font-bold text-slate-900 font-mono">
              {loading ? "…" : counts.total}
            </span>
          </CardContent>
        </Card>

        <Card className="border-emerald-100">
          <CardContent className="p-4 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
              Genuine Credentials
            </span>
            <span className="text-2xl font-bold text-emerald-700 font-mono">
              {loading ? "…" : counts.genuine}
            </span>
          </CardContent>
        </Card>

        <Card className="border-amber-100">
          <CardContent className="p-4 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
              Suspicious / Anomalies
            </span>
            <span className="text-2xl font-bold text-amber-700 font-mono">
              {loading ? "…" : counts.suspicious}
            </span>
          </CardContent>
        </Card>

        <Card className="border-rose-100">
          <CardContent className="p-4 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
              Detected Forgeries
            </span>
            <span className="text-2xl font-bold text-rose-700 font-mono">
              {loading ? "…" : counts.fake}
            </span>
          </CardContent>
        </Card>
      </div>

      {/* Main Ledger Card */}
      <Card>
        {/* Filter and Search Bar */}
        <CardHeader className="p-4 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-3">
          {/* Status Filter Pills */}
          <div className="flex flex-wrap items-center gap-1.5">
            {[
              { id: "all", label: "All Records", count: counts.total },
              { id: "genuine", label: "Genuine", count: counts.genuine },
              { id: "suspicious", label: "Suspicious", count: counts.suspicious },
              { id: "inconclusive", label: "Needs Review", count: counts.inconclusive },
              { id: "fake", label: "Forgeries", count: counts.fake },
              { id: "not_run", label: "Pending", count: counts.pending },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setFilterStatus(tab.id as FilterStatus)}
                className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors flex items-center gap-1.5 ${
                  filterStatus === tab.id
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200 border border-slate-200"
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.2 rounded-full ${
                    filterStatus === tab.id
                      ? "bg-white/20 text-white"
                      : "bg-slate-200 text-slate-700"
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          {/* Search Input */}
          <div className="w-full md:w-72">
            <Input
              type="text"
              placeholder="Search filename, ID…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              leftIcon={<Search size={13} className="text-slate-400" />}
            />
          </div>
        </CardHeader>

        {/* Ledger Table */}
        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-14 w-full rounded-lg" />
              ))}
            </div>
          ) : error ? (
            <div className="p-8 text-center text-xs text-rose-600 space-y-2">
              <AlertTriangle size={24} className="mx-auto" />
              <p>{error}</p>
              <Button onClick={() => fetchData()} variant="primary" size="sm" className="mt-2">
                Retry Sync
              </Button>
            </div>
          ) : filteredCertificates.length === 0 ? (
            <div className="p-10">
              <EmptyState
                icon={<FileText size={32} className="text-slate-400" />}
                title={
                  search || filterStatus !== "all"
                    ? "No matching certificates found"
                    : "Registry is currently empty"
                }
                description={
                  search || filterStatus !== "all"
                    ? "Try adjusting your search query or verdict status filters."
                    : "Ingest your first certificate to trigger OCR extraction and forensic verification."
                }
                action={
                  <Link href="/dashboard/upload">
                    <Button variant="primary" size="sm" icon={<UploadCloud size={13} />}>
                      Upload First Certificate
                    </Button>
                  </Link>
                }
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50 text-slate-500 text-[10px] uppercase font-mono">
                    <TableHead className="px-5 py-3">Document Credential</TableHead>
                    <TableHead className="px-5 py-3">Verification ID</TableHead>
                    <TableHead className="px-5 py-3">Uploaded Timestamp</TableHead>
                    <TableHead className="px-5 py-3">Trust Score</TableHead>
                    <TableHead className="px-5 py-3">Forensic Verdict</TableHead>
                    <TableHead className="px-5 py-3 text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredCertificates.map((c) => {
                    const isDownloading = downloadingId === c.id;
                    const isInc = c.prediction_label === "inconclusive" || c.prediction_label === "inconclusive / needs review";
                    const verdictVariant =
                      c.prediction_label === "genuine"
                        ? "genuine"
                        : isInc
                        ? "inconclusive"
                        : c.prediction_label === "suspicious"
                        ? "suspicious"
                        : c.prediction_label === "fake"
                        ? "fake"
                        : "neutral";

                    return (
                      <TableRow key={c.id} className="hover:bg-slate-50/70 transition-colors">
                        {/* Document Name */}
                        <TableCell className="px-5 py-3.5">
                          <div className="flex items-center gap-2.5">
                            <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600 shrink-0">
                              <FileText size={15} />
                            </div>
                            <div className="min-w-0">
                              <Link
                                href={`/dashboard/certificates/${c.id}`}
                                className="font-medium text-slate-900 hover:text-indigo-600 transition truncate block max-w-xs sm:max-w-sm"
                                title={c.original_filename}
                              >
                                {c.original_filename}
                              </Link>
                              <span className="text-[10px] font-mono text-slate-400 block truncate">
                                UUID: {c.id.slice(0, 16)}…
                              </span>
                            </div>
                          </div>
                        </TableCell>

                        {/* Verification ID */}
                        <TableCell className="px-5 py-3.5 font-mono text-xs text-slate-500">
                          {c.verification_id ? (
                            <span className="text-indigo-600 font-semibold font-mono">
                              {c.verification_id}
                            </span>
                          ) : (
                            <span className="text-slate-400">N/A</span>
                          )}
                        </TableCell>

                        {/* Timestamp */}
                        <TableCell className="px-5 py-3.5 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                          <div className="flex items-center gap-1.5">
                            <Clock size={11} className="shrink-0 text-slate-400" />
                            <span>
                              {new Date(c.uploaded_at).toLocaleString([], {
                                year: "numeric",
                                month: "short",
                                day: "numeric",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                          </div>
                        </TableCell>

                        {/* Trust Score */}
                        <TableCell className="px-5 py-3.5 font-mono text-xs">
                          {c.trust_score !== undefined ? (
                            <span
                              className={`font-semibold ${
                                c.trust_score >= 80
                                  ? "text-emerald-700"
                                  : c.trust_score >= 50
                                  ? "text-amber-700"
                                  : "text-rose-700"
                              }`}
                            >
                              {c.trust_score} / 100
                            </span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </TableCell>

                        {/* Final Verdict */}
                        <TableCell className="px-5 py-3.5 whitespace-nowrap">
                          <Badge variant={verdictVariant} size="sm">
                            {isInc ? "NEEDS REVIEW" : (c.prediction_label || "PENDING")}
                          </Badge>
                        </TableCell>

                        {/* Actions */}
                        <TableCell className="px-5 py-3.5 text-right whitespace-nowrap">
                          <div className="flex items-center justify-end gap-1.5">
                            {c.has_report && (
                              <button
                                onClick={() => handleDownload(c.id, c.verification_id)}
                                disabled={isDownloading}
                                className="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded transition flex items-center gap-1 disabled:opacity-50"
                                title="Download official PDF verification report"
                              >
                                {isDownloading ? (
                                  <Loader2 size={12} className="animate-spin" />
                                ) : (
                                  <Download size={12} />
                                )}
                                <span className="text-xs font-medium hidden sm:inline">PDF</span>
                              </button>
                            )}

                            <Link
                              href={`/dashboard/certificates/${c.id}`}
                              className="px-2.5 py-1 text-xs font-medium text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 rounded transition inline-flex items-center gap-1"
                              title="Inspect in AI Forensic Cockpit"
                            >
                              <span>Inspect</span>
                              <ExternalLink size={11} />
                            </Link>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
