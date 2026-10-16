"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ScrollText,
  Search,
  RefreshCw,
  AlertTriangle,
  Eye,
  Lock,
  FileQuestion,
  X,
} from "lucide-react";
import { auditLogApi, getAccessToken, AuditLogResponse } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
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

export default function AuditLogsPage() {
  const router = useRouter();
  const [logs, setLogs] = useState<AuditLogResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const [search, setSearch] = useState("");
  const [limit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [selectedLog, setSelectedLog] = useState<AuditLogResponse | null>(null);

  const fetchLogs = useCallback(async () => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    setLoading(true);
    setError(null);
    setPermissionDenied(false);

    try {
      const { data } = await auditLogApi.list({ limit, offset });
      setLogs(data);
    } catch (err: unknown) {
      const apiErr = err as { response?: { status?: number; data?: { detail?: string } } };
      if (apiErr?.response?.status === 403) {
        setPermissionDenied(true);
      } else {
        setError(apiErr?.response?.data?.detail || "Failed to load audit logs.");
      }
    } finally {
      setLoading(false);
    }
  }, [limit, offset, router]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const filteredLogs = logs.filter((log) => {
    const q = search.toLowerCase().trim();
    return (
      !q ||
      log.action.toLowerCase().includes(q) ||
      log.entity_type.toLowerCase().includes(q) ||
      (log.entity_id || "").toLowerCase().includes(q) ||
      (log.actor_user_id || "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white border border-slate-200 p-6 rounded-xl shadow-sm">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1.5">
            <Link href="/dashboard" className="hover:text-indigo-600 transition-colors">
              Dashboard
            </Link>
            <span>/</span>
            <span className="text-indigo-600 font-semibold">Audit Logs</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2 tracking-tight">
            <ScrollText size={22} className="text-indigo-600" />
            Enterprise Immutable Audit Event Logs
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Organization-scoped security event stream for compliance auditing and governance tracking.
          </p>
        </div>

        <Button
          onClick={fetchLogs}
          variant="ghost"
          size="sm"
          aria-label="Refresh logs"
          title="Refresh logs"
        >
          <RefreshCw size={14} />
        </Button>
      </div>

      {permissionDenied ? (
        <Card className="border-rose-200 bg-rose-50/40 text-center p-8">
          <CardContent className="space-y-3">
            <Lock size={36} className="text-rose-600 mx-auto" />
            <h2 className="text-base font-bold text-slate-900">Access Restricted: Permission Denied</h2>
            <p className="text-xs text-slate-600 max-w-md mx-auto">
              Viewing enterprise audit logs requires the <code className="text-indigo-600 font-mono font-semibold">audit:read</code> permission scope. Please contact your organization owner to request access.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          {/* Controls Bar */}
          <CardHeader className="p-4 border-b border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="w-full sm:w-80">
              <Input
                type="text"
                placeholder="Search by action, entity, user..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                leftIcon={<Search size={13} className="text-slate-400" />}
              />
            </div>

            <span className="text-xs font-mono text-slate-500">
              Showing {filteredLogs.length} events
            </span>
          </CardHeader>

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
                <Button onClick={fetchLogs} variant="primary" size="sm" className="mt-2">
                  Retry Loading
                </Button>
              </div>
            ) : filteredLogs.length === 0 ? (
              <div className="p-10">
                <EmptyState
                  icon={<FileQuestion size={32} className="text-slate-400" />}
                  title="No audit events recorded"
                  description="Security events and API ingestion actions will stream here automatically."
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50 text-slate-500 font-mono text-[10px] uppercase">
                      <TableHead className="px-5 py-3">Timestamp</TableHead>
                      <TableHead className="px-5 py-3">Action Event</TableHead>
                      <TableHead className="px-5 py-3">Entity Type</TableHead>
                      <TableHead className="px-5 py-3">Entity ID</TableHead>
                      <TableHead className="px-5 py-3">Actor User</TableHead>
                      <TableHead className="px-5 py-3 text-right">Details</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredLogs.map((log) => (
                      <TableRow key={log.id} className="hover:bg-slate-50/70 transition">
                        <TableCell className="px-5 py-3.5 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                          {new Date(log.timestamp).toLocaleString([], {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })}
                        </TableCell>

                        <TableCell className="px-5 py-3.5 font-mono text-xs font-bold text-indigo-700">
                          {log.action}
                        </TableCell>

                        <TableCell className="px-5 py-3.5 font-mono text-xs text-slate-700 uppercase">
                          {log.entity_type}
                        </TableCell>

                        <TableCell className="px-5 py-3.5 font-mono text-xs text-slate-400">
                          {log.entity_id ? log.entity_id.slice(0, 16) : "N/A"}
                        </TableCell>

                        <TableCell className="px-5 py-3.5 font-mono text-xs text-slate-500">
                          {log.actor_user_id ? `User:${log.actor_user_id.slice(0, 8)}` : "System"}
                        </TableCell>

                        <TableCell className="px-5 py-3.5 text-right whitespace-nowrap">
                          {log.metadata_json && (
                            <button
                              onClick={() => setSelectedLog(log)}
                              className="p-1.5 text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 rounded transition-colors"
                              title="View Metadata"
                            >
                              <Eye size={14} />
                            </button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {/* Pagination Controls */}
            <div className="p-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between text-xs font-mono text-slate-500">
              <span>Offset: {offset}</span>
              <div className="flex items-center gap-2">
                <Button
                  onClick={() => setOffset((o) => Math.max(0, o - limit))}
                  disabled={offset === 0}
                  variant="ghost"
                  size="sm"
                >
                  Previous
                </Button>
                <Button
                  onClick={() => setOffset((o) => o + limit)}
                  disabled={logs.length < limit}
                  variant="ghost"
                  size="sm"
                >
                  Next
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Metadata Detail Modal */}
      {selectedLog && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 w-full max-w-lg rounded-xl p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div>
                <span className="font-mono text-[10px] text-slate-400 uppercase block font-semibold">
                  AUDIT LOG METADATA
                </span>
                <div className="text-xs font-mono font-bold text-indigo-700 mt-0.5">
                  {selectedLog.action}
                </div>
              </div>
              <Button
                onClick={() => setSelectedLog(null)}
                variant="ghost"
                size="sm"
                className="p-1 h-auto"
              >
                <X size={14} />
              </Button>
            </div>

            <pre className="p-3 bg-slate-900 text-emerald-400 rounded-lg text-[11px] font-mono overflow-x-auto max-h-64">
              {JSON.stringify(selectedLog.metadata_json, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
