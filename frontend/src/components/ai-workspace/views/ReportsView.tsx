"use client";

import React from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import { BarChart3, TrendingUp, ShieldCheck, Sparkles, Send, FileText } from 'lucide-react';

export const ReportsView: React.FC = () => {
  const { setActiveView, sendMessage } = useAIWorkspace();
  const [prompt, setPrompt] = React.useState('');

  const handleAsk = () => {
    if (!prompt.trim()) return;
    setActiveView('chat');
    sendMessage(`Analytics report query: ${prompt}`);
  };

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex flex-col overflow-y-auto p-8 space-y-6 font-sans select-none max-w-5xl mx-auto">
      <div>
        <div className="flex items-center gap-2">
          <BarChart3 size={20} className="text-indigo-600" />
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Reports & Analytics</h1>
        </div>
        <p className="text-xs text-slate-500 font-medium">Understand verification activity, fraud prevention trends, and ledger trust metrics across your organization.</p>
      </div>

      {/* Restrained Analytics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
        <div className="bg-white border border-slate-200 p-4 rounded-2xl space-y-1 shadow-2xs">
          <span className="text-[10px] font-bold text-slate-400 uppercase">Total Verified</span>
          <p className="text-2xl font-extrabold text-slate-900 font-mono">1,482</p>
          <span className="text-[10px] text-emerald-600 font-semibold">↑ 14% vs last month</span>
        </div>
        <div className="bg-white border border-slate-200 p-4 rounded-2xl space-y-1 shadow-2xs">
          <span className="text-[10px] font-bold text-slate-400 uppercase">Avg Trust Score</span>
          <p className="text-2xl font-extrabold text-emerald-700 font-mono">92.4 <span className="text-xs text-slate-400 font-normal">/ 100</span></p>
          <span className="text-[10px] text-slate-400">High Confidence Baseline</span>
        </div>
        <div className="bg-white border border-slate-200 p-4 rounded-2xl space-y-1 shadow-2xs">
          <span className="text-[10px] font-bold text-slate-400 uppercase">Suspicious Flagged</span>
          <p className="text-2xl font-extrabold text-amber-700 font-mono">38</p>
          <span className="text-[10px] text-amber-600 font-semibold">Requires Human Review</span>
        </div>
        <div className="bg-white border border-slate-200 p-4 rounded-2xl space-y-1 shadow-2xs">
          <span className="text-[10px] font-bold text-slate-400 uppercase">Fraud Prevented</span>
          <p className="text-2xl font-extrabold text-rose-700 font-mono">12</p>
          <span className="text-[10px] text-rose-600 font-semibold">Critical Alterations Blocked</span>
        </div>
      </div>

      {/* Restrained Visual Breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs">
        <div className="bg-white border border-slate-200 p-5 rounded-2xl space-y-4 shadow-2xs">
          <h3 className="font-bold text-slate-900 text-xs uppercase tracking-wider">Verification Status Distribution</h3>
          <div className="space-y-3">
            <div>
              <div className="flex justify-between mb-1 text-[11px]"><span className="font-semibold text-slate-700">Genuine (88.4%)</span><span className="font-mono">1,310</span></div>
              <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden"><div className="bg-emerald-500 h-full rounded-full" style={{ width: '88.4%' }} /></div>
            </div>
            <div>
              <div className="flex justify-between mb-1 text-[11px]"><span className="font-semibold text-slate-700">Suspicious (9.2%)</span><span className="font-mono">136</span></div>
              <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden"><div className="bg-amber-500 h-full rounded-full" style={{ width: '9.2%' }} /></div>
            </div>
            <div>
              <div className="flex justify-between mb-1 text-[11px]"><span className="font-semibold text-slate-700">Fake / Altered (2.4%)</span><span className="font-mono">36</span></div>
              <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden"><div className="bg-rose-500 h-full rounded-full" style={{ width: '2.4%' }} /></div>
            </div>
          </div>
        </div>

        <div className="bg-white border border-slate-200 p-5 rounded-2xl space-y-4 shadow-2xs">
          <h3 className="font-bold text-slate-900 text-xs uppercase tracking-wider">Document Types Breakdown</h3>
          <div className="space-y-3">
            <div>
              <div className="flex justify-between mb-1 text-[11px]"><span className="font-semibold text-slate-700">Degree Certificates (54%)</span><span className="font-mono">800</span></div>
              <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden"><div className="bg-indigo-600 h-full rounded-full" style={{ width: '54%' }} /></div>
            </div>
            <div>
              <div className="flex justify-between mb-1 text-[11px]"><span className="font-semibold text-slate-700">Marksheets & Transcripts (31%)</span><span className="font-mono">460</span></div>
              <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden"><div className="bg-indigo-400 h-full rounded-full" style={{ width: '31%' }} /></div>
            </div>
            <div>
              <div className="flex justify-between mb-1 text-[11px]"><span className="font-semibold text-slate-700">Diplomas & Badges (15%)</span><span className="font-mono">222</span></div>
              <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden"><div className="bg-indigo-300 h-full rounded-full" style={{ width: '15%' }} /></div>
            </div>
          </div>
        </div>
      </div>

      {/* Ask CertiVerify about your reports */}
      <div className="bg-white border border-slate-200 p-4 rounded-2xl space-y-3 shadow-2xs">
        <div className="flex items-center gap-2 font-bold text-slate-900 text-xs">
          <Sparkles size={16} className="text-indigo-600" />
          <span>Ask CertiVerify about your reports</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
            placeholder="e.g. 'Which document types have the highest number of suspicious results?'"
            className="flex-1 px-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:border-indigo-500"
          />
          <button
            onClick={handleAsk}
            className="px-4 py-2 bg-indigo-600 text-white font-semibold rounded-xl text-xs hover:bg-indigo-700 transition cursor-pointer flex items-center gap-1.5"
          >
            <span>Ask AI</span>
            <Send size={14} />
          </button>
        </div>
      </div>
    </div>
  );
};
