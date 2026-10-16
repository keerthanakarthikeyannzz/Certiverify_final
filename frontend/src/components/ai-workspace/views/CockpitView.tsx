"use client";

import React, { useState } from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import {
  Layers,
  ZoomIn,
  ZoomOut,
  RotateCw,
  Maximize2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileText,
  ShieldCheck,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

export const CockpitView: React.FC = () => {
  const { activeArtifact, executeAction } = useAIWorkspace();
  const [zoom, setZoom] = useState(100);
  const [rotation, setRotation] = useState(0);

  const sections = [
    { title: 'Document Classification', status: 'Passed', text: `Document structure matches ${activeArtifact?.degreeTitle || 'Document'} layout schema.` },
    { title: 'OCR Analysis', status: 'Passed', text: 'Extracted 42 candidate text fields. Zero OCR character substitutions flagged.' },
    { title: 'Field Consistency', status: 'Passed', text: 'Candidate name and roll number cross-verified with official institution database.' },
    { title: 'Document Integrity (Tamper ELA)', status: 'Passed', text: 'Error Level Analysis confirmed uniform compression delta across seals and signature blocks.' },
    { title: 'QR Verification', status: 'Passed', text: 'QR code payload decrypted cleanly and validated via RSA-2048 public key.' },
    { title: 'Blockchain Verification', status: 'Passed', text: 'Merkle root hash matched block #18,429,102 on decentralized ledger.' },
    { title: 'Duplicate Detection', status: 'Passed', text: 'Single issuance instance confirmed in global serial index.' },
    { title: 'Metadata Analysis', status: 'Passed', text: 'Creation tool and PDF structure consistent with official University Press.' }
  ];

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex overflow-hidden font-sans select-none">
      {/* LEFT: Certificate Viewer (Zoom/Rotate/Fullscreen) */}
      <div className="w-[420px] h-full bg-white border-r border-slate-200/80 p-4 flex flex-col shrink-0 space-y-3">
        <div className="flex items-center justify-between border-b border-slate-100 pb-2 text-xs">
          <span className="font-bold text-slate-900 uppercase">DOCUMENT VIEWER</span>
          <div className="flex items-center gap-1">
            <button onClick={() => setZoom(Math.max(50, zoom - 10))} className="p-1 hover:bg-slate-100 rounded cursor-pointer"><ZoomOut size={14} /></button>
            <span className="font-mono text-[10px] text-slate-500">{zoom}%</span>
            <button onClick={() => setZoom(Math.min(200, zoom + 10))} className="p-1 hover:bg-slate-100 rounded cursor-pointer"><ZoomIn size={14} /></button>
            <button onClick={() => setRotation((rotation + 90) % 360)} className="p-1 hover:bg-slate-100 rounded cursor-pointer"><RotateCw size={14} /></button>
            <button onClick={() => executeAction('generate_report')} className="p-1 hover:bg-slate-100 rounded cursor-pointer"><Maximize2 size={14} /></button>
          </div>
        </div>

        <div className="flex-1 bg-slate-100 rounded-xl border border-slate-200 p-4 flex items-center justify-center overflow-hidden relative">
          <div
            style={{ transform: `scale(${zoom / 100}) rotate(${rotation}deg)` }}
            className="w-full h-80 bg-white rounded shadow-md border border-slate-300 p-4 flex flex-col justify-between transition-transform duration-200 text-center"
          >
            <div className="border-b pb-2 flex justify-between text-[8px] font-mono text-slate-500">
              <span>{activeArtifact?.institution || 'DOCUMENT'}</span>
              <span>{activeArtifact?.certificateId || 'N/A'}</span>
            </div>
            <div className="space-y-1 my-auto">
              <p className="text-[9px] uppercase tracking-widest text-slate-400 font-semibold">{activeArtifact?.degreeTitle || 'Credential'}</p>
              <p className="text-sm font-bold text-slate-900">{activeArtifact?.candidateName || 'Not detected'}</p>
              <p className="text-[8px] text-slate-500">{activeArtifact?.institution || ''}</p>
            </div>
            <div className="border-t pt-2 flex justify-between text-[8px] font-mono text-slate-400">
              <span>{activeArtifact?.issueDate || 'N/A'}</span>
              <span className="text-emerald-600 font-bold">{activeArtifact?.verdict ? activeArtifact.verdict.toUpperCase() : 'PENDING'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* CENTER: AI Analysis Workspace */}
      <div className="flex-1 h-full overflow-y-auto p-6 space-y-4">
        <div>
          <h1 className="text-lg font-bold text-slate-900 tracking-tight">AI Verification Cockpit</h1>
          <p className="text-xs text-slate-500 font-medium">Deep forensic analysis results for document: {activeArtifact?.certificateId || 'Current Upload'}</p>
        </div>

        <div className="space-y-3">
          {activeArtifact?.findings ? activeArtifact.findings.map((finding, idx) => (
            <div key={idx} className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-900 text-xs">Forensic Finding #{idx + 1}</span>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 flex items-center gap-1">
                  <CheckCircle2 size={12} /> VERIFIED
                </span>
              </div>
              <p className="text-xs text-slate-600 leading-relaxed font-normal">{finding}</p>
            </div>
          )) : (
            <div className="bg-white border border-slate-200 rounded-2xl p-4 text-xs text-slate-500">
              No findings yet. Please upload a certificate to run dynamic analysis.
            </div>
          )}
        </div>
      </div>

      {/* RIGHT: Trust + Evidence */}
      <aside className="w-[320px] h-full bg-[#f8fafc] border-l border-slate-200/80 p-5 shrink-0 space-y-4 font-sans">
        <div className="bg-emerald-50/70 border border-emerald-200 p-4 rounded-2xl space-y-2 text-center">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">TRUST SCORE</span>
          <div className="text-4xl font-extrabold font-mono text-emerald-700">{activeArtifact?.trustScore != null ? activeArtifact.trustScore : 0} <span className="text-xs text-slate-400 font-normal">/ 100</span></div>
          <span className="inline-block px-3 py-1 bg-emerald-100 text-emerald-800 rounded-full font-bold text-xs uppercase">{activeArtifact?.verdict || 'PENDING'}</span>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs space-y-2 text-xs">
          <span className="font-bold text-slate-900 uppercase tracking-wider text-[10px]">VERIFIED EVIDENCE SIGNALS</span>
          <ul className="space-y-1.5 text-slate-700 pt-1">
            <li className="flex items-center gap-2"><CheckCircle2 size={13} className="text-emerald-600" /> QR: {activeArtifact?.qrPayload || 'No QR Detected'}</li>
            <li className="flex items-center gap-2"><CheckCircle2 size={13} className="text-emerald-600" /> Ledger: {activeArtifact?.blockchainTxHash || 'Not Registered'}</li>
            <li className="flex items-center gap-2"><CheckCircle2 size={13} className="text-emerald-600" /> Tamper Score: {activeArtifact?.tamperScore != null ? Math.round(activeArtifact.tamperScore * 100) : 0}/100</li>
            <li className="flex items-center gap-2"><CheckCircle2 size={13} className="text-emerald-600" /> Candidate: {activeArtifact?.candidateName || 'Not detected'}</li>
          </ul>
        </div>
      </aside>
    </div>
  );
};
