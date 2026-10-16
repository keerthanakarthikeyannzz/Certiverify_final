"use client";

import React, { useState } from 'react';
import { useAIWorkspace } from '../../context/AIWorkspaceContext';
import {
  FileText,
  ShieldCheck,
  AlertTriangle,
  XCircle,
  ExternalLink,
  Info,
  CheckCircle2,
  Lock,
  Layers,
  Search,
  Eye,
  Maximize2,
  ChevronRight,
  HelpCircle,
  X
} from 'lucide-react';

export const AIContextPanel: React.FC = () => {
  const {
    activeConversation,
    activeArtifact,
    activeEvidenceId,
    setActiveEvidenceId,
    executeAction,
    currentCertificateId
  } = useAIWorkspace();

  const [showWhyModal, setShowWhyModal] = useState(false);

  const lastMsg = activeConversation?.messages?.slice().reverse().find(m => m.sender === 'assistant');
  const isStreaming = lastMsg?.isStreaming ?? false;
  const hasRunPipeline = lastMsg?.trustScore !== undefined || (activeArtifact?.trustScore != null && activeArtifact.trustScore > 0);

  const trustScore = isStreaming ? null : (lastMsg?.trustScore ?? (activeArtifact?.trustScore != null && activeArtifact.trustScore > 0 ? activeArtifact.trustScore : null));
  const verdict = isStreaming ? 'analyzing' : (lastMsg?.verdict ?? activeArtifact?.verdict ?? 'pending');
  const evidenceList = lastMsg?.evidenceList ?? [];

  const ocrSignal = lastMsg?.signals?.find(s => s.category === 'ocr');
  const qrSignal = lastMsg?.signals?.find(s => s.category === 'qr');
  const bcSignal = lastMsg?.signals?.find(s => s.category === 'blockchain');
  const tamperSignal = lastMsg?.signals?.find(s => s.category === 'tamper');
  const dupSignal = lastMsg?.signals?.find(s => s.category === 'duplicate');

  const positiveSignals = lastMsg?.signals?.filter(s => s.status === 'verified').map(s => `${s.name}: ${s.details}`) || (activeArtifact?.findings || []);
  const potentialLimitations = lastMsg?.signals?.filter(s => s.status === 'warning' || s.status === 'failed').map(s => `${s.name}: ${s.details}`) || [];

  return (
    <aside className="w-[360px] h-full bg-[#f8fafc] border-l border-slate-200/80 flex flex-col shrink-0 overflow-y-auto select-none font-sans">
      {/* Context Panel Header */}
      <div className="p-4 border-b border-slate-200/80 bg-white flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-indigo-600" />
          <span className="font-bold text-slate-900 text-sm tracking-tight">DOCUMENT CONTEXT</span>
        </div>
        <button
          onClick={() => executeAction('generate_report')}
          className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-indigo-600 transition cursor-pointer"
          title="Open Artifact Viewer"
        >
          <Maximize2 size={15} />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* Certificate Document Visual Preview Box */}
        <div className="bg-white border border-slate-200 rounded-2xl p-3 shadow-2xs space-y-2 relative overflow-hidden group">
          <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
            <span className="truncate max-w-[200px]">{activeConversation?.certificateName || 'Document Preview'}</span>
            <span className="text-[10px] font-mono bg-slate-100 px-1.5 py-0.5 rounded">PDF</span>
          </div>

          {/* Certificate Miniature Render Mock */}
          <div className="w-full h-40 bg-gradient-to-br from-slate-50 via-slate-100 to-indigo-50/30 rounded-xl border border-slate-200/70 p-3 flex flex-col justify-between relative overflow-hidden text-[9px] text-slate-700 font-serif shadow-inner">
            <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
              <div className="flex items-center gap-1">
                <div className="w-4 h-4 rounded-full bg-indigo-600/20 flex items-center justify-center text-indigo-700 font-bold text-[7px]">
                  CV
                </div>
                <span className="font-bold uppercase tracking-wider text-slate-800 text-[8px]">CERTIFICATE PREVIEW</span>
              </div>
              <span className="font-mono text-[7px] text-slate-400">ID: {activeArtifact?.certificateId || currentCertificateId || 'N/A'}</span>
            </div>

            <div className="space-y-1 text-center py-2">
              <p className="text-[7px] text-slate-400 uppercase tracking-widest font-sans font-semibold">{activeArtifact?.degreeTitle || 'Document'}</p>
              <p className="text-[11px] font-bold text-slate-900 font-sans">{activeArtifact?.candidateName || 'Not detected'}</p>
              <p className="text-[7px] text-slate-500 font-sans">{activeArtifact?.institution || 'Not detected'}</p>
            </div>

            <div className="flex items-center justify-between pt-1 border-t border-slate-200 text-[7px] font-sans text-slate-500">
              <span>Date: {activeArtifact?.issueDate || 'Not detected'}</span>
              <div className="w-4 h-4 bg-slate-800 rounded flex items-center justify-center text-white font-mono text-[6px]">
                QR
              </div>
            </div>

            {/* Hover overlay inspect button */}
            <div className="absolute inset-0 bg-slate-900/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2 backdrop-blur-2xs">
              <button
                onClick={() => executeAction('generate_report')}
                className="px-3 py-1.5 bg-white text-slate-900 rounded-lg text-xs font-semibold shadow-md hover:bg-indigo-50 transition cursor-pointer flex items-center gap-1"
              >
                <Eye size={13} />
                <span>Inspect Document</span>
              </button>
            </div>
          </div>
        </div>

        {/* Trust Score Breakdown Card */}
        <div className={`p-4 rounded-2xl border shadow-2xs space-y-3 ${
          isStreaming || trustScore === null ? 'bg-slate-50 border-slate-200' :
          verdict === 'genuine' ? 'bg-emerald-50/60 border-emerald-200/80' :
          verdict === 'suspicious' ? 'bg-amber-50/60 border-amber-200/80' :
          'bg-rose-50/60 border-rose-200/80'
        }`}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-600">TRUST SCORE</span>
            {trustScore !== null && (
              <button
                onClick={() => setShowWhyModal(true)}
                className="text-xs font-semibold text-indigo-700 hover:text-indigo-900 flex items-center gap-1 cursor-pointer"
              >
                <HelpCircle size={13} />
                <span>Why?</span>
              </button>
            )}
          </div>

          <div className="flex items-baseline justify-between">
            <div className="flex items-baseline gap-1">
              <span className={`text-4xl font-extrabold font-mono tracking-tight ${
                isStreaming || trustScore === null ? 'text-slate-400' :
                trustScore >= 85 ? 'text-emerald-700' :
                trustScore >= 50 ? 'text-amber-700' :
                'text-rose-700'
              }`}>
                {isStreaming ? '...' : trustScore !== null ? trustScore : '--'}
              </span>
              <span className="text-xs text-slate-400 font-semibold">/ 100</span>
            </div>

            <span className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wide border ${
              isStreaming ? 'bg-indigo-100 text-indigo-800 border-indigo-300 animate-pulse' :
              verdict === 'genuine' ? 'bg-emerald-100 text-emerald-800 border-emerald-300' :
              verdict === 'suspicious' ? 'bg-amber-100 text-amber-800 border-amber-300' :
              verdict === 'fake' ? 'bg-rose-100 text-rose-800 border-rose-300' :
              'bg-slate-100 text-slate-600 border-slate-300'
            }`}>
              {isStreaming ? 'Analyzing' : verdict}
            </span>
          </div>

          <p className="text-xs text-slate-600 leading-relaxed font-normal">
            {isStreaming && 'Executing multi-layer AI verification pipeline...'}
            {!isStreaming && trustScore === null && 'Upload a certificate PDF to compute verification trust score.'}
            {!isStreaming && verdict === 'genuine' && 'High-confidence authenticity backed by cryptographic ledger hash and clean optical signals.'}
            {!isStreaming && verdict === 'suspicious' && 'Moderate-risk document. Flagged for font metric anomalies or QR payload checksum failure.'}
            {!isStreaming && verdict === 'fake' && 'Low-confidence document. Detected critical digital seal forgery and zero ledger record.'}
          </p>
        </div>

        {/* Verification Badges Matrix */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs space-y-3">
          <div className="text-xs font-bold text-slate-800 uppercase tracking-wider border-b border-slate-100 pb-2">
            VERIFICATION SIGNALS
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-2 bg-slate-50 border border-slate-100 rounded-xl flex items-center justify-between">
              <span className="font-semibold text-slate-700">OCR</span>
              <span className={`font-bold ${ocrSignal?.status === 'verified' ? 'text-emerald-600' : isStreaming ? 'text-indigo-600' : 'text-slate-400'}`}>
                {ocrSignal?.status === 'verified' ? '✓ Ready' : isStreaming ? 'Processing...' : 'Pending'}
              </span>
            </div>
            <div className="p-2 bg-slate-50 border border-slate-100 rounded-xl flex items-center justify-between">
              <span className="font-semibold text-slate-700">QR Code</span>
              <span className={`font-bold ${qrSignal?.status === 'verified' ? 'text-emerald-600' : qrSignal?.status === 'warning' ? 'text-amber-600' : qrSignal?.status === 'failed' ? 'text-rose-600' : 'text-slate-400'}`}>
                {qrSignal ? (qrSignal.status === 'verified' ? '✓ Verified' : qrSignal.status === 'warning' ? '⚠ Warning' : '❌ Invalid') : (isStreaming ? 'Checking...' : 'Pending')}
              </span>
            </div>
            <div className="p-2 bg-slate-50 border border-slate-100 rounded-xl flex items-center justify-between">
              <span className="font-semibold text-slate-700">Blockchain</span>
              <span className={`font-bold ${bcSignal?.status === 'verified' ? 'text-emerald-600' : bcSignal?.status === 'failed' ? 'text-rose-600' : 'text-slate-400'}`}>
                {bcSignal ? (bcSignal.status === 'verified' ? '✓ Verified' : '— Unlinked') : (isStreaming ? 'Checking...' : 'Pending')}
              </span>
            </div>
            <div className="p-2 bg-slate-50 border border-slate-100 rounded-xl flex items-center justify-between">
              <span className="font-semibold text-slate-700">Tamper</span>
              <span className={`font-bold ${tamperSignal?.status === 'verified' ? 'text-emerald-600' : tamperSignal?.status === 'warning' ? 'text-amber-600' : tamperSignal?.status === 'failed' ? 'text-rose-600' : 'text-slate-400'}`}>
                {tamperSignal ? (tamperSignal.status === 'verified' ? '✓ Clean' : tamperSignal.status === 'warning' ? '⚠ Review' : '❌ Tampered') : (isStreaming ? 'Scanning...' : 'Pending')}
              </span>
            </div>
            <div className="p-2 bg-slate-50 border border-slate-100 rounded-xl flex items-center justify-between col-span-2">
              <span className="font-semibold text-slate-700">Duplicate Check</span>
              <span className={`font-bold ${dupSignal?.status === 'verified' ? 'text-emerald-600' : dupSignal?.status === 'failed' ? 'text-rose-600' : 'text-slate-400'}`}>
                {dupSignal ? (dupSignal.status === 'verified' ? '✓ Unique Record' : '❌ Duplicate Detected') : (isStreaming ? 'Checking...' : 'Pending')}
              </span>
            </div>
          </div>
        </div>

        {/* Evidence Explorer List */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs space-y-3">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2">
            <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">EVIDENCE CITATIONS</span>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">
              {evidenceList.length} Signals
            </span>
          </div>

          <div className="space-y-2">
            {evidenceList.length > 0 ? (
              evidenceList.map(ev => {
                const isSelected = activeEvidenceId === ev.id;
                return (
                  <button
                    key={ev.id}
                    onClick={() => setActiveEvidenceId(ev.id)}
                    className={`w-full text-left p-3 rounded-xl border text-xs transition cursor-pointer ${
                      isSelected
                        ? 'bg-indigo-50/80 border-indigo-300 ring-1 ring-indigo-300 shadow-2xs'
                        : 'bg-slate-50/50 border-slate-200/80 hover:bg-slate-100'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-indigo-700">[{ev.id}] {ev.title}</span>
                      <span className="text-[10px] font-mono text-slate-400">{ev.sourceType}</span>
                    </div>
                    <p className="text-[11px] text-slate-600 line-clamp-2 leading-relaxed">{ev.snippet}</p>
                  </button>
                );
              })
            ) : (
              <p className="text-xs text-slate-400 italic p-2">Upload a document to extract evidence citations.</p>
            )}
          </div>
        </div>
      </div>

      {/* "Why?" Trust Score Explanation Modal */}
      {showWhyModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl border border-slate-200 p-6 max-w-lg w-full space-y-4 shadow-xl animate-splash-scale">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck size={20} className="text-indigo-600" />
                <h3 className="font-bold text-slate-900 text-base">Trust Score Breakdown ({trustScore}/100)</h3>
              </div>
              <button
                onClick={() => setShowWhyModal(false)}
                className="p-1 text-slate-400 hover:text-slate-700 rounded-lg transition cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="space-y-2">
                <span className="font-bold text-emerald-800 flex items-center gap-1">
                  <CheckCircle2 size={14} /> Supporting Positive Signals:
                </span>
                <ul className="space-y-1.5 pl-4 list-disc text-slate-700 leading-relaxed">
                  {positiveSignals.map((sig, idx) => (
                    <li key={idx}>{sig}</li>
                  ))}
                </ul>
              </div>

              <div className="space-y-2 pt-2 border-t border-slate-100">
                <span className="font-bold text-amber-800 flex items-center gap-1">
                  <Info size={14} /> Potential Limitations & Risk Factors:
                </span>
                <ul className="space-y-1.5 pl-4 list-disc text-slate-700 leading-relaxed">
                  {potentialLimitations.map((lim, idx) => (
                    <li key={idx}>{lim}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex justify-end">
              <button
                onClick={() => setShowWhyModal(false)}
                className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition cursor-pointer"
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};
