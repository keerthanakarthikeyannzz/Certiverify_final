"use client";

import React, { useState } from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import {
  FileText,
  Search,
  Filter,
  PlusCircle,
  Eye,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Sparkles,
  MessageSquare,
  ChevronRight
} from 'lucide-react';

export const CertificatesView: React.FC = () => {
  const { certificateRecords, setActiveView, selectConversation, sendMessage } = useAIWorkspace();
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('all');

  const filtered = certificateRecords.filter(c => {
    const matchSearch = c.name.toLowerCase().includes(search.toLowerCase()) || c.certificateId.toLowerCase().includes(search.toLowerCase()) || c.owner.toLowerCase().includes(search.toLowerCase());
    const matchFilter = filterType === 'all' || c.verdict === filterType;
    return matchSearch && matchFilter;
  });

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex flex-col overflow-y-auto p-8 space-y-6 font-sans select-none">
      {/* Title Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">All Certificates</h1>
          <p className="text-xs text-slate-500 font-medium">Manage and investigate certificates using CertiVerify AI.</p>
        </div>

        <button
          onClick={() => setActiveView('upload')}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-medium text-xs flex items-center gap-1.5 shadow-xs transition cursor-pointer"
        >
          <PlusCircle size={16} />
          <span>+ Upload Certificate</span>
        </button>
      </div>

      {/* Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white border border-slate-200 p-3 rounded-2xl shadow-2xs">
        <div className="relative flex-1 min-w-[240px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search certificates by name, ID, or owner..."
            className="w-full pl-8 pr-4 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div className="flex items-center gap-2 text-xs">
          <Filter size={14} className="text-slate-400" />
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-slate-700 font-medium focus:outline-none"
          >
            <option value="all">All Statuses</option>
            <option value="genuine">Genuine</option>
            <option value="suspicious">Suspicious</option>
            <option value="fake">Fake</option>
          </select>
        </div>
      </div>

      {/* Modern AI Document Rows */}
      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-2xs">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50/80 border-b border-slate-200 text-slate-500 font-bold uppercase text-[10px]">
            <tr>
              <th className="p-3.5 pl-4">Certificate Name & ID</th>
              <th className="p-3.5">Owner</th>
              <th className="p-3.5">Document Type</th>
              <th className="p-3.5 text-center">Trust Score</th>
              <th className="p-3.5">Status</th>
              <th className="p-3.5">Last Verified</th>
              <th className="p-3.5 pr-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-normal">
            {filtered.map(cert => (
              <tr key={cert.id} className="hover:bg-indigo-50/30 transition">
                <td className="p-3.5 pl-4 flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold shrink-0">
                    <FileText size={18} />
                  </div>
                  <div>
                    <p className="font-bold text-slate-900">{cert.name}</p>
                    <p className="text-[10px] font-mono text-slate-400">{cert.certificateId}</p>
                  </div>
                </td>
                <td className="p-3.5 font-medium text-slate-700">{cert.owner}</td>
                <td className="p-3.5 text-slate-600">{cert.documentType}</td>
                <td className="p-3.5 text-center font-mono font-bold">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    cert.trustScore >= 85 ? 'bg-emerald-50 text-emerald-700' :
                    cert.trustScore >= 50 ? 'bg-amber-50 text-amber-700' : 'bg-rose-50 text-rose-700'
                  }`}>
                    {cert.trustScore}/100
                  </span>
                </td>
                <td className="p-3.5">
                  <span className={`px-2.5 py-0.5 rounded-full font-bold uppercase text-[10px] ${
                    cert.verdict === 'genuine' ? 'bg-emerald-100 text-emerald-800' :
                    cert.verdict === 'suspicious' ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'
                  }`}>
                    {cert.verdict}
                  </span>
                </td>
                <td className="p-3.5 text-slate-500">{cert.lastVerified}</td>
                <td className="p-3.5 pr-4 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={() => setActiveView('detail')}
                      className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-medium text-[11px] transition cursor-pointer"
                    >
                      Open
                    </button>
                    <button
                      onClick={() => {
                        setActiveView('chat');
                        sendMessage(`Verify certificate ${cert.certificateId}`);
                      }}
                      className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg font-semibold text-[11px] transition cursor-pointer"
                    >
                      Verify
                    </button>
                    <button
                      onClick={() => {
                        setActiveView('chat');
                        sendMessage(`Ask CertiVerify about certificate ${cert.name} (${cert.certificateId})`);
                      }}
                      className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold text-[11px] transition cursor-pointer flex items-center gap-1"
                    >
                      <Sparkles size={11} />
                      <span>Ask AI</span>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* AI Command option */}
      <div className="bg-indigo-50/70 border border-indigo-100 p-4 rounded-2xl flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Sparkles size={18} className="text-indigo-600" />
          <div>
            <p className="font-bold text-slate-900 text-xs">Ask CertiVerify about these certificates</p>
            <p className="text-[11px] text-slate-500">Run natural language bulk queries across all uploaded documents.</p>
          </div>
        </div>
        <button
          onClick={() => {
            setActiveView('chat');
            sendMessage("Analyze all uploaded certificates and summarize risk trends.");
          }}
          className="px-3.5 py-1.5 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition cursor-pointer"
        >
          Ask AI Now
        </button>
      </div>
    </div>
  );
};
