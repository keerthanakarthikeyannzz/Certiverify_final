"use client";

import React, { useEffect, useState, useCallback, Suspense, useMemo } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Search,
  RefreshCw,
  FileText,
  ShieldAlert,
  AlertTriangle,
  Copy,
  Check,
  ChevronRight,
  ExternalLink,
  Database,
  Info,
  Activity,
} from "lucide-react";
import {
  certificateApi,
  evidenceApi,
  getAccessToken,
  CertificateResponse,
  EvidenceItemResponse,
} from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";

type UIState = "LOADING" | "SUCCESS" | "EMPTY" | "ERROR" | "IN_PROGRESS";

export default function EvidenceExplorerPage() {
  return (
    <Suspense
      fallback={
        <div className="p-8 max-w-7xl mx-auto space-y-4">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      }
    >
      <EvidenceExplorerContent />
    </Suspense>
  );
}

function EvidenceExplorerContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialCertId = searchParams?.get("certId") || "";

  const [certificates, setCertificates] = useState<CertificateResponse[]>([]);
  const [selectedCertId, setSelectedCertId] = useState<string>(initialCertId);
  const [loadingCerts, setLoadingCerts] = useState(true);

  // Evidence state
  const [uiState, setUiState] = useState<UIState>("LOADING");
  const [evidenceItems, setEvidenceItems] = useState<EvidenceItemResponse[]>([]);
  const [totalItems, setTotalItems] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [totalPages, setTotalPages] = useState(1);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState<string>("all");
  const [filterStage, setFilterStage] = useState<string>("all");
  const [copiedHash, setCopiedHash] = useState(false);

  // Selected Detail Panel
  const [selectedItem, setSelectedItem] = useState<EvidenceItemResponse | null>(null);

  // Fetch Certificate List
  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    certificateApi
      .list()
      .then((res) => {
        setCertificates(res.data);
        if (res.data.length > 0 && !selectedCertId) {
          setSelectedCertId(res.data[0].id);
        }
      })
      .catch(() => setCertificates([]))
      .finally(() => setLoadingCerts(false));
  }, [router, selectedCertId]);

  // Fetch Evidence Items for Selected Certificate
  const fetchEvidence = useCallback(async () => {
    if (!selectedCertId) {
      setUiState("EMPTY");
      setEvidenceItems([]);
      return;
    }

    setUiState("LOADING");
    setErrorMessage(null);

    try {
      const { data } = await evidenceApi.getEvidence(selectedCertId, {
        page,
        page_size: pageSize,
        evidence_type: filterType !== "all" ? filterType : undefined,
      });

      if (!data || !data.items || data.items.length === 0) {
        setUiState("EMPTY");
        setEvidenceItems([]);
        setTotalItems(0);
        setTotalPages(1);
        setSelectedItem(null);
        return;
      }

      setEvidenceItems(data.items);
      setTotalItems(data.total);
      setTotalPages(data.total_pages || 1);
      setUiState("SUCCESS");

      // Set default selected item
      if (!selectedItem || !data.items.some((i: EvidenceItemResponse) => i.id === selectedItem.id)) {
        setSelectedItem(data.items[0]);
      }
    } catch (err: unknown) {
      const apiErr = err as { response?: { data?: { detail?: string } } };
      setErrorMessage(apiErr?.response?.data?.detail || "Unable to retrieve evidence records for this certificate.");
      setUiState("ERROR");
    }
  }, [selectedCertId, filterType, page, pageSize, selectedItem]);

  useEffect(() => {
    fetchEvidence();
  }, [fetchEvidence]);

  const filteredItems = useMemo(() => {
    return evidenceItems.filter((item) => {
      const q = searchQuery.toLowerCase().trim();
      const matchesQuery =
        !q ||
        item.evidence_id.toLowerCase().includes(q) ||
        item.explanation.toLowerCase().includes(q) ||
        item.algorithm_engine.toLowerCase().includes(q) ||
        (item.document_hash || "").toLowerCase().includes(q);

      const matchesStage = filterStage === "all" || item.stage.toLowerCase() === filterStage.toLowerCase();

      return matchesQuery && matchesStage;
    });
  }, [evidenceItems, searchQuery, filterStage]);

  const selectedCert = certificates.find((c) => c.id === selectedCertId);

  const handleCopyHash = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  const renderResultBadge = (result: string) => {
    const res = result.toUpperCase();
    if (res === "PASS" || res === "VERIFIED" || res === "MATCH" || res === "GENUINE" || res === "CONSISTENT") {
      return (
        <Badge variant="genuine" size="sm">
          <Check size={10} className="mr-1" />
          {result}
        </Badge>
      );
    }
    if (res === "FAIL" || res === "FORGERY" || res === "HIGH_RISK" || res === "MISMATCH" || res === "TAMPERED") {
      return (
        <Badge variant="fake" size="sm">
          <ShieldAlert size={10} className="mr-1" />
          {result}
        </Badge>
      );
    }
    return (
      <Badge variant="suspicious" size="sm">
        <AlertTriangle size={10} className="mr-1" />
        {result}
      </Badge>
    );
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Top Banner & Certificate Selector */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white border border-slate-200 p-6 rounded-xl shadow-sm">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1.5">
            <Link href="/dashboard" className="hover:text-indigo-600 transition-colors">
              Dashboard
            </Link>
            <span>/</span>
            <span className="text-indigo-600 font-semibold">Evidence Explorer</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2 tracking-tight">
            <Database size={22} className="text-indigo-600" />
            Explainable AI Evidence Explorer
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Cryptographic provenance, neural engine signals, and explainable evidence trail for every verification verdict.
          </p>
        </div>

        {/* Certificate Picker Dropdown */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="w-64">
            <label className="text-[11px] font-semibold text-slate-500 uppercase block mb-1">
              Certificate Context
            </label>
            <select
              value={selectedCertId}
              onChange={(e) => {
                setSelectedCertId(e.target.value);
                setSelectedItem(null);
                setPage(1);
              }}
              disabled={loadingCerts || certificates.length === 0}
              className="w-full bg-white border border-slate-300 text-slate-900 text-xs px-3 py-2 rounded-lg font-mono focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
            >
              {loadingCerts ? (
                <option>Loading certificates...</option>
              ) : certificates.length === 0 ? (
                <option>No certificates found</option>
              ) : (
                certificates.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.original_filename} ({c.id.slice(0, 8)})
                  </option>
                ))
              )}
            </select>
          </div>

          <Button
            onClick={fetchEvidence}
            variant="ghost"
            size="sm"
            className="mt-5"
            aria-label="Reload Evidence"
            title="Reload Evidence"
          >
            <RefreshCw size={14} />
          </Button>
        </div>
      </div>

      {/* Selected Certificate Summary Bar */}
      {selectedCert && (
        <Card className="border-indigo-100 bg-indigo-50/30">
          <CardContent className="p-4 flex flex-wrap items-center justify-between gap-4 text-xs">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-indigo-100 text-indigo-700 rounded-lg">
                <FileText size={20} />
              </div>
              <div>
                <div className="font-semibold text-slate-900 text-sm">
                  {selectedCert.original_filename}
                </div>
                <div className="font-mono text-[11px] text-slate-500 mt-0.5">
                  Format: <span className="uppercase text-slate-700 font-semibold">{selectedCert.file_type}</span> | Size: {(selectedCert.file_size_bytes / 1024).toFixed(1)} KB | Uploaded: {new Date(selectedCert.uploaded_at).toLocaleString()}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3 font-mono text-xs">
              <div className="p-2 bg-white border border-slate-200 rounded-lg shadow-sm">
                <span className="text-[10px] text-slate-400 block font-semibold uppercase">SHA-256 HASH</span>
                <span className="text-indigo-700 font-bold">
                  {selectedCert.sha256_hash ? `${selectedCert.sha256_hash.slice(0, 12)}…${selectedCert.sha256_hash.slice(-8)}` : "Pending"}
                </span>
              </div>

              <Link href={`/dashboard/certificates/${selectedCert.id}`}>
                <Button variant="primary" size="sm" icon={<ExternalLink size={12} />}>
                  Inspect Cockpit
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main Evidence Workbench: Filters + List + Detail Drawer */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Filter & Evidence List (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <Card>
            <CardHeader className="p-3 border-b border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="w-full sm:w-64">
                <Input
                  type="text"
                  placeholder="Search evidence..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  leftIcon={<Search size={13} className="text-slate-400" />}
                />
              </div>

              <div className="flex items-center gap-2 w-full sm:w-auto">
                <select
                  value={filterType}
                  onChange={(e) => setFilterType(e.target.value)}
                  className="bg-white border border-slate-300 text-slate-700 text-xs px-2.5 py-1.5 rounded-lg focus:border-indigo-600 focus:outline-none"
                >
                  <option value="all">All Types</option>
                  <option value="ocr">OCR Data</option>
                  <option value="qr">QR Code</option>
                  <option value="blockchain">Blockchain</option>
                  <option value="tampering">Tamper ELA</option>
                  <option value="duplicate">Duplicate</option>
                  <option value="fraud_prediction">Fraud Prediction</option>
                </select>

                <select
                  value={filterStage}
                  onChange={(e) => setFilterStage(e.target.value)}
                  className="bg-white border border-slate-300 text-slate-700 text-xs px-2.5 py-1.5 rounded-lg focus:border-indigo-600 focus:outline-none"
                >
                  <option value="all">All Stages</option>
                  <option value="document_analysis">Analysis</option>
                  <option value="ocr">OCR</option>
                  <option value="qr_verification">QR Verify</option>
                  <option value="blockchain_verification">Blockchain</option>
                  <option value="tamper_analysis">Tampering</option>
                  <option value="duplicate_detection">Duplicate</option>
                  <option value="fraud_analysis">Fraud</option>
                </select>
              </div>
            </CardHeader>

            <CardContent className="p-0">
              {uiState === "LOADING" && (
                <div className="p-8 space-y-3">
                  {[...Array(4)].map((_, i) => (
                    <Skeleton key={i} className="h-16 w-full rounded-lg" />
                  ))}
                </div>
              )}

              {uiState === "IN_PROGRESS" && (
                <div className="p-10 text-center space-y-3">
                  <Activity size={32} className="text-indigo-600 animate-pulse mx-auto" />
                  <h3 className="text-sm font-semibold text-slate-900">Verification Job In Progress</h3>
                  <p className="text-xs text-slate-500 max-w-sm mx-auto">
                    Verification stages are actively running. Evidence records will populate automatically as each stage completes.
                  </p>
                  <Button onClick={fetchEvidence} variant="primary" size="sm">
                    Refresh Telemetry
                  </Button>
                </div>
              )}

              {uiState === "EMPTY" && (
                <div className="p-10">
                  <EmptyState
                    icon={<Database size={32} className="text-slate-400" />}
                    title="No Evidence Records Found"
                    description="No evidence records match your current filters or verification has not been initiated for this certificate yet."
                    action={
                      <Link href={selectedCertId ? `/dashboard/certificates/${selectedCertId}` : "/dashboard/upload"}>
                        <Button variant="primary" size="sm">
                          Run Verification Pipeline →
                        </Button>
                      </Link>
                    }
                  />
                </div>
              )}

              {uiState === "ERROR" && (
                <div className="p-8 text-center text-xs text-rose-600 space-y-2">
                  <AlertTriangle size={32} className="mx-auto" />
                  <h3 className="text-sm font-semibold">Failed to Load Evidence</h3>
                  <p className="text-slate-600 max-w-sm mx-auto">
                    {errorMessage || "An unexpected error occurred while querying the evidence ledger."}
                  </p>
                  <Button onClick={fetchEvidence} variant="primary" size="sm" icon={<RefreshCw size={13} />}>
                    Retry Evidence Load
                  </Button>
                </div>
              )}

              {uiState === "SUCCESS" && (
                <div className="divide-y divide-slate-100">
                  {filteredItems.length === 0 ? (
                    <div className="p-8 text-center text-xs text-slate-400">
                      No evidence items matched search filter "{searchQuery}".
                    </div>
                  ) : (
                    filteredItems.map((item) => {
                      const isSelected = selectedItem?.id === item.id;
                      return (
                        <div
                          key={item.id}
                          onClick={() => setSelectedItem(item)}
                          className={`p-4 cursor-pointer transition-colors flex items-start justify-between gap-3 ${
                            isSelected
                              ? "bg-indigo-50/60 border-l-4 border-indigo-600"
                              : "hover:bg-slate-50"
                          }`}
                        >
                          <div className="space-y-1.5 min-w-0">
                            <div className="flex items-center gap-2">
                              {renderResultBadge(item.result)}
                              <span className="font-mono text-xs font-bold text-slate-900">
                                {item.evidence_id}
                              </span>
                              <span className="font-mono text-[10px] px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-slate-600 uppercase">
                                {item.evidence_type}
                              </span>
                            </div>

                            <p className="text-xs text-slate-700 line-clamp-2 leading-relaxed">
                              {item.explanation}
                            </p>

                            <div className="flex items-center gap-3 font-mono text-[11px] text-slate-500">
                              <span>Engine: <strong className="text-indigo-700">{item.algorithm_engine}</strong></span>
                              <span>Confidence: <strong className="text-emerald-700">{Math.round(item.confidence * 100)}%</strong></span>
                              <span>Stage: <strong className="text-slate-700">{item.stage}</strong></span>
                            </div>
                          </div>

                          <ChevronRight
                            size={16}
                            className={`shrink-0 ${isSelected ? "text-indigo-600" : "text-slate-300"}`}
                          />
                        </div>
                      );
                    })
                  )}

                  {totalPages > 1 && (
                    <div className="p-3 bg-slate-50 border-t border-slate-100 flex items-center justify-between text-xs font-mono text-slate-500">
                      <span>Page {page} of {totalPages} ({totalItems} records)</span>
                      <div className="flex items-center gap-2">
                        <Button
                          onClick={() => setPage((p) => Math.max(1, p - 1))}
                          disabled={page === 1}
                          variant="ghost"
                          size="sm"
                        >
                          Previous
                        </Button>
                        <Button
                          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                          disabled={page === totalPages}
                          variant="ghost"
                          size="sm"
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Evidence Detail Panel (5 cols) */}
        <div className="lg:col-span-5">
          {selectedItem ? (
            <Card className="sticky top-20">
              <CardHeader className="pb-3 border-b border-slate-100 flex flex-row items-center justify-between">
                <div>
                  <span className="font-mono text-[10px] text-slate-400 uppercase tracking-wider block font-semibold">
                    EVIDENCE RECORD DETAIL
                  </span>
                  <h3 className="text-sm font-bold text-slate-900 font-mono mt-0.5">
                    {selectedItem.evidence_id}
                  </h3>
                </div>
                {renderResultBadge(selectedItem.result)}
              </CardHeader>

              <CardContent className="p-5 space-y-5">
                <div className="grid grid-cols-2 gap-3 font-mono text-xs">
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-0.5">
                    <span className="text-[10px] text-slate-500 uppercase font-semibold block">
                      CONFIDENCE SCORE
                    </span>
                    <div className="text-xl font-bold text-emerald-700">
                      {Math.round(selectedItem.confidence * 100)}%
                    </div>
                  </div>

                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-0.5">
                    <span className="text-[10px] text-slate-500 uppercase font-semibold block">
                      ALGORITHM ENGINE
                    </span>
                    <div className="text-xs font-bold text-indigo-700 truncate">
                      {selectedItem.algorithm_engine}
                    </div>
                    <div className="text-[10px] text-slate-400">
                      v{selectedItem.algorithm_version || "1.0.0"}
                    </div>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold text-slate-700 uppercase block">
                    Human-Readable Explanation
                  </label>
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-800 leading-relaxed">
                    {selectedItem.explanation}
                  </div>
                </div>

                <div className="space-y-2 font-mono text-xs">
                  <div className="flex items-center justify-between text-[11px] text-slate-500">
                    <span className="font-semibold uppercase">DOCUMENT HASH (SHA-256)</span>
                    <button
                      onClick={() => handleCopyHash(selectedItem.document_hash)}
                      className="text-indigo-600 hover:underline flex items-center gap-1 font-sans"
                    >
                      {copiedHash ? <Check size={11} /> : <Copy size={11} />}
                      {copiedHash ? "Copied!" : "Copy"}
                    </button>
                  </div>
                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-[11px] text-indigo-900 break-all font-mono">
                    {selectedItem.document_hash || "N/A"}
                  </div>
                </div>

                <div className="space-y-2 text-xs font-mono">
                  <label className="text-[11px] font-semibold text-slate-700 uppercase block font-sans">
                    Provenential Telemetry
                  </label>
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
                    <div className="flex justify-between py-1 border-b border-slate-200">
                      <span className="text-slate-500">Stage:</span>
                      <span className="text-slate-900 font-semibold">{selectedItem.stage}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-200">
                      <span className="text-slate-500">Source:</span>
                      <span className="text-slate-900 font-semibold">{selectedItem.source}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-200">
                      <span className="text-slate-500">Evidence Type:</span>
                      <span className="text-indigo-700 font-semibold">{selectedItem.evidence_type}</span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-slate-500">Logged At:</span>
                      <span className="text-slate-500">{new Date(selectedItem.timestamp).toLocaleString()}</span>
                    </div>
                  </div>
                </div>

                {selectedItem.details && (
                  <div className="space-y-1.5 font-mono text-xs">
                    <label className="text-[11px] font-semibold text-slate-700 uppercase block font-sans">
                      Engine Details JSON
                    </label>
                    <pre className="p-3 bg-slate-900 text-emerald-400 rounded-lg text-[10px] overflow-x-auto max-h-48 font-mono">
                      {JSON.stringify(selectedItem.details, null, 2)}
                    </pre>
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card className="text-center p-8">
              <CardContent className="space-y-2">
                <Info size={28} className="mx-auto text-indigo-400" />
                <p className="text-xs text-slate-500">
                  Select any evidence item from the list to view provenance, confidence, and engine telemetry.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
