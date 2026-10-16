"use client";

import React from 'react';
import { useAIWorkspace } from '../../context/AIWorkspaceContext';
import { ShieldCheck, Search, Bell, HelpCircle, User, Sparkles } from 'lucide-react';

import { Logo } from '../ui/Logo';

export const AIHeader: React.FC = () => {
  const {
    searchQuery,
    setSearchQuery,
    setActiveView,
    isNotificationsOpen,
    setIsNotificationsOpen,
    notifications,
    setIsSettingsOpen
  } = useAIWorkspace();

  const unreadCount = notifications.filter(n => !n.read).length;

  return (
    <header className="h-14 bg-white border-b border-slate-200/80 px-6 flex items-center justify-between shrink-0 select-none font-sans shadow-2xs z-20">
      {/* Left Brand Identity */}
      <div className="flex items-center gap-2 cursor-pointer" onClick={() => setActiveView('dashboard')}>
        <Logo size="sm" isDark={false} showWordmark={true} />
        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-indigo-100 text-indigo-700 uppercase tracking-wide ml-1">
          AI PLATFORM
        </span>
      </div>

      {/* Center AI Search & Command Bar */}
      <div className="flex-1 max-w-md mx-8 relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              setActiveView('search');
            }
          }}
          placeholder="Ask CertiVerify... (e.g. 'Show suspicious marksheets', 'Trust Score < 70')"
          className="w-full pl-8 pr-4 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-100 transition"
        />
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => alert("CertiVerify AI Platform v2.4 — Multi-Layer Autonomous Verification System")}
          className="p-2 text-slate-500 hover:text-indigo-600 hover:bg-slate-100 rounded-xl transition cursor-pointer"
          title="Help & Info"
        >
          <HelpCircle size={18} />
        </button>

        {/* Notifications Button */}
        <button
          onClick={() => setIsNotificationsOpen(!isNotificationsOpen)}
          className="p-2 text-slate-500 hover:text-indigo-600 hover:bg-slate-100 rounded-xl transition relative cursor-pointer"
          title="Activity Notifications"
        >
          <Bell size={18} />
          {unreadCount > 0 && (
            <span className="absolute top-1 right-1 w-4 h-4 bg-indigo-600 text-white rounded-full text-[9px] font-bold flex items-center justify-center">
              {unreadCount}
            </span>
          )}
        </button>

        {/* User Profile */}
        <button
          onClick={() => setIsSettingsOpen(true)}
          className="flex items-center gap-2 pl-2 border-l border-slate-200 hover:opacity-80 transition cursor-pointer"
        >
          <div className="w-7 h-7 rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs flex items-center justify-center border border-indigo-200">
            KK
          </div>
        </button>
      </div>
    </header>
  );
};
