"use client";

import React, { useCallback, useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  History,
  Search,
  RefreshCw,
  AlertTriangle,
  ExternalLink,
  Download,
  Filter,
  ChevronLeft,
  ChevronRight,
  FileCheck2,
  Trash2,
  Loader2,
} from "lucide-react";
import { certificateApi, CertificateHistoryItem, getAccessToken, reportApi } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
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
import { Modal } from "@/components/ui/Modal";
import { Toast, ToastType } from "@/components/ui/Toast";

const ITEMS_PER_PAGE = 10;

export default function VerificationHistoryPage() {
  const router = useRouter();
  const [historyItems, setHistoryItems] = useState<CertificateHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [verdictFilter, setVerdictFilter] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { data } = await certificateApi.getHistory();
      setHistoryItems(data);
    } catch (err: unknown) {
      const apiErr = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(apiErr?.response?.data?.detail || apiErr?.message || "Failed to load verification history.");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleDownloadReport = async (certId: string) => {
    setDownloadingId(certId);
    try {
      await reportApi.download(certId);
    } catch (err: any) {
      console.error("Failed to download report:", err);
      setToast({
        type: "error",
        title: "Download Failed",
        message: err?.message || "Please ensure the report has been generated in the AI Cockpit.",
      });
    } finally {
      setDownloadingId(null);
    }
  };

  const [itemToDelete, setItemToDelete] = useState<CertificateHistoryItem | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: ToastType; title: string; message?: string } | null>(null);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const handleConfirmDelete = async () => {
    if (!itemToDelete) return;
    const targetId = itemToDelete.certificate_id;
    const targetFilename = itemToDelete.filename;
    setDeletingId(targetId);
    try {
      await certificateApi.deleteHistory(targetId);
      setHistoryItems((prev) => prev.filter((item) => item.certificate_id !== targetId));
      setItemToDelete(null);
      setToast({
        type: "success",
        title: "History Entry Deleted",
        message: `Verification record for "${targetFilename}" was successfully removed from history.`,
      });
    } catch (err: unknown) {
      const apiErr = err as { response?: { data?: { detail?: string } }; message?: string };
      const errorMsg =
        apiErr?.response?.data?.detail ||
        apiErr?.message ||
        "Failed to delete verification history entry.";
      setToast({
        type: "error",
        title: "Deletion Failed",
        message: errorMsg,
      });
    } finally {
      setDeletingId(null);
    }
  };

  const filteredItems = useMemo(() => {
    return historyItems.filter((item) => {
      const q = search.toLowerCase().trim();
      const matchesSearch =
        !q ||
        item.filename.toLowerCase().includes(q) ||
        item.certificate_id.toLowerCase().includes(q) ||
        (item.prediction || "").toLowerCase().includes(q) ||
        (item.document_type || "").toLowerCase().includes(q);

      const matchesVerdict =
        verdictFilter === "all" ||
        (verdictFilter === "inconclusive"
          ? (item.prediction || "").toLowerCase() === "inconclusive" || (item.prediction || "").toLowerCase().includes("inconclusive")
          : (item.prediction || "").toLowerCase() === verdictFilter.toLowerCase());

      return matchesSearch && matchesVerdict;
    });
  }, [historyItems, search, verdictFilter]);

  // Reset to page 1 when search or filter changes
  useEffect(() => {
    setCurrentPage(1);
  }, [search, verdictFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / ITEMS_PER_PAGE));
  const paginatedItems = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    return filteredItems.slice(start, start + ITEMS_PER_PAGE);
  }, [filteredItems, currentPage]);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white border border-slate-200 p-6 rounded-xl shadow-sm">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1.5">
            <Link href="/dashboard" className="hover:text-indigo-600 transition-colors">
              Dashboard
            </Link>
            <span>/</span>
            <span className="text-indigo-600 font-semibold">Verification History</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2 tracking-tight">
            <History size={22} className="text-indigo-600" />
            Chronological Verification History
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Complete ledger of past verification events, forensic outcomes, and generated audit reports.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            onClick={fetchHistory}
            variant="ghost"
            size="sm"
            aria-label="Refresh history"
            title="Refresh history"
          >
            <RefreshCw size={14} />
          </Button>
        </div>
      </div>

      {/* Main Table Card */}
      <Card>
        <CardHeader className="p-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full sm:w-auto">
            <div className="relative w-full sm:w-80">
              <Input
                type="text"
                placeholder="Search by filename or ID..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                leftIcon={<Search size={14} className="text-slate-400" />}
              />
            </div>

            <div className="w-full sm:w-44">
              <Select
                value={verdictFilter}
                onChange={(e) => setVerdictFilter(e.target.value)}
                options={[
                  { value: "all", label: "All Verdicts" },
                  { value: "genuine", label: "Genuine Only" },
                  { value: "suspicious", label: "Suspicious Only" },
                  { value: "inconclusive", label: "Needs Review Only" },
                  { value: "fake", label: "Fake Only" },
                ]}
              />
            </div>
          </div>

          <span className="text-xs font-mono text-slate-500 shrink-0">
            Showing {filteredItems.length} of {historyItems.length} events
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
            <div className="p-10 text-center text-xs text-rose-600 space-y-2">
              <AlertTriangle size={24} className="mx-auto" />
              <p>{error}</p>
              <Button onClick={fetchHistory} variant="primary" size="sm" className="mt-2">
                Retry Loading
              </Button>
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="p-10">
              <EmptyState
                icon={<FileCheck2 size={32} className="text-slate-400" />}
                title="No verification records found"
                description={
                  search || verdictFilter !== "all"
                    ? "Try adjusting your search query or verdict filter."
                    : "Upload documents to begin generating verifiable ledger records."
                }
                action={
                  <Link href="/dashboard/upload">
                    <Button variant="primary" size="sm">
                      Upload Certificate
                    </Button>
                  </Link>
                }
              />
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50 text-[10px] uppercase font-mono text-slate-500">
                      <TableHead className="px-5 py-3">Timestamp</TableHead>
                      <TableHead className="px-5 py-3">Document</TableHead>
                      <TableHead className="px-5 py-3">Doc Type</TableHead>
                      <TableHead className="px-5 py-3">Trust Score</TableHead>
                      <TableHead className="px-5 py-3">Verdict</TableHead>
                      <TableHead className="px-5 py-3 text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedItems.map((item, idx) => {
                      const isInc = item.prediction === "inconclusive" || (item.prediction || "").toLowerCase().includes("inconclusive");
                      const verdictVariant =
                        item.prediction === "genuine"
                          ? "genuine"
                          : isInc
                          ? "inconclusive"
                          : item.prediction === "suspicious"
                          ? "suspicious"
                          : item.prediction === "fake"
                          ? "fake"
                          : "neutral";

                      return (
                        <TableRow
                          key={`${item.certificate_id}-${idx}`}
                          className="hover:bg-slate-50/70 transition-colors"
                        >
                          <TableCell className="px-5 py-3.5 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                            {new Date(item.timestamp).toLocaleString([], {
                              month: "short",
                              day: "numeric",
                              year: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </TableCell>
                          <TableCell className="px-5 py-3.5">
                            <div className="font-medium text-slate-900 truncate max-w-xs">
                              {item.filename}
                            </div>
                            <div className="font-mono text-[10px] text-slate-400 uppercase">
                              {item.file_type}
                            </div>
                          </TableCell>
                          <TableCell className="px-5 py-3.5 font-mono text-xs text-indigo-700 font-medium">
                            {item.document_type || "Unclassified"}
                          </TableCell>
                          <TableCell className="px-5 py-3.5 font-mono text-xs">
                            {item.trust_score != null ? (
                              <span
                                className={
                                  item.trust_score >= 70
                                    ? "text-emerald-700 font-semibold"
                                    : item.trust_score >= 40
                                    ? "text-amber-700 font-semibold"
                                    : "text-rose-700 font-semibold"
                                }
                              >
                                {Math.round(item.trust_score)} / 100
                              </span>
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </TableCell>
                          <TableCell className="px-5 py-3.5 whitespace-nowrap">
                            <Badge variant={verdictVariant} size="sm">
                              {isInc ? "NEEDS REVIEW" : (item.prediction || "COMPLETED")}
                            </Badge>
                          </TableCell>
                          <TableCell className="px-5 py-3.5 text-right whitespace-nowrap">
                            <div className="inline-flex items-center gap-1.5 justify-end">
                              <button
                                onClick={() => handleDownloadReport(item.certificate_id)}
                                disabled={downloadingId === item.certificate_id || deletingId === item.certificate_id}
                                title="Download Verification Report"
                                aria-label="Download Verification Report"
                                className="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded transition-colors disabled:opacity-50 cursor-pointer"
                              >
                                <Download size={13} />
                              </button>
                              <Link
                                href={`/dashboard/certificates/${item.certificate_id}`}
                                className="px-2.5 py-1 text-xs text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 font-medium rounded inline-flex items-center gap-1 transition-colors"
                              >
                                <span>Cockpit</span>
                                <ExternalLink size={12} />
                              </Link>
                              <button
                                onClick={() => setItemToDelete(item)}
                                disabled={deletingId === item.certificate_id}
                                title="Delete verification history entry"
                                aria-label={`Delete history entry for ${item.filename}`}
                                className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors disabled:opacity-50 cursor-pointer"
                              >
                                {deletingId === item.certificate_id ? (
                                  <Loader2 size={13} className="animate-spin text-rose-600" />
                                ) : (
                                  <Trash2 size={13} />
                                )}
                              </button>
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>

              {/* Pagination controls */}
              {totalPages > 1 && (
                <div className="p-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                  <span>
                    Page {currentPage} of {totalPages}
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage <= 1}
                      variant="ghost"
                      size="sm"
                      icon={<ChevronLeft size={14} />}
                    >
                      Previous
                    </Button>
                    <Button
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                      disabled={currentPage >= totalPages}
                      variant="ghost"
                      size="sm"
                      icon={<ChevronRight size={14} />}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!itemToDelete}
        onClose={() => {
          if (!deletingId) setItemToDelete(null);
        }}
        title={
          <div className="flex items-center gap-2 text-rose-600">
            <AlertTriangle className="w-5 h-5 shrink-0" />
            <span className="font-semibold text-slate-900">Delete Verification History Entry</span>
          </div>
        }
        description="Are you sure you want to delete this verification history entry? This action cannot be undone."
        maxWidth="md"
        footer={
          <div className="flex items-center justify-end gap-2 w-full">
            <Button
              variant="secondary"
              size="sm"
              disabled={!!deletingId}
              onClick={() => setItemToDelete(null)}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={!!deletingId}
              onClick={handleConfirmDelete}
            >
              Delete
            </Button>
          </div>
        }
      >
        {itemToDelete && (
          <div className="space-y-3 text-xs text-slate-600">
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1.5 font-mono text-[11px]">
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Document:</span>
                <span className="font-medium text-slate-800 truncate max-w-[220px]">
                  {itemToDelete.filename}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Timestamp:</span>
                <span className="text-slate-600">
                  {new Date(itemToDelete.timestamp).toLocaleString([], {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Verdict:</span>
                <span className="font-semibold uppercase text-slate-700">
                  {itemToDelete.prediction || "Completed"}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Certificate ID:</span>
                <span className="text-slate-500 font-mono text-[10px]">
                  {itemToDelete.certificate_id}
                </span>
              </div>
            </div>
            <p className="text-slate-500 text-[11px] leading-relaxed">
              Note: This action only removes the entry from your verification history. Original document archives and cryptographic audit logs remain safely preserved.
            </p>
          </div>
        )}
      </Modal>

      {/* Toast Notification */}
      {toast && (
        <div className="fixed bottom-5 right-5 z-50">
          <Toast
            type={toast.type}
            title={toast.title}
            message={toast.message}
            onClose={() => setToast(null)}
          />
        </div>
      )}
    </div>
  );
}
