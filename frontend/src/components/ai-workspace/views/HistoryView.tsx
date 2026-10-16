"use client";

import React, { useState } from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import { History, Search, FileText, CheckCircle2, AlertTriangle, XCircle, Sparkles } from 'lucide-react';

export const HistoryView: React.FC = () => {
  const { conversations, selectConversation, setActiveView, executeAction } = useAIWorkspace();
  const [search, setSearch] = useState('');

  const filtered = conversations.filter(c => c.title.toLowerCase().includes(search.toLowerCase()) || (c.certificateName && c.certificateName.toLowerCase().includes(search.toLowerCase())));

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex flex-col overflow-y-auto p-8 space-y-6 font-sans select-none max-w-5xl mx-auto">
      <div>
        <div className="flex items-center gap-2">
          <History size={20} className="text-indigo-600" />
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Verification History</h1>
        </div>
        <p className="text-xs text-slate-500 font-medium">Review past AI verification conversations, audit trails, and generated reports.</p>
      </div>

      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter history by certificate name or title..."
          className="w-full pl-8 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:border-indigo-500 shadow-2xs"
        />
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-2xs">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase text-[10px]">
            <tr>
              <th className="p-3.5 pl-4">Certificate & Conversation</th>
              <th className="p-3.5">Category</th>
              <th className="p-3.5">Trust Score</th>
              <th className="p-3.5">Status</th>
              <th className="p-3.5">Last Activity</th>
              <th className="p-3.5 pr-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-normal">
            {filtered.map(conv => (
              <tr key={conv.id} className="hover:bg-indigo-50/30 transition">
                <td className="p-3.5 pl-4 flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                    <FileText size={16} />
                  </div>
                  <div>
                    <p className="font-bold text-slate-900">{conv.title}</p>
                    <p className="text-[10px] text-slate-400 font-mono">{conv.certificateName || 'Uploaded File'}</p>
                  </div>
                </td>
                <td className="p-3.5 text-slate-600 font-medium">{conv.category}</td>
                <td className="p-3.5 font-mono font-bold">
                  {conv.trustScore !== undefined ? (
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      conv.trustScore >= 85 ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                    }`}>
                      {conv.trustScore}/100
                    </span>
                  ) : '—'}
                </td>
                <td className="p-3.5">
                  <span className={`px-2.5 py-0.5 rounded-full font-bold uppercase text-[10px] ${
                    conv.verdict === 'genuine' ? 'bg-emerald-100 text-emerald-800' :
                    conv.verdict === 'suspicious' ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'
                  }`}>
                    {conv.verdict || 'analyzing'}
                  </span>
                </td>
                <td className="p-3.5 text-slate-500">{conv.updatedAt}</td>
                <td className="p-3.5 pr-4 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={() => selectConversation(conv.id)}
                      className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold text-[11px] transition cursor-pointer"
                    >
                      Open Conversation
                    </button>
                    <button
                      onClick={() => {
                        selectConversation(conv.id);
                        executeAction('generate_report');
                      }}
                      className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-medium text-[11px] transition cursor-pointer"
                    >
                      View Report
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
