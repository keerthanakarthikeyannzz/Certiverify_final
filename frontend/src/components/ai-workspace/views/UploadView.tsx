"use client";

import React, { useState, useRef } from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import { Upload, FileText, CheckCircle2, ArrowRight, ShieldCheck, Zap } from 'lucide-react';

export const UploadView: React.FC = () => {
  const { sendMessage, setActiveView } = useAIWorkspace();
  const [selectedFile, setSelectedFile] = useState<{ name: string; size: string; rawFile: File } | null>(null);
  const [selectedOption, setSelectedOption] = useState<string>('Complete Verification');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile({
        name: file.name,
        size: `${(file.size / 1024 / 1024).toFixed(1)} MB`,
        rawFile: file,
      });
    }
  };

  const handleStart = () => {
    if (!selectedFile) return;
    setActiveView('chat');
    sendMessage(`${selectedOption} for document ${selectedFile.name}`, selectedFile.rawFile);
  };

  const optionsList = [
    'Complete Verification',
    'Extract Information',
    'Check Tampering',
    'Verify QR',
    'Check Blockchain',
    'Compare With Existing Certificate'
  ];

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex flex-col overflow-y-auto p-8 space-y-6 font-sans select-none max-w-3xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-slate-900 tracking-tight">Start a Verification</h1>
        <p className="text-xs text-slate-500 font-medium">Upload a certificate and let CertiVerify investigate it.</p>
      </div>

      {/* Upload Box */}
      {!selectedFile ? (
        <div
          onClick={() => fileInputRef.current?.click()}
          className="border-2 border-dashed border-slate-300 hover:border-indigo-500 bg-white rounded-2xl p-12 text-center space-y-4 cursor-pointer transition shadow-2xs group"
        >
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept=".pdf,.png,.jpg,.jpeg"
            className="hidden"
          />
          <div className="w-16 h-16 rounded-2xl bg-indigo-50 text-indigo-600 mx-auto flex items-center justify-center group-hover:scale-105 transition-transform">
            <Upload size={32} />
          </div>

          <div className="space-y-1">
            <p className="font-bold text-slate-900 text-sm">Drag & drop certificate here</p>
            <p className="text-xs text-slate-400">or browse files from your computer</p>
          </div>

          <div className="text-[11px] text-slate-400 font-mono">
            Supported formats: PDF, JPG, JPEG, PNG (Max 10 MB)
          </div>
        </div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs space-y-6">
          <div className="flex items-center justify-between border-b border-slate-100 pb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                <FileText size={20} />
              </div>
              <div>
                <p className="font-bold text-slate-900 text-sm">{selectedFile.name}</p>
                <p className="text-xs text-slate-400 font-mono">{selectedFile.size}</p>
              </div>
            </div>

            <button
              onClick={() => setSelectedFile(null)}
              className="text-xs font-semibold text-rose-600 hover:underline"
            >
              Change File
            </button>
          </div>

          {/* Action Selector */}
          <div className="space-y-3">
            <label className="font-bold text-slate-800 text-xs uppercase tracking-wider">
              What would you like me to do?
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {optionsList.map(opt => (
                <button
                  key={opt}
                  onClick={() => setSelectedOption(opt)}
                  className={`p-3 rounded-xl border text-xs text-left font-medium transition cursor-pointer flex items-center justify-between ${
                    selectedOption === opt
                      ? 'bg-indigo-50 border-indigo-300 text-indigo-900 shadow-2xs font-semibold'
                      : 'bg-slate-50 border-slate-200/80 text-slate-700 hover:bg-slate-100'
                  }`}
                >
                  <span>{opt}</span>
                  {selectedOption === opt && <CheckCircle2 size={15} className="text-indigo-600" />}
                </button>
              ))}
            </div>
          </div>

          <div className="pt-2 flex justify-end">
            <button
              onClick={handleStart}
              className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold transition flex items-center gap-2 shadow-xs cursor-pointer"
            >
              <span>Start Verification</span>
              <ArrowRight size={15} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
