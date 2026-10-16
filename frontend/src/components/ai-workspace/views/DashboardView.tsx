"use client";

import React from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import {
  ShieldCheck,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  FileText,
  Zap,
  Layers,
  ChevronRight
} from 'lucide-react';

export const DashboardView: React.FC = () => {
  const { sendMessage, setActiveView, selectConversation, conversations } = useAIWorkspace();

  const suggestedActions = [
    { label: 'Verify a Certificate', prompt: 'Verify this academic certificate for structural and cryptographic authenticity.' },
    { label: 'Analyze a Document', prompt: 'Analyze this document for signs of font manipulation or digital tampering.' },
    { label: 'Detect Tampering', prompt: 'Run Error Level Analysis (ELA) to detect image alteration.' },
    { label: 'Verify QR', prompt: 'Check the embedded QR code payload signature.' },
    { label: 'Check Blockchain', prompt: 'Check if this certificate hash exists on the immutable ledger.' },
    { label: 'Compare Certificates', prompt: 'Compare two certificates to identify discrepancies.' },
    { label: 'Generate Report', prompt: 'Generate a detailed verification report for audit.' }
  ];

  const recentActivity = conversations.slice(0, 5).map(c => ({
    id: c.id,
    name: c.title || 'Uploaded Certificate',
    verdict: c.verdict || 'genuine',
    trustScore: c.trustScore || 0,
    time: c.updatedAt || 'Recently',
    idNum: c.artifact?.certificateId || c.id
  }));

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex overflow-hidden font-sans select-none">
      {/* Central AI Dashboard Workspace */}
      <div className="flex-1 overflow-y-auto p-8 space-y-8 max-w-4xl mx-auto">
        {/* Welcome Empty State Header */}
        <div className="text-center space-y-4 pt-6">
          <div className="w-16 h-16 rounded-2xl bg-indigo-600 text-white mx-auto flex items-center justify-center shadow-lg shadow-indigo-200">
            <ShieldCheck size={36} />
          </div>

          <div className="space-y-1">
            <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
              How can I help you verify a document?
            </h1>
            <p className="text-sm text-slate-500 font-medium max-w-md mx-auto leading-relaxed">
              Upload a certificate or ask me to investigate its authenticity using AI optical forensics and blockchain ledgers.
            </p>
          </div>
        </div>

        {/* Suggested Action Chips */}
        <div className="space-y-3">
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wider text-center">
            Suggested AI Actions
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2 max-w-2xl mx-auto">
            {suggestedActions.map(act => (
              <button
                key={act.label}
                onClick={() => {
                  setActiveView('chat');
                  sendMessage(act.prompt);
                }}
                className="px-4 py-2 bg-white hover:bg-indigo-50/70 border border-slate-200 hover:border-indigo-200 rounded-xl text-xs text-slate-700 hover:text-indigo-700 font-medium transition shadow-2xs flex items-center gap-2 cursor-pointer group"
              >
                <span>{act.label}</span>
                <ArrowRight size={13} className="text-slate-400 group-hover:text-indigo-600 transition-transform group-hover:translate-x-0.5" />
              </button>
            ))}
          </div>
        </div>

        {/* Recent Verification Activity (Compact list) */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2">
              <Zap size={16} className="text-indigo-600" />
              <h3 className="font-bold text-slate-900 text-sm tracking-tight">Recent Verification Activity</h3>
            </div>
            <button
              onClick={() => setActiveView('history')}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition flex items-center gap-1 cursor-pointer"
            >
              <span>View All History</span>
              <ChevronRight size={14} />
            </button>
          </div>

          <div className="space-y-2">
            {recentActivity.map(item => (
              <div
                key={item.id}
                onClick={() => selectConversation(item.id)}
                className="p-3.5 rounded-xl border border-slate-100 bg-slate-50/50 hover:bg-indigo-50/40 hover:border-indigo-200 transition flex items-center justify-between text-xs cursor-pointer group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                    <FileText size={16} />
                  </div>
                  <div>
                    <p className="font-bold text-slate-900 group-hover:text-indigo-900">{item.name}</p>
                    <p className="text-[10px] text-slate-400 font-mono">ID: {item.idNum}</p>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <span className={`px-2.5 py-0.5 rounded-full font-bold uppercase text-[10px] ${
                    item.verdict === 'genuine' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                  }`}>
                    {item.verdict}
                  </span>

                  <div className="text-right">
                    <span className="font-mono font-bold text-slate-800">{item.trustScore}/100</span>
                    <p className="text-[10px] text-slate-400">{item.time}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right Contextual Panel: Recent Documents */}
      <aside className="w-[340px] h-full bg-[#f8fafc] border-l border-slate-200/80 p-5 shrink-0 overflow-y-auto space-y-4">
        <div className="flex items-center justify-between border-b border-slate-200 pb-3">
          <span className="font-bold text-slate-900 text-xs tracking-tight uppercase">RECENT DOCUMENTS</span>
          <span className="text-[10px] font-mono text-slate-400">{conversations.length} items</span>
        </div>

        <div className="space-y-3">
          {conversations.slice(0, 4).map(conv => (
            <div
              key={conv.id}
              onClick={() => selectConversation(conv.id)}
              className="bg-white border border-slate-200 rounded-xl p-3 shadow-2xs hover:border-indigo-300 transition cursor-pointer space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-800 text-xs truncate max-w-[180px]">
                  {conv.certificateName || conv.title}
                </span>
                {conv.trustScore !== undefined && (
                  <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                    conv.trustScore >= 85 ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                  }`}>
                    {conv.trustScore}
                  </span>
                )}
              </div>

              <div className="w-full h-24 bg-gradient-to-br from-slate-50 to-indigo-50/40 rounded-lg border border-slate-200/60 p-2 flex flex-col justify-between text-[8px] text-slate-500 font-mono">
                <div className="flex justify-between items-center border-b border-slate-200 pb-1">
                  <span>DIPLOMA PREVIEW</span>
                  <span>VERIFIED</span>
                </div>
                <div className="text-center font-bold text-slate-800 text-[9px]">
                  {conv.artifact?.candidateName || 'Not detected'}
                </div>
                <div className="flex justify-between text-[7px] text-slate-400">
                  <span>QR MATCHED</span>
                  <span>BLOCKCHAIN</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
};
