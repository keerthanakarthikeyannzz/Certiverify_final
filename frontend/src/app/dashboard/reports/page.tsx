"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  FileText,
  Download,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  FileQuestion,
  Sparkles,
  Lock,
  ExternalLink,
  Copy,
  Check,
  ShieldCheck,
  Search,
  CheckCircle,
  XCircle,
} from "lucide-react";
import {
  certificateApi,
  reportApi,
  verificationApi,
  getAccessToken,
  CertificateResponse,
  VerificationReportResponse,
  VerificationResultResponse,
  ReportListItem,
} from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";

export default function VerificationReportsPage() {
  const router = useRouter();
  const [certificates, setCertificates] = useState<CertificateResponse[]>([]);
  const [selectedCertId, setSelectedCertId] = useState<string>("");
  const [loadingCerts, setLoadingCerts] = useState(true);

  // Selected report state
  const [report, setReport] = useState<VerificationReportResponse | null>(null);
  const [verification, setVerification] = useState<VerificationResultResponse | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generationStep, setGenerationStep] = useState<string>("");
  const [copiedHash, setCopiedHash] = useState(false);
  const [copiedSig, setCopiedSig] = useState(false);

  // All Generated Reports list
  const [reportsList, setReportsList] = useState<ReportListItem[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [searchFilter, setSearchFilter] = useState("");

  // Signature verification modal/state
  const [verifyingCertId, setVerifyingCertId] = useState<string | null>(null);
  const [downloadingCertId, setDownloadingCertId] = useState<string | null>(null);
  const [sigStatus, setSigStatus] = useState<{
    certId: string;
    isValid: boolean;
    detail: string;
  } | null>(null);

  const fetchReportsList = () => {
    reportApi
      .list()
      .then((res) => setReportsList(res.data))
      .catch(() => setReportsList([]))
      .finally(() => setLoadingList(false));
  };

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    certificateApi
      .list()
      .then((res) => {
        setCertificates(res.data);
        if (res.data.length > 0) {
          setSelectedCertId(res.data[0].id);
        }
      })
      .catch(() => setCertificates([]))
      .finally(() => setLoadingCerts(false));

    fetchReportsList();
  }, [router]);

  useEffect(() => {
    if (!selectedCertId) return;

    setLoadingReport(true);
    setReport(null);
    setVerification(null);
    setSigStatus(null);

    Promise.allSettled([
      reportApi.get(selectedCertId),
      verificationApi.get(selectedCertId),
    ])
      .then(([reportRes, verRes]) => {
        if (reportRes.status === "fulfilled") setReport(reportRes.value.data);
        if (verRes.status === "fulfilled") setVerification(verRes.value.data);
      })
      .finally(() => setLoadingReport(false));
  }, [selectedCertId]);

  const handleGenerateReport = async () => {
    if (!selectedCertId) return;
    setGenerating(true);
    setGenerationStep("Gathering verified pipeline evidence...");

    const stepTimer1 = setTimeout(() => {
      setGenerationStep("Compiling PDF tables & ELA heatmaps...");
    }, 600);

    const stepTimer2 = setTimeout(() => {
      setGenerationStep("Applying HMAC-SHA256 digital signature...");
    }, 1200);

    try {
      const { data } = await reportApi.generate(selectedCertId);
      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      setReport(data);
      fetchReportsList();
    } catch (err: any) {
      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      alert("Failed to generate verification report: " + (err?.response?.data?.detail || err?.message || "Unknown error"));
    } finally {
      setGenerating(false);
      setGenerationStep("");
    }
  };

  const handleDownloadReport = async (certId?: string) => {
    const targetId = certId || selectedCertId;
    if (!targetId) return;
    setDownloadingCertId(targetId);
    try {
      await reportApi.download(targetId);
    } catch (err: any) {
      console.error("Failed to download report:", err);
      alert("Failed to download verification report: " + (err?.message || "Please try again."));
    } finally {
      setDownloadingCertId(null);
    }
  };

  const handleViewReport = async (certId?: string) => {
    const targetId = certId || selectedCertId;
    if (!targetId) return;
    try {
      await reportApi.viewInline(targetId);
    } catch (err: any) {
      console.error("Failed to view report:", err);
      alert("Failed to preview verification report: " + (err?.message || "Please try again."));
    }
  };

  const handleVerifySignature = async (certId: string) => {
    setVerifyingCertId(certId);
    try {
      const res = await reportApi.verifySignature(certId);
      setSigStatus({
        certId,
        isValid: res.data.is_valid,
        detail: res.data.detail,
      });
    } catch (err: any) {
      setSigStatus({
        certId,
        isValid: false,
        detail: err?.response?.data?.detail || "Verification request failed",
      });
    } finally {
      setVerifyingCertId(null);
    }
  };

  const selectedCert = certificates.find((c) => c.id === selectedCertId);

  const handleCopyHash = (hash?: string) => {
    if (!hash) return;
    navigator.clipboard.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

  const handleCopySig = (sig?: string) => {
    if (!sig) return;
    navigator.clipboard.writeText(sig);
    setCopiedSig(true);
    setTimeout(() => setCopiedSig(false), 2000);
  };

  const filteredReports = reportsList.filter((r) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return (
      r.verification_id?.toLowerCase().includes(q) ||
      r.certificate_filename?.toLowerCase().includes(q) ||
      r.sha256_hash?.toLowerCase().includes(q) ||
      r.prediction_label?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-8">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white border border-slate-200 p-6 rounded-xl shadow-sm">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1.5">
            <Link href="/dashboard" className="hover:text-indigo-600 transition-colors">
              Dashboard
            </Link>
            <span>/</span>
            <span className="text-indigo-600 font-semibold">Verification Reports</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2 tracking-tight">
            <FileText size={22} className="text-indigo-600" />
            Official Verification Reports & Audit Dossiers
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Generate, download, and cryptographically verify PDF reports with HMAC-SHA256 integrity proofs.
          </p>
        </div>

        {/* Certificate Selector Dropdown */}
        <div className="w-72 shrink-0">
          <label className="text-[11px] font-semibold text-slate-500 uppercase block mb-1">
            Active Certificate Dossier
          </label>
          <select
            value={selectedCertId}
            onChange={(e) => setSelectedCertId(e.target.value)}
            disabled={loadingCerts || certificates.length === 0}
            className="w-full bg-white border border-slate-300 text-slate-900 text-xs px-3 py-2 rounded-lg font-mono focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/20"
          >
            {loadingCerts ? (
              <option>Loading certificates...</option>
            ) : certificates.length === 0 ? (
              <option>No certificates available</option>
            ) : (
              certificates.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.original_filename} ({c.id.slice(0, 8)})
                </option>
              ))
            )}
          </select>
        </div>
      </div>

      {/* Main Report Preview Layout */}
      {!selectedCert ? (
        <Card className="p-10">
          <EmptyState
            icon={<FileQuestion size={36} className="text-slate-400" />}
            title="No Certificate Selected"
            description="Please upload or choose a certificate from the dropdown above."
            action={
              <Link href="/dashboard/upload">
                <Button variant="primary" size="sm">
                  Upload Certificate
                </Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Report Document Card (8 cols) */}
          <Card className="lg:col-span-8">
            <CardHeader className="flex flex-row items-center justify-between pb-4 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-indigo-50 text-indigo-600 rounded-lg">
                  <FileText size={24} />
                </div>
                <div>
                  <span className="font-mono text-[10px] text-emerald-700 uppercase font-bold tracking-wider">
                    OFFICIAL REPORT PREVIEW
                  </span>
                  <CardTitle className="text-base font-bold text-slate-900">
                    {selectedCert.original_filename}
                  </CardTitle>
                </div>
              </div>

              {/* Status Badge */}
              {report ? (
                <Badge variant="genuine" size="sm">
                  <CheckCircle2 size={12} className="mr-1" />
                  REPORT GENERATED
                </Badge>
              ) : (
                <Badge variant="suspicious" size="sm">
                  <AlertTriangle size={12} className="mr-1" />
                  NOT GENERATED YET
                </Badge>
              )}
            </CardHeader>

            <CardContent className="p-6 space-y-6">
              {/* Certificate Metadata */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 font-mono text-xs">
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-[10px] text-slate-400 block font-semibold">CERTIFICATE ID</span>
                  <span className="font-bold text-slate-900">{selectedCert.id.slice(0, 12)}…</span>
                </div>
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-[10px] text-slate-400 block font-semibold">FILE FORMAT</span>
                  <span className="font-bold text-indigo-700 uppercase">{selectedCert.file_type}</span>
                </div>
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-[10px] text-slate-400 block font-semibold">UPLOADED AT</span>
                  <span className="text-slate-600">{new Date(selectedCert.uploaded_at).toLocaleDateString()}</span>
                </div>
              </div>

              {/* Cryptographic SHA-256 Hash */}
              <div className="space-y-1.5 font-mono text-xs">
                <div className="flex items-center justify-between text-[11px] text-slate-500 font-sans">
                  <span className="font-semibold uppercase">SHA-256 INTEGRITY FINGERPRINT</span>
                  <button
                    onClick={() => handleCopyHash(selectedCert.sha256_hash)}
                    className="text-indigo-600 hover:underline flex items-center gap-1"
                  >
                    {copiedHash ? <Check size={11} /> : <Copy size={11} />}
                    {copiedHash ? "Copied" : "Copy Hash"}
                  </button>
                </div>
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-indigo-900 break-all">
                  {selectedCert.sha256_hash}
                </div>
              </div>

              {/* Verification Pipeline Outcomes Summary */}
              <div className="space-y-3 pt-2">
                <h3 className="text-xs font-mono uppercase text-slate-500 font-bold">
                  Verification Pipeline Telemetry
                </h3>
                {verification ? (
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 font-mono text-xs">
                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                      <span className="text-[10px] text-slate-400 block font-semibold">QR VERIFICATION</span>
                      <span className={`font-bold ${verification.qr_valid ? "text-emerald-700" : "text-amber-700"}`}>
                        {verification.qr_present ? (verification.qr_valid ? "VERIFIED" : "INVALID") : "NO QR"}
                      </span>
                    </div>

                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                      <span className="text-[10px] text-slate-400 block font-semibold">BLOCKCHAIN MATCH</span>
                      <span className={`font-bold ${verification.blockchain_match ? "text-emerald-700" : "text-slate-500"}`}>
                        {verification.blockchain_status || "NOT REGISTERED"}
                      </span>
                    </div>

                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                      <span className="text-[10px] text-slate-400 block font-semibold">TAMPERING SCAN</span>
                      <span className={`font-bold ${
                        verification.tampering_status === "not_applicable_for_pdf_text_layer"
                          ? "text-amber-700"
                          : verification.tampering_status?.startsWith("failed:")
                          ? "text-rose-700"
                          : verification.tampering_score && verification.tampering_score > 30
                          ? "text-rose-700"
                          : "text-emerald-700"
                      }`}>
                        {verification.tampering_status === "not_applicable_for_pdf_text_layer"
                          ? "NOT APPLICABLE"
                          : verification.tampering_status?.startsWith("failed:")
                          ? "FAILED"
                          : verification.tampering_status?.startsWith("skipped:")
                          ? "SKIPPED"
                          : verification.tampering_score !== undefined && verification.tampering_score !== null
                          ? `${verification.tampering_score} / 100`
                          : "PENDING"}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-500">
                    Verification outcome telemetry will populate after pipeline run.
                  </div>
                )}
              </div>

              {/* Report Digital Signature & Verification Box */}
              {report && (
                <div className="p-4 bg-emerald-50/50 border border-emerald-200 rounded-xl space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-mono font-bold text-emerald-800">
                      <Lock size={14} />
                      <span>DETACHED HMAC-SHA256 DIGITAL SIGNATURE</span>
                    </div>
                    <button
                      onClick={() => handleCopySig(report.digital_signature)}
                      className="text-xs text-emerald-700 hover:underline flex items-center gap-1 font-mono"
                    >
                      {copiedSig ? <Check size={11} /> : <Copy size={11} />}
                      {copiedSig ? "Copied" : "Copy Signature"}
                    </button>
                  </div>
                  <p className="font-mono text-[11px] text-emerald-900 break-all bg-white p-2.5 rounded border border-emerald-200">
                    {report.digital_signature || "N/A"}
                  </p>
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[11px] font-mono text-slate-500">
                    <span>Generated: {new Date(report.generated_at).toLocaleString()}</span>
                    <span>Ref ID: <b>{report.verification_id}</b></span>
                  </div>

                  {/* Real-time signature verification result */}
                  {sigStatus && sigStatus.certId === selectedCert.id && (
                    <div className={`mt-2 p-3 rounded-lg border text-xs flex items-center gap-2 font-mono ${
                      sigStatus.isValid
                        ? "bg-emerald-100/70 border-emerald-300 text-emerald-900"
                        : "bg-rose-100/70 border-rose-300 text-rose-900"
                    }`}>
                      {sigStatus.isValid ? <CheckCircle size={16} className="text-emerald-600 shrink-0" /> : <XCircle size={16} className="text-rose-600 shrink-0" />}
                      <span>{sigStatus.detail}</span>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Right Column: Actions Panel (4 cols) */}
          <Card className="lg:col-span-4 h-fit">
            <CardHeader className="pb-3 border-b border-slate-100">
              <CardTitle className="text-sm font-semibold text-slate-900">
                Report Generation & Integrity
              </CardTitle>
            </CardHeader>

            <CardContent className="p-5 space-y-4 text-xs text-slate-600">
              <p className="leading-relaxed">
                Verification reports compile all OCR extractions, tamper ELA heatmaps, blockchain logs, trust scores, and AI predictions into a sealed PDF dossier.
              </p>

              {generating ? (
                <div className="p-4 bg-indigo-50 border border-indigo-200 rounded-lg space-y-2 text-center">
                  <RefreshCw size={20} className="animate-spin text-indigo-600 mx-auto" />
                  <p className="font-semibold text-indigo-900 text-xs">Generating Report</p>
                  <p className="text-[11px] text-indigo-700 font-mono">{generationStep}</p>
                </div>
              ) : report ? (
                <div className="space-y-2">
                  <Button
                    onClick={() => handleDownloadReport(selectedCert.id)}
                    disabled={downloadingCertId === selectedCert.id}
                    loading={downloadingCertId === selectedCert.id}
                    variant="primary"
                    size="md"
                    icon={<Download size={15} />}
                    className="w-full bg-emerald-600 hover:bg-emerald-700 shadow-sm"
                  >
                    Download Signed PDF Report
                  </Button>

                  <Button
                    onClick={() => handleViewReport(selectedCert.id)}
                    variant="secondary"
                    size="sm"
                    icon={<ExternalLink size={14} />}
                    className="w-full text-xs"
                  >
                    View Report in Browser
                  </Button>

                  <Button
                    onClick={() => handleVerifySignature(selectedCert.id)}
                    disabled={verifyingCertId === selectedCert.id}
                    loading={verifyingCertId === selectedCert.id}
                    variant="secondary"
                    size="sm"
                    icon={<ShieldCheck size={14} className="text-indigo-600" />}
                    className="w-full text-xs"
                  >
                    Verify Cryptographic Signature
                  </Button>

                  <Button
                    onClick={handleGenerateReport}
                    disabled={generating}
                    variant="ghost"
                    size="sm"
                    icon={<RefreshCw size={12} />}
                    className="w-full text-xs text-slate-500"
                  >
                    Re-Generate Report (New Version)
                  </Button>
                </div>
              ) : (
                <Button
                  onClick={handleGenerateReport}
                  disabled={generating}
                  loading={generating}
                  variant="primary"
                  size="md"
                  icon={<Sparkles size={15} />}
                  className="w-full shadow-sm"
                >
                  Generate PDF Report
                </Button>
              )}

              <Link href={`/dashboard/certificates/${selectedCert.id}`}>
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<ExternalLink size={13} />}
                  className="w-full mt-2"
                >
                  Inspect in Forensic Cockpit
                </Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Bottom Section: All Generated Reports Table */}
      <Card>
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
              <FileText size={18} className="text-indigo-600" />
              Generated Verification Reports
            </CardTitle>
            <CardDescription className="text-xs text-slate-500 mt-0.5">
              Repository of all official verification reports generated within your tenant organization.
            </CardDescription>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative w-64">
              <Search size={14} className="absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search by ID, file, verdict..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-white border border-slate-200 rounded-lg focus:outline-none focus:border-indigo-600 font-mono"
              />
            </div>
            <Button
              onClick={fetchReportsList}
              variant="secondary"
              size="sm"
              icon={<RefreshCw size={13} />}
            >
              Refresh
            </Button>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {loadingList ? (
            <div className="p-8 text-center text-xs text-slate-400">Loading generated reports...</div>
          ) : filteredReports.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400">
              {searchFilter ? "No reports match your filter." : "No reports have been generated yet."}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-mono text-[11px] uppercase tracking-wider">
                    <th className="py-3 px-4">Verification ID</th>
                    <th className="py-3 px-4">Certificate Name</th>
                    <th className="py-3 px-4">Generated At</th>
                    <th className="py-3 px-4">Verdict / Trust</th>
                    <th className="py-3 px-4">Digital Signature</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono">
                  {filteredReports.map((item) => (
                    <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 px-4">
                        <span className="font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded text-[11px]">
                          {item.verification_id}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-slate-900 font-medium font-sans block">
                          {item.certificate_filename}
                        </span>
                        <span className="text-[10px] text-slate-400 uppercase">
                          {item.file_type} • {item.sha256_hash.slice(0, 10)}…
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-600 text-[11px]">
                        {new Date(item.generated_at).toLocaleString()}
                      </td>
                      <td className="py-3 px-4 font-sans">
                        <div className="flex items-center gap-1.5">
                          {item.prediction_label ? (
                            <Badge
                              variant={
                                item.prediction_label === "genuine"
                                  ? "genuine"
                                  : item.prediction_label === "suspicious"
                                  ? "suspicious"
                                  : "fake"
                              }
                              size="sm"
                            >
                              {item.prediction_label.toUpperCase()}
                            </Badge>
                          ) : (
                            <span className="text-slate-400 text-xs">—</span>
                          )}
                          {item.trust_score !== undefined && item.trust_score !== null && (
                            <span className="text-[11px] text-slate-500 font-mono">
                              ({Math.round(item.trust_score)}/100)
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-slate-500 text-[10px]">
                        <span title={item.digital_signature || ""}>
                          {item.digital_signature ? `${item.digital_signature.slice(0, 16)}…` : "—"}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5 font-sans">
                          <Button
                            onClick={() => handleVerifySignature(item.certificate_id)}
                            disabled={verifyingCertId === item.certificate_id}
                            variant="ghost"
                            size="sm"
                            title="Verify Cryptographic Signature"
                            className="text-indigo-600 hover:text-indigo-800"
                          >
                            <ShieldCheck size={14} />
                          </Button>
                          <Button
                            onClick={() => handleDownloadReport(item.certificate_id)}
                            disabled={downloadingCertId === item.certificate_id}
                            loading={downloadingCertId === item.certificate_id}
                            variant="secondary"
                            size="sm"
                            icon={<Download size={13} />}
                          >
                            Download
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
