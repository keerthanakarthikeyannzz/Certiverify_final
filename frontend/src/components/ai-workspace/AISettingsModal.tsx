"use client";

import React, { useState } from 'react';
import { useAIWorkspace } from '../../context/AIWorkspaceContext';
import { X, Settings, ShieldCheck, Key, Cpu, Sliders, Database, Save, Check } from 'lucide-react';

export const AISettingsModal: React.FC = () => {
  const { isSettingsOpen, setIsSettingsOpen } = useAIWorkspace();
  const [activeTab, setActiveTab] = useState<'general' | 'engine' | 'api'>('general');
  const [ocrEngine, setOcrEngine] = useState('tesseract-v5');
  const [sensitivity, setSensitivity] = useState(85);
  const [saved, setSaved] = useState(false);

  if (!isSettingsOpen) return null;

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => {
      setSaved(false);
      setIsSettingsOpen(false);
    }, 1000);
  };

  return (
    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-xl w-full overflow-hidden font-sans animate-splash-scale">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Settings size={18} className="text-indigo-600" />
            <h3 className="font-bold text-slate-900 text-base">CertiVerify AI Settings</h3>
          </div>
          <button
            onClick={() => setIsSettingsOpen(false)}
            className="p-1 text-slate-400 hover:text-slate-700 rounded-lg transition cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Settings Navigation Tabs */}
        <div className="flex border-b border-slate-200 bg-slate-50/50 px-6 text-xs font-medium text-slate-600">
          {[
            { id: 'general', label: 'General & Thresholds', icon: Sliders },
            { id: 'engine', label: 'AI Pipeline Parameters', icon: Cpu },
            { id: 'api', label: 'API Keys & Ledger', icon: Key }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`py-3 px-4 border-b-2 font-semibold flex items-center gap-1.5 transition cursor-pointer ${
                activeTab === tab.id
                  ? 'border-indigo-600 text-indigo-700 bg-white'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <tab.icon size={14} />
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Tab Body */}
        <div className="p-6 space-y-4 text-xs">
          {activeTab === 'general' && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="font-semibold text-slate-800">Genuine Trust Score Threshold ({sensitivity}/100)</label>
                <input
                  type="range"
                  min={50}
                  max={95}
                  value={sensitivity}
                  onChange={(e) => setSensitivity(parseInt(e.target.value))}
                  className="w-full accent-indigo-600 cursor-pointer"
                />
                <p className="text-[11px] text-slate-400">
                  Documents scoring at or above {sensitivity} will be classified as Genuine.
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-800">Default AI Workspace Mode</label>
                <select className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-800">
                  <option value="verify">Verify (Standard 8-signal check)</option>
                  <option value="analyze">Analyze (Deep forensic inspection)</option>
                  <option value="investigate">Investigate (Perplexity-style evidence collection)</option>
                </select>
              </div>
            </div>
          )}

          {activeTab === 'engine' && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="font-semibold text-slate-800">Primary OCR & Vision Model</label>
                <select
                  value={ocrEngine}
                  onChange={(e) => setOcrEngine(e.target.value)}
                  className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-800"
                >
                  <option value="tesseract-v5">CertiVerify Optical Vision Engine v5 (Default)</option>
                  <option value="paddle-ocr">PaddleOCR High Confidence Multi-Lingual</option>
                  <option value="cloud-vision">Enterprise Cloud Vision API</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-800">Tamper Error Level Analysis (ELA) Resolution</label>
                <select className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-800">
                  <option value="high">High Resolution Pixel Compression Grid (1024x1024)</option>
                  <option value="fast">Fast Standard ELA Grid (512x512)</option>
                </select>
              </div>
            </div>
          )}

          {activeTab === 'api' && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="font-semibold text-slate-800">Decentralized Blockchain Provider</label>
                <input
                  type="text"
                  defaultValue="https://mainnet.infura.io/v3/official-certiverify-key"
                  className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg font-mono text-slate-800"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-800">Institutional Public Registry API Key</label>
                <input
                  type="password"
                  defaultValue="sk_live_certiverify_992183019283"
                  className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg font-mono text-slate-800"
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex justify-end gap-2">
          <button
            onClick={() => setIsSettingsOpen(false)}
            className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-100 transition cursor-pointer font-medium"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition cursor-pointer font-semibold flex items-center gap-1.5"
          >
            {saved ? <Check size={14} /> : <Save size={14} />}
            <span>{saved ? 'Saved Configuration' : 'Save Preferences'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
