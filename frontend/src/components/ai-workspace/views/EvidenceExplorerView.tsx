"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import {
  Eye,
  Sparkles,
  Loader2,
  AlertTriangle,
  RefreshCw,
  Play,
  CheckCircle2,
  ShieldAlert,
  History,
  XCircle,
  FileCheck,
} from 'lucide-react';
import {
  evidenceApi,
  jobsApi,
  verificationApi,
  EvidenceItemResponse,
  getAccessToken,
} from '../../../lib/api';

export const EvidenceExplorerView: React.FC = () => {
  const {
    currentCertificateId,
    activeEvidenceId,
    setActiveEvidenceId,
    setActiveView,
    sendMessage,
  } = useAIWorkspace();

  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [selectedJobId, setSelectedJobId] = useState<string>('all');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<{ code: number | string; message: string } | null>(null);

  const [evidenceItems, setEvidenceItems] = useState<EvidenceItemResponse[]>([]);
  const [jobRuns, setJobRuns] = useState<Array<{ id: string; status: string; current_stage: string; progress_percentage: number; created_at: string }>>([]);
  const [isVerifyingNow, setIsVerifyingNow] = useState<boolean>(false);
  const [jobStatus, setJobStatus] = useState<string | null>(null);

  const fetchEvidenceAndJobs = useCallback(async () => {
    if (!currentCertificateId) {
      setEvidenceItems([]);
      setJobRuns([]);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // 1. Fetch Job Runs History for run selection dropdown
      const jobsRes = await evidenceApi.getJobs(currentCertificateId);
      const jobsData = jobsRes.data || [];
      setJobRuns(jobsData);

      // Check if there is an active running job
      const latestJob = jobsData[0];
      if (latestJob && ['QUEUED', 'PROCESSING'].includes(latestJob.status)) {
        setJobStatus('PROCESSING');
      } else if (latestJob && latestJob.status === 'FAILED') {
        setJobStatus('FAILED');
      } else {
        setJobStatus(null);
      }

      // 2. Build filter params for backend Evidence API
      const params: { evidence_type?: string; verification_job_id?: string; page_size: number } = { page_size: 100 };
      if (activeCategory !== 'all') {
        params.evidence_type = activeCategory.toUpperCase();
      }
      if (selectedJobId !== 'all') {
        params.verification_job_id = selectedJobId;
      }

      const evRes = await evidenceApi.getEvidence(currentCertificateId, params);
      setEvidenceItems(evRes.data.items || []);

    } catch (err: any) {
      console.error("Failed to load backend evidence:", err);
      const statusCode = err?.response?.status;
      const detailMsg = err?.response?.data?.detail;

      if (statusCode === 404) {
        setError({
          code: 404,
          message: typeof detailMsg === 'string' ? detailMsg : `Certificate "${currentCertificateId}" was not found or access is unauthorized.`,
        });
      } else if (statusCode === 401 && !getAccessToken()) {
        setError({
          code: 401,
          message: "Session expired or unauthorized. Please log in again.",
        });
      } else {
        setError({
          code: statusCode || 'NETWORK_ERROR',
          message: typeof detailMsg === 'string' ? detailMsg : (err?.message || "Unable to retrieve evidence from backend."),
        });
      }
    } finally {
      setLoading(false);
    }
  }, [currentCertificateId, activeCategory, selectedJobId]);

  useEffect(() => {
    if (currentCertificateId) {
      fetchEvidenceAndJobs();
    } else {
      setLoading(false);
    }
  }, [currentCertificateId, fetchEvidenceAndJobs]);

  const fetchEvidenceData = () => {
    fetchEvidenceAndJobs();
  };

  const handleRunVerification = async () => {
    if (!currentCertificateId) return;
    setIsVerifyingNow(true);
    setError(null);
    try {
      // Start async job or sync verification
      await verificationApi.verifyAll(currentCertificateId);
      await fetchEvidenceAndJobs();
    } catch (err: any) {
      console.error("Verification execution failed:", err);
      setError({
        code: 'VERIFY_FAILED',
        message: err?.response?.data?.detail || err?.message || "Verification check execution failed.",
      });
    } finally {
      setIsVerifyingNow(false);
    }
  };

  const categories = [
    { id: 'all', label: 'All Evidence' },
    { id: 'ocr', label: 'OCR Evidence' },
    { id: 'qr', label: 'QR Evidence' },
    { id: 'blockchain', label: 'Blockchain' },
    { id: 'tamper', label: 'Tamper Analysis' },
    { id: 'structure', label: 'Structure' },
    { id: 'metadata', label: 'Metadata' },
  ];

  const getResultBadgeConfig = (result: string) => {
    const res = (result || '').toUpperCase();
    if (['PASS', 'VERIFIED', 'CLEAN', 'LOW_RISK'].includes(res)) {
      return {
        bg: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        icon: CheckCircle2,
      };
    }
    if (['WARN', 'NOT_FOUND', 'MEDIUM_RISK', 'UNAVAILABLE'].includes(res)) {
      return {
        bg: 'bg-amber-50 text-amber-700 border-amber-200',
        icon: AlertTriangle,
      };
    }
    return {
      bg: 'bg-rose-50 text-rose-700 border-rose-200',
      icon: XCircle,
    };
  };

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex flex-col overflow-y-auto p-8 space-y-6 font-sans select-none max-w-4xl mx-auto">
      {/* Header & Verification Job Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <FileCheck className="text-indigo-600" size={22} />
            Verification Evidence Explorer
          </h1>
          <p className="text-xs text-slate-500 font-medium mt-0.5">
            Traceable, immutable empirical evidence generated across verification runs.
          </p>
        </div>

        {/* Historical Verification Job Selector */}
        {jobRuns.length > 0 && (
          <div className="flex items-center gap-2 shrink-0 bg-white border border-slate-200 rounded-xl px-3 py-1.5 shadow-2xs">
            <History size={14} className="text-slate-400" />
            <span className="text-xs font-semibold text-slate-600">Run:</span>
            <select
              value={selectedJobId}
              onChange={(e) => setSelectedJobId(e.target.value)}
              className="text-xs font-mono font-medium text-indigo-700 bg-transparent focus:outline-none cursor-pointer"
            >
              <option value="all">All Runs ({jobRuns.length})</option>
              {jobRuns.map((job, idx) => (
                <option key={job.id} value={job.id}>
                  Run #{jobRuns.length - idx} ({new Date(job.created_at).toLocaleTimeString()}) — {job.status}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Category Filter Pills */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-3">
        {categories.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setActiveCategory(cat.id)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium transition cursor-pointer ${
              activeCategory === cat.id
                ? 'bg-indigo-600 text-white shadow-2xs font-semibold'
                : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-100'
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* ── Error State ── */}
      {error && (
        <div className="p-5 bg-rose-50 border border-rose-200 rounded-2xl space-y-3">
          <div className="flex items-start gap-3">
            <AlertTriangle className="text-rose-600 shrink-0 mt-0.5" size={20} />
            <div className="space-y-1">
              <h3 className="text-sm font-bold text-rose-900">Evidence Unavailable</h3>
              <p className="text-xs text-rose-700 leading-relaxed">{error.message}</p>
            </div>
          </div>
          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={fetchEvidenceData}
              className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg font-medium text-xs flex items-center gap-1.5 transition cursor-pointer"
            >
              <RefreshCw size={14} />
              <span>Retry Request</span>
            </button>
            <button
              onClick={() => setActiveView('cockpit')}
              className="px-3 py-1.5 bg-white border border-rose-200 text-rose-800 hover:bg-rose-100 rounded-lg font-medium text-xs transition cursor-pointer"
            >
              Back to Cockpit
            </button>
          </div>
        </div>
      )}

      {/* ── Verification Processing Banner ── */}
      {jobStatus === 'PROCESSING' && !error && (
        <div className="p-4 bg-indigo-50 border border-indigo-200 rounded-2xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Loader2 className="text-indigo-600 animate-spin shrink-0" size={20} />
            <div>
              <p className="text-xs font-bold text-indigo-900">Verification in progress</p>
              <p className="text-xs text-indigo-700">Verification in progress. Evidence will appear as pipeline stages complete.</p>
            </div>
          </div>
          <button
            onClick={fetchEvidenceData}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl text-xs flex items-center gap-1 shrink-0 transition cursor-pointer"
          >
            <RefreshCw size={12} />
            <span>Refresh</span>
          </button>
        </div>
      )}

      {/* ── Verification Failed Banner ── */}
      {jobStatus === 'FAILED' && !error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-2xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <XCircle className="text-rose-600 shrink-0" size={20} />
            <div>
              <p className="text-xs font-bold text-rose-900">Evidence unavailable because verification failed</p>
              <p className="text-xs text-rose-700">The previous pipeline run encountered an error. Click below to retry verification.</p>
            </div>
          </div>
          <button
            onClick={handleRunVerification}
            disabled={isVerifyingNow}
            className="px-3.5 py-1.5 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white font-semibold rounded-xl text-xs flex items-center gap-1.5 shrink-0 transition cursor-pointer"
          >
            {isVerifyingNow ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            <span>Retry Run</span>
          </button>
        </div>
      )}

      {/* ── Pending Verification Action Banner ── */}
      {!currentCertificateId && (
        <div className="p-8 bg-white border border-slate-200 rounded-2xl text-center space-y-2 text-xs text-slate-500">
          <p className="font-bold text-slate-700 text-sm">No Active Document Selected</p>
          <p>Select or upload a certificate in the workspace to inspect its backend evidence provenance.</p>
        </div>
      )}

      {currentCertificateId && evidenceItems.length === 0 && !loading && !error && !jobStatus && (
        <div className="p-8 bg-amber-50 border border-amber-200 rounded-2xl flex flex-col items-center text-center space-y-3">
          <ShieldAlert className="text-amber-600" size={32} />
          <div>
            <p className="font-bold text-amber-900 text-sm">No verification evidence is available yet.</p>
            <p className="text-xs text-amber-700 max-w-md mt-1">
              Run the full AI verification pipeline to generate standardized evidence items for OCR, QR, Blockchain, Tampering, Duplicate, Fraud, and Trust Score.
            </p>
          </div>
          <button
            onClick={handleRunVerification}
            disabled={isVerifyingNow}
            className="mt-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-bold rounded-xl text-xs flex items-center gap-2 transition cursor-pointer"
          >
            {isVerifyingNow ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            <span>{isVerifyingNow ? 'Running Pipeline...' : 'Run Verification Now'}</span>
          </button>
        </div>
      )}

      {/* ── Loading State ── */}
      {loading ? (
        <div className="p-10 bg-white border border-slate-200 rounded-2xl text-center space-y-2 text-xs text-slate-500 flex flex-col items-center">
          <Loader2 size={32} className="animate-spin text-indigo-600 mb-2" />
          <p className="font-bold text-slate-700 text-sm">Retrieving Backend Evidence...</p>
          <p>Querying standardized evidence items from database for {currentCertificateId}.</p>
        </div>
      ) : !error && evidenceItems.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-slate-500 font-medium px-1">
            <span>Showing {evidenceItems.length} evidence items</span>
            <span>Document Hash: <code className="font-mono text-[11px] text-slate-700">{evidenceItems[0]?.document_hash.substring(0, 16)}...</code></span>
          </div>

          {evidenceItems.map((ev) => {
            const isSelected = String(activeEvidenceId) === String(ev.id);
            const badgeCfg = getResultBadgeConfig(ev.result);
            const BadgeIcon = badgeCfg.icon;
            const confPct = Math.round((ev.confidence > 1 ? ev.confidence / 100 : ev.confidence) * 100);

            return (
              <div
                key={ev.id}
                onClick={() => setActiveEvidenceId(ev.id as any)}
                className={`p-5 rounded-2xl border transition shadow-2xs space-y-3 cursor-pointer ${
                  isSelected
                    ? 'bg-white border-indigo-500 ring-2 ring-indigo-100'
                    : 'bg-white border-slate-200 hover:border-slate-300'
                }`}
              >
                {/* Item Top Bar */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded bg-indigo-100 text-indigo-700 font-mono text-xs font-bold">
                      [{ev.evidence_type}]
                    </span>
                    <h3 className="font-bold text-slate-900 text-sm">{ev.source}</h3>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className={`flex items-center gap-1 text-xs font-bold px-2.5 py-0.5 rounded-full border ${badgeCfg.bg}`}>
                      <BadgeIcon size={12} />
                      <span>{ev.result}</span>
                    </span>
                    <span className="font-mono text-xs font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                      {confPct}% Confidence
                    </span>
                  </div>
                </div>

                {/* Explanation text */}
                <p className="text-xs text-slate-700 leading-relaxed font-mono bg-slate-50 p-3.5 rounded-xl border border-slate-100">
                  "{ev.explanation}"
                </p>

                {/* Metadata & Actions */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-1 text-xs text-slate-400">
                  <div className="flex flex-wrap items-center gap-3">
                    <span>Engine: <strong className="text-slate-600 font-normal">{ev.algorithm_engine}</strong></span>
                    <span>•</span>
                    <span>Stage: <strong className="text-slate-600 font-normal">{ev.stage}</strong></span>
                    <span>•</span>
                    <span>Time: <strong className="text-slate-600 font-normal">{new Date(ev.timestamp).toLocaleTimeString()}</strong></span>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setActiveView('cockpit');
                      }}
                      className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-medium text-xs flex items-center gap-1 transition cursor-pointer"
                    >
                      <Eye size={12} />
                      <span>View on Canvas</span>
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setActiveView('chat');
                        sendMessage(`Explain evidence item [${ev.evidence_type}] (${ev.source}) in detail: "${ev.explanation}"`);
                      }}
                      className="px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium text-xs flex items-center gap-1 transition cursor-pointer"
                    >
                      <Sparkles size={12} />
                      <span>Ask AI</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
