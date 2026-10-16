"use client";

import React from 'react';
import { useAIWorkspace } from '../../context/AIWorkspaceContext';
import { ActiveView, CertificateStatus } from '../../types/ai-workspace';
import {
  PlusCircle,
  Search,
  MessageSquare,
  ShieldCheck,
  LayoutDashboard,
  FileText,
  Upload,
  Cpu,
  Eye,
  SearchCode,
  GitCompare,
  BarChart3,
  History,
  AlertTriangle,
  Settings,
  HelpCircle,
  Layers,
  Sparkles
} from 'lucide-react';

export const AISidebar: React.FC = () => {
  const {
    conversations,
    activeConversationId,
    selectConversation,
    createNewConversation,
    searchQuery,
    setSearchQuery,
    activeView,
    setActiveView,
    setIsSettingsOpen
  } = useAIWorkspace();

  const filteredConversations = conversations.filter(c =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (c.certificateName && c.certificateName.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const categories: Array<'Today' | 'Yesterday' | 'This Week'> = ['Today', 'Yesterday', 'This Week'];

  const getVerdictBadge = (verdict?: CertificateStatus) => {
    if (verdict === 'genuine') {
      return <div className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" title="Genuine" />;
    }
    if (verdict === 'suspicious') {
      return <div className="w-2 h-2 rounded-full bg-amber-500 shrink-0 animate-pulse" title="Suspicious" />;
    }
    if (verdict === 'inconclusive') {
      return <div className="w-2 h-2 rounded-full bg-amber-400 shrink-0" title="Needs Review (Inconclusive)" />;
    }
    if (verdict === 'fake') {
      return <div className="w-2 h-2 rounded-full bg-rose-500 shrink-0" title="Fake" />;
    }
    if (verdict === 'analyzing') {
      return <div className="w-2 h-2 rounded-full bg-indigo-500 shrink-0 animate-spin" title="Analyzing" />;
    }
    return <div className="w-2 h-2 rounded-full bg-slate-300 shrink-0" />;
  };

  const mainNavItems: Array<{ id: ActiveView; label: string; icon: any }> = [
    { id: 'dashboard', label: 'AI Home', icon: LayoutDashboard },
    { id: 'certificates', label: 'All Certificates', icon: FileText },
    { id: 'upload', label: 'Upload Certificate', icon: Upload },
    { id: 'pipeline', label: 'AI Pipeline', icon: Cpu },
    { id: 'cockpit', label: 'Verification Cockpit', icon: Layers },
    { id: 'evidence', label: 'Evidence Explorer', icon: Eye },
    { id: 'investigation', label: 'AI Investigation', icon: SearchCode },
    { id: 'compare', label: 'Compare Certificates', icon: GitCompare },
    { id: 'reports', label: 'Reports & Analytics', icon: BarChart3 },
    { id: 'history', label: 'History', icon: History },
    { id: 'review', label: 'Certificate Review', icon: AlertTriangle }
  ];

  return (
    <aside className="w-[280px] h-full bg-[#f8fafc] border-r border-slate-200/80 flex flex-col shrink-0 select-none font-sans">
      {/* New Verification CTA Button */}
      <div className="p-3.5 pb-2">
        <button
          onClick={createNewConversation}
          className="w-full py-2.5 px-3.5 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white rounded-xl font-medium text-sm flex items-center justify-center gap-2 shadow-xs transition-all duration-150 group cursor-pointer"
        >
          <PlusCircle size={18} className="group-hover:rotate-90 transition-transform duration-200" />
          <span>+ New Verification</span>
        </button>
      </div>

      {/* Search Input */}
      <div className="px-3.5 py-1.5">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations & files..."
            className="w-full pl-8 pr-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
          />
        </div>
      </div>

      {/* Scrollable Navigation Body */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-4">
        {/* Workspace Views Navigation */}
        <div className="space-y-0.5">
          <div className="px-2.5 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
            Platform Views
          </div>
          {mainNavItems.map(item => {
            const isActive = activeView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveView(item.id)}
                className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-medium flex items-center gap-2.5 transition cursor-pointer ${
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 font-semibold border border-indigo-200/60 shadow-2xs'
                    : 'text-slate-600 hover:bg-slate-200/50 hover:text-slate-900'
                }`}
              >
                <item.icon size={15} className={isActive ? 'text-indigo-600' : 'text-slate-400'} />
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </div>

        {/* AI Conversations History */}
        {categories.map(cat => {
          const items = filteredConversations.filter(c => c.category === cat);
          if (items.length === 0) return null;

          return (
            <div key={cat} className="space-y-1 pt-1 border-t border-slate-200/60">
              <div className="px-2.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                {cat} Conversations
              </div>
              <div className="space-y-0.5">
                {items.map(conv => {
                  const isActive = activeView === 'chat' && conv.id === activeConversationId;
                  return (
                    <button
                      key={conv.id}
                      onClick={() => selectConversation(conv.id)}
                      className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs flex items-center justify-between gap-2 transition cursor-pointer ${
                        isActive
                          ? 'bg-white border border-slate-200/80 shadow-xs text-indigo-950 font-semibold'
                          : 'text-slate-600 hover:bg-slate-200/50 hover:text-slate-900 font-normal'
                      }`}
                    >
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        {getVerdictBadge(conv.verdict)}
                        <span className="truncate text-[11px]">{conv.title}</span>
                      </div>
                      {conv.trustScore !== undefined && (
                        <span className={`text-[9px] font-mono px-1 py-0.5 rounded ${
                          conv.trustScore >= 85 ? 'bg-emerald-50 text-emerald-700 font-semibold' :
                          conv.trustScore >= 50 ? 'bg-amber-50 text-amber-700 font-semibold' :
                          'bg-rose-50 text-rose-700 font-semibold'
                        }`}>
                          {conv.trustScore}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer Settings Link */}
      <div className="p-3 border-t border-slate-200/80 bg-white/60 space-y-1">
        <button
          onClick={() => setIsSettingsOpen(true)}
          className="w-full px-2.5 py-1.5 rounded-lg text-xs text-slate-600 hover:bg-slate-100 flex items-center gap-2 transition cursor-pointer"
        >
          <Settings size={15} className="text-slate-400" />
          <span>Settings</span>
        </button>
        <div className="pt-1 flex items-center justify-between px-2.5">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 font-semibold text-[10px] flex items-center justify-center border border-indigo-200">
              KK
            </div>
            <div className="text-left">
              <p className="text-xs font-medium text-slate-800 leading-tight">Keerthana K</p>
              <p className="text-[10px] text-slate-400 leading-tight">Enterprise Security</p>
            </div>
          </div>
          <span className="w-2 h-2 rounded-full bg-emerald-500" title="Online" />
        </div>
      </div>
    </aside>
  );
};
