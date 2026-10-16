"use client";

import React from 'react';
import { useAIWorkspace } from '../../context/AIWorkspaceContext';
import {
  X,
  Download,
  Share2,
  Copy,
  Check,
  ShieldCheck,
  FileText,
  Lock,
  QrCode,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Printer
} from 'lucide-react';

export const AIArtifactViewer: React.FC = () => {
  const { activeArtifact, setActiveArtifact, executeAction } = useAIWorkspace();
  const [copied, setCopied] = React.useState(false);

  if (!activeArtifact) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(activeArtifact, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center z-50 p-6 animate-splash-scale">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-4xl w-full h-[85vh] flex flex-col overflow-hidden font-sans">
        {/* Artifact Header Toolbar */}
        <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-indigo-600 text-white flex items-center justify-center font-bold text-xs shadow-xs">
              <FileText size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-slate-900 text-sm tracking-tight">{activeArtifact.title}</span>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 uppercase">
                  AI ARTIFACT
                </span>
              </div>
              <p className="text-[11px] text-slate-500 font-mono">ID: {activeArtifact.verificationId}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-700 hover:bg-slate-100 transition flex items-center gap-1.5 cursor-pointer shadow-2xs"
            >
              {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
              <span>{copied ? 'Copied JSON' : 'Copy Data'}</span>
            </button>
            <button
              onClick={handlePrint}
              className="px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-700 hover:bg-slate-100 transition flex items-center gap-1.5 cursor-pointer shadow-2xs"
            >
              <Printer size={14} />
              <span>Print Dossier</span>
            </button>
            <button
              onClick={() => executeAction('download_pdf')}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition flex items-center gap-1.5 cursor-pointer shadow-xs"
            >
              <Download size={14} />
              <span>Download PDF</span>
            </button>
            <button
              onClick={() => setActiveArtifact(null)}
              className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-200 transition cursor-pointer"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Artifact Scrollable Content Dossier */}
        <div className="flex-1 overflow-y-auto p-8 space-y-6 bg-[#fafafa]">
          {/* Header Banner */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">CERTIVERIFY FORENSIC REPORT</span>
              <h2 className="text-xl font-extrabold text-slate-900 tracking-tight">{activeArtifact.degreeTitle}</h2>
              <p className="text-xs text-slate-500 font-medium">{activeArtifact.institution}</p>
            </div>

            <div className="text-right flex items-center gap-4 border-l border-slate-100 pl-6">
              <div>
                <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">TRUST SCORE</div>
                <div className={`text-3xl font-extrabold font-mono ${
                  activeArtifact.trustScore >= 85 ? 'text-emerald-700' :
                  activeArtifact.trustScore >= 50 ? 'text-amber-700' : 'text-rose-700'
                }`}>
                  {activeArtifact.trustScore} <span className="text-xs text-slate-400 font-normal">/ 100</span>
                </div>
              </div>

              <div className={`px-3.5 py-1.5 rounded-xl border font-bold text-xs uppercase tracking-wide ${
                activeArtifact.verdict === 'genuine' ? 'bg-emerald-50 text-emerald-800 border-emerald-200' :
                activeArtifact.verdict === 'suspicious' ? 'bg-amber-50 text-amber-800 border-amber-200' :
                'bg-rose-50 text-rose-800 border-rose-200'
              }`}>
                {activeArtifact.verdict}
              </div>
            </div>
          </div>

          {/* Candidate & Verification Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs space-y-3">
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider border-b border-slate-100 pb-2">
                Extracted Identity Fields
              </h3>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-slate-100">
                  <span className="text-slate-500">Candidate Name:</span>
                  <span className="font-bold text-slate-900">{activeArtifact.candidateName}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-100">
                  <span className="text-slate-500">Certificate Serial:</span>
                  <span className="font-mono font-bold text-slate-900">{activeArtifact.certificateId}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-100">
                  <span className="text-slate-500">Issue Date:</span>
                  <span className="font-medium text-slate-800">{activeArtifact.issueDate}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-500">Verification ID:</span>
                  <span className="font-mono text-indigo-700 font-semibold">{activeArtifact.verificationId}</span>
                </div>
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs space-y-3">
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider border-b border-slate-100 pb-2">
                Cryptographic Evidence Ledger
              </h3>
              <div className="space-y-2 text-xs">
                <div className="space-y-0.5">
                  <span className="text-[10px] text-slate-400 font-medium uppercase">QR Payload Target:</span>
                  <p className="font-mono text-[11px] text-indigo-700 truncate bg-slate-50 p-1.5 rounded border border-slate-200">
                    {activeArtifact.qrPayload || 'N/A'}
                  </p>
                </div>
                <div className="space-y-0.5">
                  <span className="text-[10px] text-slate-400 font-medium uppercase">Blockchain Ledger TX Hash:</span>
                  <p className="font-mono text-[11px] text-slate-800 truncate bg-slate-50 p-1.5 rounded border border-slate-200">
                    {activeArtifact.blockchainTxHash || 'N/A'}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* AI Executive Summary & Forensic Findings */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs space-y-4">
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider border-b border-slate-100 pb-2 flex items-center gap-2">
              <Sparkles size={15} className="text-indigo-600" />
              <span>AI Autonomous Forensic Findings</span>
            </h3>

            <p className="text-sm text-slate-700 leading-relaxed font-normal">
              {activeArtifact.summaryText}
            </p>

            <div className="space-y-2 pt-2">
              <span className="text-xs font-bold text-slate-800">Verified Evidence Points:</span>
              <ul className="space-y-2">
                {activeArtifact.findings.map((f, idx) => (
                  <li key={idx} className="flex items-start gap-2.5 text-xs text-slate-700 bg-slate-50 p-2.5 rounded-xl border border-slate-100">
                    <CheckCircle2 size={15} className="text-emerald-600 shrink-0 mt-0.5" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
