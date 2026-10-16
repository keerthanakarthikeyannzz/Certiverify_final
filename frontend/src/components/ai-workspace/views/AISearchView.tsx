"use client";

import React, { useState } from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import { Search, Sparkles, FileText, ArrowRight, ShieldCheck } from 'lucide-react';

export const AISearchView: React.FC = () => {
  const { searchQuery, setSearchQuery, certificateRecords, selectConversation } = useAIWorkspace();
  const [query, setQuery] = useState(searchQuery || 'Show suspicious certificates');

  const filtered = certificateRecords.filter(c => {
    const q = query.toLowerCase();
    if (q.includes('suspicious')) return c.verdict === 'suspicious';
    if (q.includes('genuine')) return c.verdict === 'genuine';
    if (q.includes('fake') || q.includes('70')) return c.trustScore < 70;
    return c.name.toLowerCase().includes(q) || c.certificateId.toLowerCase().includes(q);
  });

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex flex-col overflow-y-auto p-8 space-y-6 font-sans select-none max-w-4xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-slate-900 tracking-tight">AI Global Search</h1>
        <p className="text-xs text-slate-500 font-medium">Search across certificates, verification ledgers, and forensic rules using natural language.</p>
      </div>

      {/* Query Bar */}
      <div className="relative">
        <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search your certificates or ask a question (e.g. 'Show suspicious marksheets', 'Trust Score < 70')..."
          className="w-full pl-10 pr-4 py-3 bg-white border border-slate-200 rounded-2xl text-xs text-slate-900 focus:outline-none focus:border-indigo-500 shadow-2xs"
        />
      </div>

      {/* Conversational Synthesis Result */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl space-y-3 text-xs shadow-2xs">
        <div className="flex items-center gap-2 font-bold text-slate-900">
          <Sparkles size={16} className="text-indigo-600" />
          <span>I found {filtered.length} certificates matching your query "{query}"</span>
        </div>
        <p className="text-slate-600 leading-relaxed font-normal">
          Results reflect records matching structural parameters, trust scores, and verification status filters.
        </p>
      </div>

      {/* Compact Results List */}
      <div className="space-y-3">
        {filtered.map(item => (
          <div
            key={item.id}
            onClick={() => selectConversation('conv-2')}
            className="bg-white border border-slate-200 rounded-2xl p-4 flex items-center justify-between text-xs hover:border-indigo-300 transition cursor-pointer shadow-2xs"
          >
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                <FileText size={18} />
              </div>
              <div>
                <p className="font-bold text-slate-900">{item.name}</p>
                <p className="text-[10px] font-mono text-slate-400">{item.certificateId} • {item.owner}</p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <span className={`px-2.5 py-0.5 rounded-full font-bold uppercase text-[10px] ${
                item.verdict === 'genuine' ? 'bg-emerald-100 text-emerald-800' :
                item.verdict === 'suspicious' ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'
              }`}>
                {item.verdict}
              </span>
              <span className="font-mono font-bold text-slate-800">{item.trustScore}/100</span>
              <ArrowRight size={14} className="text-slate-400" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
