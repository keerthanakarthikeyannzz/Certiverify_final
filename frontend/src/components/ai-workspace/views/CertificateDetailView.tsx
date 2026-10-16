"use client";

import React from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import { FileText, CheckCircle2, ShieldCheck, Sparkles, Download, Share2 } from 'lucide-react';

export const CertificateDetailView: React.FC = () => {
  const { activeArtifact, setActiveView, sendMessage } = useAIWorkspace();

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex overflow-hidden font-sans select-none">
      {/* Left Large Preview */}
      <div className="flex-1 p-8 flex flex-col items-center justify-center border-r border-slate-200/80">
        <div className="w-full max-w-lg h-96 bg-white border border-slate-300 rounded-2xl p-8 shadow-md flex flex-col justify-between text-center relative overflow-hidden">
          <div className="border-b pb-3 flex justify-between text-xs font-mono text-slate-500">
            <span>DOCUMENT PREVIEW</span>
            <span>ID: {activeArtifact?.certificateId || 'N/A'}</span>
          </div>

          <div className="space-y-2 my-auto">
            <p className="text-xs uppercase tracking-widest text-slate-400 font-semibold font-sans">{activeArtifact?.degreeTitle || 'Document'}</p>
            <h2 className="text-xl font-bold text-slate-900 font-sans">{activeArtifact?.candidateName || 'Not detected'}</h2>
            <p className="text-xs text-slate-600 font-sans">{activeArtifact?.institution || 'Not detected'}</p>
          </div>

          <div className="border-t pt-3 flex justify-between text-xs font-mono text-slate-400">
            <span>Issue Date: {activeArtifact?.issueDate || 'Not detected'}</span>
            <span className="text-emerald-600 font-bold">{activeArtifact?.verdict ? activeArtifact.verdict.toUpperCase() : 'PENDING'}</span>
          </div>
        </div>
      </div>

      {/* Right Verification Summary */}
      <aside className="w-[420px] h-full bg-white p-6 overflow-y-auto space-y-6 shrink-0">
        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">CERTIFICATE VERIFICATION</span>
          <h2 className="text-lg font-bold text-slate-900 font-mono">{activeArtifact?.certificateId || 'N/A'}</h2>
        </div>

        {/* Status Banner */}
        <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-between">
          <div>
            <span className="text-[10px] font-bold uppercase text-slate-500">STATUS</span>
            <div className="flex items-center gap-1.5 font-bold text-emerald-800 text-sm">
              <CheckCircle2 size={16} /> VERIFIED {activeArtifact?.verdict ? activeArtifact.verdict.toUpperCase() : 'PENDING'}
            </div>
          </div>
          <div className="text-right">
            <span className="text-[10px] font-bold uppercase text-slate-500">TRUST SCORE</span>
            <p className="text-2xl font-extrabold font-mono text-emerald-700">{activeArtifact?.trustScore != null ? activeArtifact.trustScore : 0}/100</p>
          </div>
        </div>

        {/* Certificate Information Table */}
        <div className="space-y-3">
          <h3 className="text-xs font-bold uppercase text-slate-800 tracking-wider border-b border-slate-100 pb-2">
            Certificate Attributes
          </h3>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-100"><span className="text-slate-500">Candidate Name:</span><span className="font-bold text-slate-900">{activeArtifact?.candidateName || 'Not detected'}</span></div>
            <div className="flex justify-between py-1 border-b border-slate-100"><span className="text-slate-500">Serial Number:</span><span className="font-mono text-slate-800 font-semibold">{activeArtifact?.certificateId || 'N/A'}</span></div>
            <div className="flex justify-between py-1 border-b border-slate-100"><span className="text-slate-500">Issuing Institution:</span><span className="font-medium text-slate-800">{activeArtifact?.institution || 'Not detected'}</span></div>
            <div className="flex justify-between py-1 border-b border-slate-100"><span className="text-slate-500">Degree / Program:</span><span className="font-medium text-slate-800">{activeArtifact?.degreeTitle || 'Document'}</span></div>
            <div className="flex justify-between py-1"><span className="text-slate-500">Issue Date:</span><span className="text-slate-800">{activeArtifact?.issueDate || 'Not detected'}</span></div>
          </div>
        </div>

        {/* Badges Grid */}
        <div className="space-y-2">
          <h3 className="text-xs font-bold uppercase text-slate-800 tracking-wider">Verification Signals</h3>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="p-2 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between font-medium"><span>OCR</span><span className="text-emerald-600 font-bold">{activeArtifact?.candidateName && activeArtifact.candidateName !== 'Not detected' ? '✓' : '—'}</span></div>
            <div className="p-2 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between font-medium"><span>QR Code</span><span className="text-emerald-600 font-bold">{activeArtifact?.qrPayload && activeArtifact.qrPayload !== 'Not detected' ? '✓' : 'No QR'}</span></div>
            <div className="p-2 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between font-medium"><span>Blockchain</span><span className="text-emerald-600 font-bold">{activeArtifact?.blockchainTxHash && activeArtifact.blockchainTxHash !== 'Pending' ? (activeArtifact.blockchainTxHash.includes('Verified') ? '✓' : 'Not Reg.') : '—'}</span></div>
            <div className="p-2 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between font-medium"><span>Tamper Check</span><span className="text-emerald-600 font-bold">{activeArtifact?.tamperScore != null ? (activeArtifact.tamperScore < 0.3 ? 'Clean' : 'Risk') : '—'}</span></div>
            <div className="p-2 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between font-medium"><span>Duplicate Check</span><span className="text-emerald-600 font-bold">{activeArtifact?.certificateId ? 'Unique' : '—'}</span></div>
            <div className="p-2 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between font-medium"><span>Metadata Check</span><span className="text-emerald-600 font-bold">{activeArtifact?.certificateId ? '✓' : '—'}</span></div>
          </div>
        </div>

        {/* Action button */}
        <button
          onClick={() => {
            setActiveView('chat');
            if (activeArtifact?.certificateId) {
              sendMessage(`Investigate certificate ${activeArtifact.certificateId} in detail.`);
            }
          }}
          className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl text-xs flex items-center justify-center gap-2 shadow-xs transition cursor-pointer"
        >
          <Sparkles size={16} />
          <span>Ask CertiVerify About This Certificate</span>
        </button>
      </aside>
    </div>
  );
};
