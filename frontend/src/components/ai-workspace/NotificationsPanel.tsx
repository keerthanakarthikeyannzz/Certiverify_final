"use client";

import React from 'react';
import { useAIWorkspace } from '../../context/AIWorkspaceContext';
import { X, CheckCircle2, AlertTriangle, XCircle, Info, Bell } from 'lucide-react';

export const NotificationsPanel: React.FC = () => {
  const {
    isNotificationsOpen,
    setIsNotificationsOpen,
    notifications,
    markNotificationAsRead,
    clearAllNotifications
  } = useAIWorkspace();

  if (!isNotificationsOpen) return null;

  return (
    <div className="fixed inset-0 bg-slate-900/30 backdrop-blur-2xs flex justify-end z-50 animate-splash-scale">
      <div className="w-[360px] h-full bg-white border-l border-slate-200 shadow-2xl flex flex-col font-sans select-none">
        {/* Drawer Header */}
        <div className="p-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bell size={18} className="text-indigo-600" />
            <h3 className="font-bold text-slate-900 text-sm tracking-tight">AI Activity & Notifications</h3>
          </div>
          <button
            onClick={() => setIsNotificationsOpen(false)}
            className="p-1 text-slate-400 hover:text-slate-700 rounded-lg transition cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Notifications List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {notifications.map(n => (
            <div
              key={n.id}
              onClick={() => markNotificationAsRead(n.id)}
              className={`p-3.5 rounded-xl border text-xs transition cursor-pointer space-y-1 ${
                n.read
                  ? 'bg-slate-50/60 border-slate-200/80 text-slate-600'
                  : 'bg-indigo-50/50 border-indigo-200 text-slate-900 shadow-2xs font-semibold'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  {n.type === 'success' && <CheckCircle2 size={14} className="text-emerald-600" />}
                  {n.type === 'warning' && <AlertTriangle size={14} className="text-amber-600" />}
                  {n.type === 'danger' && <XCircle size={14} className="text-rose-600" />}
                  {n.type === 'info' && <Info size={14} className="text-indigo-600" />}
                  <span className="font-bold">{n.title}</span>
                </div>
                <span className="text-[10px] text-slate-400 font-mono">{n.timestamp}</span>
              </div>
              <p className="text-[11px] leading-relaxed font-normal text-slate-600">{n.message}</p>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-slate-200 bg-slate-50 flex justify-between text-xs">
          <button
            onClick={clearAllNotifications}
            className="text-slate-500 hover:text-slate-800 font-medium transition cursor-pointer"
          >
            Mark all read
          </button>
          <button
            onClick={() => setIsNotificationsOpen(false)}
            className="text-indigo-600 font-bold hover:underline transition cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
