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
} from "lucide-react";
import {
  certificateApi,
  reportApi,
  verificationApi,
  getAccessToken,
  CertificateResponse,
  VerificationReportResponse,
  VerificationResultResponse,
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
  const [copiedHash, setCopiedHash] = useState(false);

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
  }, [router]);

  useEffect(() => {
    if (!selectedCertId) return;

    setLoadingReport(true);
    setReport(null);
    setVerification(null);

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
    try {
      const { data } = await reportApi.generate(selectedCertId);
      setReport(data);
    } catch {
      alert("Failed to generate verification report.");
    } finally {
      setGenerating(false);
    }
  };

  const handleDownloadReport = () => {
    if (!selectedCertId) return;
    const url = reportApi.downloadUrl(selectedCertId);
    const token = getAccessToken();
    const directUrl = token ? `${url}?token=${encodeURIComponent(token)}` : url;
    window.open(directUrl, "_blank");
  };

  const selectedCert = certificates.find((c) => c.id === selectedCertId);

  const handleCopyHash = (hash?: string) => {
    if (!hash) return;
    navigator.clipboard.writeText(hash);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 2000);
  };

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
            <span className="text-indigo-600 font-semibold">Verification Reports</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2 tracking-tight">
            <FileText size={22} className="text-indigo-600" />
            Official Verification Reports & Audit Certificates
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Generate and download cryptographically signed verification reports with SHA-256 integrity proofs.
          </p>
        </div>

        {/* Certificate Selector Dropdown */}
        <div className="w-64 shrink-0">
          <label className="text-[11px] font-semibold text-slate-500 uppercase block mb-1">
            Select Certificate
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
                  Verification Pipeline Outcomes
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

              {/* Report Digital Signature (if generated) */}
              {report && (
                <div className="p-4 bg-emerald-50/50 border border-emerald-200 rounded-xl space-y-2">
                  <div className="flex items-center gap-2 text-xs font-mono font-bold text-emerald-800">
                    <Lock size={14} />
                    <span>DIGITAL SIGNATURE & AUDIT REF</span>
                  </div>
                  <p className="font-mono text-[11px] text-emerald-900 break-all">
                    Sig: {report.digital_signature || `CERTIVERIFY-SIG-${report.id.slice(0, 16)}`}
                  </p>
                  <div className="text-[11px] font-mono text-slate-500">
                    Generated: {new Date(report.generated_at).toLocaleString()}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Right Column: Actions Panel (4 cols) */}
          <Card className="lg:col-span-4 h-fit">
            <CardHeader className="pb-3 border-b border-slate-100">
              <CardTitle className="text-sm font-semibold text-slate-900">
                Report Generation & Actions
              </CardTitle>
            </CardHeader>

            <CardContent className="p-5 space-y-4 text-xs text-slate-600">
              <p className="leading-relaxed">
                Verification reports compile all OCR field extractions, tamper ELA heatmaps, blockchain logs, and AI predictions into an official signed PDF dossier.
              </p>

              {report ? (
                <Button
                  onClick={handleDownloadReport}
                  variant="primary"
                  size="md"
                  icon={<Download size={15} />}
                  className="w-full bg-emerald-600 hover:bg-emerald-700 shadow-sm"
                >
                  Download Signed PDF Report
                </Button>
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
                  {generating ? "Generating..." : "Generate PDF Report"}
                </Button>
              )}

              {report && (
                <Button
                  onClick={handleGenerateReport}
                  disabled={generating}
                  loading={generating}
                  variant="ghost"
                  size="sm"
                  icon={<RefreshCw size={12} />}
                  className="w-full text-xs"
                >
                  Re-Generate Report
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
    </div>
  );
}
