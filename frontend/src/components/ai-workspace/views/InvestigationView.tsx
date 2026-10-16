"use client";

import React, { useEffect, useState, useMemo } from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import { SearchCode, AlertTriangle, CheckCircle2, Sparkles, ArrowRight, ShieldCheck, FileText, Loader2 } from 'lucide-react';
import { verificationApi, certificateApi, VerificationResultResponse } from '../../../lib/api';

export const InvestigationView: React.FC = () => {
  const { currentCertificateId, setActiveView, sendMessage, executeAction, activeArtifact, activeConversation } = useAIWorkspace();

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [tamperingData, setTamperingData] = useState<VerificationResultResponse | null>(null);
  const [certFileName, setCertFileName] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    if (!currentCertificateId) {
      setTamperingData(null);
      setError(null);
      setLoading(false);
      setCertFileName(null);
      return;
    }

    async function fetchInvestigation() {
      if (!currentCertificateId) return;
      setLoading(true);
      setError(null);
      try {
        certificateApi.get(currentCertificateId).then(res => {
          if (isMounted && res.data) setCertFileName(res.data.original_filename);
        }).catch(() => {});

        let res;
        try {
          res = await verificationApi.verifyTampering(currentCertificateId);
        } catch (tampErr) {
          res = await verificationApi.get(currentCertificateId);
        }

        if (isMounted) {
          if (res && res.data) {
            setTamperingData(res.data);
          } else {
            setError("Unable to retrieve forensic analysis for current document.");
          }
        }
      } catch (err: any) {
        if (isMounted) {
          console.error("Forensic analysis error:", err);
          const msg = err.response?.data?.detail || err.message || "Failed to execute tampering investigation.";
          setError(msg);
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchInvestigation();

    return () => {
      isMounted = false;
    };
  }, [currentCertificateId]);

  const findingsList = useMemo(() => {
    if (!currentCertificateId || !tamperingData) {
      if (activeArtifact?.findings && activeArtifact.findings.length > 0) {
        return activeArtifact.findings.map((f, idx) => ({
          title: `Finding #${idx + 1}: ${f}`,
          severity: activeArtifact.verdict === 'fake' ? 'high' : activeArtifact.verdict === 'suspicious' ? 'medium' : 'low',
          snippet: f
        }));
      }
      return [];
    }

    const items: Array<{ title: string; severity: 'high' | 'medium' | 'low'; snippet: string }> = [];
    const detail = tamperingData.tampering_detail || {};
    const score = tamperingData.tampering_score ?? 0;
    const flags = tamperingData.tampering_flags || [];

    if (detail.ela) {
      const elaScore = detail.ela.score ?? 0;
      const elaStatus = detail.ela.status || "NORMAL";
      items.push({
        title: `Finding #${items.length + 1}: Error Level Analysis (ELA)`,
        severity: elaScore > 40 || elaStatus === "POSSIBLE_MANIPULATION" ? "high" : elaScore > 20 ? "medium" : "low",
        snippet: `ELA compression variance score: ${elaScore.toFixed(1)}/100. Status: ${elaStatus}. ${elaScore > 30 ? "Elevated compression difference detected indicating potential digital editing." : "Compression distribution is uniform across document."}`
      });
    }

    if (detail.image_quality) {
      const iqScore = detail.image_quality.score ?? 100;
      items.push({
        title: `Finding #${items.length + 1}: Image Quality & Noise Profile`,
        severity: iqScore < 30 ? "high" : iqScore < 60 ? "medium" : "low",
        snippet: `Quality Score: ${iqScore.toFixed(0)}/100. ${detail.image_quality.detail || "Resolution and noise profile evaluated for forensic clarity."}`
      });
    }

    if (detail.metadata) {
      const anomalies = detail.metadata.anomalies || [];
      items.push({
        title: `Finding #${items.length + 1}: Metadata & PDF Structure`,
        severity: anomalies.length > 0 ? "high" : "low",
        snippet: anomalies.length > 0 ? `Anomalies detected: ${anomalies.join("; ")}` : "No editing software tags or metadata anomalies detected in document header."
      });
    }

    if (detail.copy_paste) {
      const count = detail.copy_paste.clone_regions_count || 0;
      items.push({
        title: `Finding #${items.length + 1}: Copy-Paste & Duplicate Region Check`,
        severity: count > 0 ? "high" : "low",
        snippet: count > 0 ? `Detected ${count} duplicate/cloned pixel region(s) in document.` : "No duplicated or cloned pixel patches detected."
      });
    }

    if (detail.font_consistency) {
      const fontStatus = detail.font_consistency.status || "CONSISTENT";
      items.push({
        title: `Finding #${items.length + 1}: Typography & Font Consistency`,
        severity: fontStatus === "INCONSISTENT" ? "high" : fontStatus === "WARNING" ? "medium" : "low",
        snippet: detail.font_consistency.detail || `Typography check status: ${fontStatus}`
      });
    }

    if (detail.text_analysis) {
      const alignScore = detail.text_analysis.alignment_score ?? 100;
      items.push({
        title: `Finding #${items.length + 1}: Text Alignment & Baseline Check`,
        severity: alignScore < 50 ? "high" : alignScore < 80 ? "medium" : "low",
        snippet: detail.text_analysis.detail || `Baseline alignment score: ${alignScore.toFixed(0)}/100`
      });
    }

    if (detail.signature || detail.seal) {
      const sig = detail.signature?.detected ? "Signature detected" : "No signature detected";
      const seal = detail.seal?.detected ? "Security seal detected" : "No security seal detected";
      items.push({
        title: `Finding #${items.length + 1}: Document Stamp & Signature Signals`,
        severity: "low",
        snippet: `${sig}. ${seal}.`
      });
    }

    flags.forEach(flag => {
      if (!items.some(it => it.snippet.includes(flag))) {
        items.push({
          title: `Finding #${items.length + 1}: Specific Forensic Flag`,
          severity: score > 60 ? "high" : score > 30 ? "medium" : "low",
          snippet: flag
        });
      }
    });

    return items;
  }, [currentCertificateId, tamperingData, activeArtifact]);

  const verdict = useMemo(() => {
    if (!tamperingData) return activeArtifact?.verdict || 'genuine';
    const score = tamperingData.tampering_score ?? 0;
    const risk = tamperingData.tampering_risk_level || '';
    if (score >= 60 || risk.includes('HIGH')) return 'fake';
    if (score >= 30 || risk.includes('MODERATE') || risk.includes('MINOR')) return 'suspicious';
    return 'genuine';
  }, [tamperingData, activeArtifact]);

  const summaryText = useMemo(() => {
    if (error) {
      return `Forensic Analysis Error: ${error}`;
    }
    if (loading) {
      return "Executing forensic algorithms (ELA, copy-paste clone detection, metadata analysis, font consistency)...";
    }
    if (tamperingData) {
      const score = Math.round(tamperingData.tampering_score ?? 0);
      const risk = tamperingData.tampering_risk_level || 'LOW';
      const conf = tamperingData.tampering_confidence ?? 90;
      const flagsCount = (tamperingData.tampering_flags || []).length;

      return `Overall Forensic Risk Level: ${risk} | Tampering Score: ${score}/100 | Confidence: ${conf}%. ${
        flagsCount > 0
          ? `${flagsCount} forensic flag(s) identified during multi-signal scanning.`
          : 'All forensic checks (ELA, metadata, typography, and clone analysis) passed within normal limits.'
      }`;
    }
    return activeArtifact?.summaryText || "No active document under investigation. Upload a document to analyze forensic findings.";
  }, [error, loading, tamperingData, activeArtifact]);

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex flex-col overflow-y-auto p-8 space-y-6 font-sans select-none max-w-4xl mx-auto">
      <div>
        <div className="flex items-center gap-2">
          <SearchCode size={20} className="text-indigo-600" />
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">AI Investigation Report</h1>
        </div>
        <p className="text-xs text-slate-500 font-medium">
          {currentCertificateId ? `Investigating document: ${certFileName || activeArtifact?.degreeTitle || 'Document'} (${currentCertificateId})` : "Investigating document for potential forgery, alteration, or checksum anomalies."}
        </p>
      </div>

      {loading ? (
        <div className="p-6 bg-white border border-slate-200 rounded-2xl text-center space-y-2 text-xs text-slate-500 flex flex-col items-center">
          <Loader2 size={32} className="animate-spin text-indigo-600 mb-2" />
          <p className="font-bold text-slate-700 text-sm">Analyzing Forensic Evidence...</p>
          <p>Running ELA, metadata, clone detection, and typography checks for {currentCertificateId}.</p>
        </div>
      ) : currentCertificateId ? (
        <div className={`p-4 rounded-2xl border text-xs space-y-2 ${
          verdict === 'fake' ? 'bg-rose-50 border-rose-200 text-rose-900' :
          verdict === 'suspicious' ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-emerald-50 border-emerald-200 text-emerald-900'
        }`}>
          <div className="flex items-center gap-2 font-bold text-sm">
            {verdict === 'genuine' ? <CheckCircle2 size={16} className="text-emerald-600" /> : <AlertTriangle size={16} className="text-amber-600" />}
            <span>Investigation Summary: {findingsList.length} Forensic Signals Analyzed</span>
          </div>
          <p className="leading-relaxed font-normal">{summaryText}</p>
        </div>
      ) : (
        <div className="p-6 bg-white border border-slate-200 rounded-2xl text-center space-y-2 text-xs text-slate-500">
          <FileText size={32} className="mx-auto text-slate-300" />
          <p className="font-bold text-slate-700 text-sm">No Document Uploaded</p>
          <p>Upload a document in the workspace to view forensic investigation findings.</p>
        </div>
      )}

      <div className="space-y-4">
        {findingsList.map((f, idx) => (
          <div key={idx} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900 text-xs">{f.title}</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                f.severity === 'high' ? 'bg-rose-100 text-rose-800' :
                f.severity === 'medium' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'
              }`}>
                {f.severity} Risk
              </span>
            </div>
            <p className="text-slate-600 leading-relaxed font-mono bg-slate-50 p-3 rounded-xl border border-slate-100">
              {f.snippet}
            </p>
          </div>
        ))}
      </div>

      {currentCertificateId && (
        <div className="flex flex-wrap items-center gap-3 pt-2">
          <button
            onClick={() => {
              setActiveView('chat');
              sendMessage("Investigate these findings deeper and explain root causes.");
            }}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-semibold text-xs transition flex items-center gap-2 cursor-pointer shadow-xs"
          >
            <Sparkles size={14} />
            <span>Investigate Further</span>
          </button>

          <button
            onClick={() => setActiveView('compare')}
            className="px-4 py-2 bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 rounded-xl font-medium text-xs transition cursor-pointer"
          >
            Compare Certificate
          </button>

          <button
            onClick={() => executeAction('generate_report')}
            className="px-4 py-2 bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 rounded-xl font-medium text-xs transition cursor-pointer"
          >
            Generate Report
          </button>
        </div>
      )}
    </div>
  );
};

