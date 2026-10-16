"use client";

import React, { useEffect, useState, useCallback } from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import { GitCompare, CheckCircle2, AlertTriangle, FileText, Sparkles, Download, Upload, HelpCircle, RefreshCw } from 'lucide-react';
import { certificateApi, comparisonApi, CertificatePairComparisonResponse, CertificateHistoryItem } from '../../../lib/api';

export const CompareView: React.FC = () => {
  const { currentCertificateId, executeAction, activeArtifact, activeConversation } = useAIWorkspace();

  const artifact = activeArtifact || activeConversation?.artifact;
  const certIdA = currentCertificateId || artifact?.certificateId || null;

  const [availableCerts, setAvailableCerts] = useState<CertificateHistoryItem[]>([]);
  const [selectedDocBId, setSelectedDocBId] = useState<string | null>(null);
  const [comparisonData, setComparisonData] = useState<CertificatePairComparisonResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isUploadingB, setIsUploadingB] = useState<boolean>(false);

  // Load available certificates for Document B selection
  const loadAvailableCertificates = useCallback(async () => {
    try {
      const res = await certificateApi.getHistory();
      const items = res.data || [];
      setAvailableCerts(items);

      // Auto-select first certificate that is not Document A
      if (certIdA) {
        const otherCert = items.find(c => c.certificate_id !== certIdA);
        if (otherCert && !selectedDocBId) {
          setSelectedDocBId(otherCert.certificate_id);
        }
      }
    } catch (err) {
      console.error("Failed to load history for comparison:", err);
    }
  }, [certIdA, selectedDocBId]);

  useEffect(() => {
    loadAvailableCertificates();
  }, [loadAvailableCertificates]);

  // Fetch pair comparison whenever certIdA or selectedDocBId changes
  const runPairComparison = useCallback(async (idA: string, idB: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await comparisonApi.comparePair(idA, idB);
      setComparisonData(res.data);
    } catch (err: any) {
      console.error("Pair comparison error:", err);
      setError(err?.response?.data?.detail || "Failed to compare documents.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (certIdA && selectedDocBId && certIdA !== selectedDocBId) {
      runPairComparison(certIdA, selectedDocBId);
    } else {
      setComparisonData(null);
    }
  }, [certIdA, selectedDocBId, runPairComparison]);

  // Handle uploading a new Document B to compare directly against Document A
  const handleDocBUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !certIdA) return;

    setIsUploadingB(true);
    setError(null);
    try {
      const res = await comparisonApi.uploadAndCompare(certIdA, file);
      setComparisonData(res.data);
      setSelectedDocBId(res.data.certificate_id_b);
      await loadAvailableCertificates();
    } catch (err: any) {
      console.error("Upload & compare error:", err);
      setError(err?.response?.data?.detail || "Failed to upload and compare Document B.");
    } finally {
      setIsUploadingB(false);
    }
  };

  const summaryNarrative = comparisonData?.summary_narrative
    ? comparisonData.summary_narrative
    : certIdA
      ? selectedDocBId
        ? "Running comparative analysis between Document A and Document B..."
        : "Select or upload Document B to compare side-by-side against Document A."
      : "Upload a primary document (Document A) to run side-by-side comparative analysis.";

  const rows = comparisonData?.comparison_rows || [
    { field: 'student_name', field_label: 'Candidate Name', doc_a_value: artifact?.candidateName || 'Not detected', doc_b_value: 'Select Document B', status: 'UNKNOWN / NOT DETECTED' },
    { field: 'register_number', field_label: 'Certificate / Registration Number', doc_a_value: certIdA || 'Not detected', doc_b_value: 'Select Document B', status: 'UNKNOWN / NOT DETECTED' },
    { field: 'university_name', field_label: 'Issuing Institution', doc_a_value: artifact?.institution || 'Not detected', doc_b_value: 'Select Document B', status: 'UNKNOWN / NOT DETECTED' },
    { field: 'date_of_issue', field_label: 'Issue Date', doc_a_value: artifact?.issueDate || 'Not detected', doc_b_value: 'Select Document B', status: 'UNKNOWN / NOT DETECTED' },
    { field: 'course', field_label: 'Course / Degree', doc_a_value: artifact?.degreeTitle || 'Not detected', doc_b_value: 'Select Document B', status: 'UNKNOWN / NOT DETECTED' },
    { field: 'qr_code_data', field_label: 'QR Payload Cryptographic Signature', doc_a_value: artifact?.qrPayload || 'Not detected', doc_b_value: 'Select Document B', status: 'UNKNOWN / NOT DETECTED' }
  ];

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex flex-col overflow-y-auto p-8 space-y-6 font-sans select-none max-w-4xl mx-auto">
      <div>
        <div className="flex items-center gap-2">
          <GitCompare size={20} className="text-indigo-600" />
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Compare Certificates</h1>
        </div>
        <p className="text-xs text-slate-500 font-medium">Side-by-side comparative analysis between Document A (Current Upload) and Document B.</p>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-700 font-medium flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => certIdA && selectedDocBId && runPairComparison(certIdA, selectedDocBId)} className="text-indigo-600 hover:underline flex items-center gap-1 font-bold">
            <RefreshCw size={12} /> Retry
          </button>
        </div>
      )}

      {/* Selected Pair Headers */}
      <div className="grid grid-cols-2 gap-4">
        {/* Document A Card */}
        <div className="bg-white border border-slate-200 p-4 rounded-2xl space-y-2 text-xs">
          <span className="text-[10px] font-bold uppercase text-slate-400">DOCUMENT A (PRIMARY CERTIFICATE)</span>
          <p className="font-bold text-slate-900 text-sm truncate">{comparisonData?.doc_a_filename || artifact?.title || 'Current Upload'}</p>
          <p className="font-mono text-[10px] text-indigo-700">{certIdA || 'No active document'}</p>
        </div>

        {/* Document B Card */}
        <div className="bg-white border border-slate-200 p-4 rounded-2xl space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase text-slate-400">DOCUMENT B (COMPARISON TARGET)</span>
            <label className="text-[10px] font-bold text-indigo-600 hover:underline cursor-pointer flex items-center gap-1">
              <Upload size={10} />
              <span>{isUploadingB ? 'Uploading...' : 'Upload File'}</span>
              <input type="file" onChange={handleDocBUpload} className="hidden" accept=".pdf,.png,.jpg,.jpeg" disabled={isUploadingB || !certIdA} />
            </label>
          </div>

          {availableCerts.filter(c => c.certificate_id !== certIdA).length > 0 ? (
            <select
              value={selectedDocBId || ''}
              onChange={(e) => setSelectedDocBId(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-lg p-1.5 text-xs font-semibold text-slate-800 focus:outline-hidden"
            >
              <option value="" disabled>-- Select Document B from uploaded --</option>
              {availableCerts
                .filter(c => c.certificate_id !== certIdA)
                .map(c => (
                  <option key={c.certificate_id} value={c.certificate_id}>
                    {c.filename} ({c.certificate_id.slice(0, 8)}...)
                  </option>
                ))}
            </select>
          ) : (
            <p className="font-bold text-slate-900 text-sm truncate">{comparisonData?.doc_b_filename || 'No Document B Selected'}</p>
          )}

          <p className="font-mono text-[10px] text-indigo-700">{selectedDocBId || 'Select or upload a 2nd document'}</p>
        </div>
      </div>

      {/* Comparison Matrix Table */}
      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-2xs">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase text-[10px]">
            <tr>
              <th className="p-3.5 pl-4">Attribute Field</th>
              <th className="p-3.5">Document A</th>
              <th className="p-3.5">Document B</th>
              <th className="p-3.5 pr-4 text-right">Comparison Verdict</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-normal">
            {loading ? (
              <tr>
                <td colSpan={4} className="p-8 text-center text-slate-400 font-medium">
                  <RefreshCw className="animate-spin inline-block mr-2" size={16} />
                  Running field-by-field OCR comparison...
                </td>
              </tr>
            ) : (
              rows.map((row, idx) => (
                <tr key={idx} className="hover:bg-slate-50/50 transition">
                  <td className="p-3.5 pl-4 font-bold text-slate-900">{row.field_label}</td>
                  <td className="p-3.5 font-mono text-slate-700">{row.doc_a_value || 'Not detected'}</td>
                  <td className="p-3.5 font-mono text-slate-700">{row.doc_b_value || 'Not detected'}</td>
                  <td className="p-3.5 pr-4 text-right">
                    {row.status === 'MATCH' ? (
                      <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-bold text-[10px] inline-flex items-center gap-1">
                        <CheckCircle2 size={12} /> MATCH
                      </span>
                    ) : row.status === 'MISMATCH' ? (
                      <span className="px-2 py-0.5 rounded bg-rose-50 text-rose-700 font-bold text-[10px] inline-flex items-center gap-1">
                        <AlertTriangle size={12} /> MISMATCH
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-bold text-[10px] inline-flex items-center gap-1">
                        <HelpCircle size={12} /> UNKNOWN / NOT DETECTED
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* AI Summary */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl space-y-2 text-xs">
        <h3 className="font-bold text-slate-900 text-xs flex items-center gap-2">
          <Sparkles size={15} className="text-indigo-600" />
          <span>AI Comparative Summary Narrative</span>
        </h3>
        <p className="text-slate-700 leading-relaxed font-normal">
          {summaryNarrative}
        </p>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={() => executeAction('generate_report')}
          className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition cursor-pointer flex items-center gap-1.5"
        >
          <Download size={14} />
          <span>Export Comparison Report</span>
        </button>
      </div>
    </div>
  );
};

