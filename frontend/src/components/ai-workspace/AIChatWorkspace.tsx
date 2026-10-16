"use client";

import React, { useState, useRef, useEffect } from 'react';
import { useAIWorkspace } from '../../context/AIWorkspaceContext';
import {
  ShieldCheck,
  Sparkles,
  Paperclip,
  Image as ImageIcon,
  FileText,
  Send,
  Mic,
  MicOff,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Loader2,
  FileCheck,
  Search,
  Zap,
  ArrowRight,
  Maximize2,
  Download,
  Eye
} from 'lucide-react';
import { AIMode } from '../../types/ai-workspace';

export const AIChatWorkspace: React.FC = () => {
  const {
    activeConversation,
    mode,
    setMode,
    sendMessage,
    executeAction,
    setActiveEvidenceId,
    isVoiceActive,
    toggleVoice,
    setSearchQuery
  } = useAIWorkspace();

  const [input, setInput] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [expandedSignalsMap, setExpandedSignalsMap] = useState<Record<string, boolean>>({});
  const [expandedTranscriptsMap, setExpandedTranscriptsMap] = useState<Record<string, boolean>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [activeConversation?.messages]);

  const toggleSignals = (msgId: string) => {
    setExpandedSignalsMap(prev => ({
      ...prev,
      [msgId]: !prev[msgId]
    }));
  };

  const toggleTranscript = (msgId: string) => {
    setExpandedTranscriptsMap(prev => ({
      ...prev,
      [msgId]: !prev[msgId]
    }));
  };

  const handleSend = () => {
    if (!input.trim() && !selectedFile) return;
    const sendText = input.trim() || (selectedFile ? `Please verify this document: ${selectedFile.name}` : '');
    sendMessage(sendText, selectedFile || undefined);
    setInput('');
    setSelectedFile(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = (file: File) => {
    if (!file) return;
    const allowedExts = ['.pdf', '.png', '.jpg', '.jpeg'];
    const fileNameLower = file.name.toLowerCase();
    const isValidExt = allowedExts.some(ext => fileNameLower.endsWith(ext));

    if (!isValidExt) {
      alert("Unsupported file type. Please select a PDF or document image (.pdf, .png, .jpg, .jpeg).");
      return;
    }

    if (file.size > 15 * 1024 * 1024) {
      alert("File size exceeds maximum allowed limit of 15 MB.");
      return;
    }

    setSelectedFile(file);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileSelect(file);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleFileSelect(file);
    }
  };

  const modesList: Array<{ id: AIMode; label: string }> = [
    { id: 'verify', label: 'Verify' },
    { id: 'analyze', label: 'Analyze' },
    { id: 'investigate', label: 'Investigate' },
    { id: 'compare', label: 'Compare' },
    { id: 'report', label: 'Report' }
  ];

  const suggestedActions = [
    { label: 'Verify Certificate', prompt: 'Verify this certificate for authenticity and structural integrity.' },
    { label: 'Analyze Document', prompt: 'Analyze this document for signs of font, pixel, or stamp tampering.' },
    { label: 'Check QR', prompt: 'Check the embedded QR code payload and verify its cryptographic signature.' },
    { label: 'Check Blockchain', prompt: 'Check if this certificate hash exists on the immutable ledger.' },
    { label: 'Detect Tampering', prompt: 'Run Error Level Analysis (ELA) to detect digital photo alterations.' },
    { label: 'Compare Certificates', prompt: 'Compare two certificates to spot discrepancies in issued versions.' },
    { label: 'Generate Report', prompt: 'Generate a detailed PDF verification dossier for institutional audit.' }
  ];

  const messages = activeConversation?.messages || [];

  return (
    <div
      className="flex-1 h-full bg-[#fafafa] flex flex-col relative overflow-hidden font-sans"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Top AI Control Bar */}
      <header className="h-14 bg-white border-b border-slate-200/80 px-6 flex items-center justify-between shrink-0 z-10 shadow-2xs">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-800 text-sm tracking-tight">CertiVerify AI</span>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          </div>

          {/* Mode Selector Tabs */}
          <div className="flex items-center bg-slate-100/80 p-0.5 rounded-lg border border-slate-200/60">
            {modesList.map(m => (
              <button
                key={m.id}
                onClick={() => setMode(m.id)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition cursor-pointer ${
                  mode === m.id
                    ? 'bg-white text-indigo-700 shadow-xs font-semibold'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* Global Natural Language Query / Search shortcut */}
        <div className="flex items-center gap-3">
          <div className="relative hidden md:block">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Filter certificates (e.g. Trust Score < 70)..."
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  setSearchQuery((e.target as HTMLInputElement).value);
                }
              }}
              className="pl-7 pr-3 py-1 bg-slate-50 border border-slate-200 rounded-md text-xs text-slate-700 w-64 placeholder-slate-400 focus:outline-none focus:border-indigo-500"
            />
          </div>
          <span className="text-[11px] font-mono text-slate-400">v2.4-AI</span>
        </div>
      </header>

      {/* Main Conversational Workspace Body */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {messages.length === 0 ? (
          /* Empty / Welcome State */
          <div className="h-full max-w-2xl mx-auto flex flex-col items-center justify-center text-center space-y-6 pt-8">
            <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shadow-sm">
              <ShieldCheck size={36} />
            </div>

            <div className="space-y-2">
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                How can I help verify your documents?
              </h1>
              <p className="text-sm text-slate-500 max-w-md mx-auto leading-relaxed">
                Upload a certificate or ask me to investigate its authenticity, check QR payloads, or run tamper analysis.
              </p>
            </div>

            {/* Suggested Action Chips */}
            <div className="w-full pt-4">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Suggested AI Actions
              </p>
              <div className="flex flex-wrap items-center justify-center gap-2 max-w-xl mx-auto">
                {suggestedActions.map(act => (
                  <button
                    key={act.label}
                    onClick={() => sendMessage(act.prompt)}
                    className="px-3.5 py-2 bg-white hover:bg-indigo-50/70 border border-slate-200 hover:border-indigo-200 rounded-xl text-xs text-slate-700 hover:text-indigo-700 font-medium transition shadow-2xs flex items-center gap-1.5 cursor-pointer group"
                  >
                    <span>{act.label}</span>
                    <ArrowRight size={12} className="text-slate-400 group-hover:text-indigo-600 transition-transform group-hover:translate-x-0.5" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          /* Active Chat Thread */
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map((msg) => (
              <div key={msg.id} className="space-y-3">
                {/* User Message */}
                {msg.sender === 'user' && (
                  <div className="flex flex-col items-end space-y-2">
                    <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-xs px-4 py-2.5 max-w-xl text-sm shadow-xs font-medium leading-relaxed">
                      {msg.text}
                    </div>
                    {msg.attachedFile && (
                      <div className="bg-white border border-slate-200 rounded-xl p-2.5 flex items-center gap-3 shadow-2xs text-xs text-slate-700 max-w-sm">
                        <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                          <FileText size={18} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="font-semibold text-slate-900 truncate">{msg.attachedFile.name}</p>
                          <p className="text-[10px] text-slate-400">{msg.attachedFile.size} • {msg.attachedFile.type.includes('pdf') ? 'PDF Document' : 'Document Image'}</p>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Assistant Response */}
                {msg.sender === 'assistant' && (
                  <div className="flex items-start gap-3 text-left">
                    <div className="w-8 h-8 rounded-xl bg-indigo-600 text-white flex items-center justify-center shrink-0 mt-1 shadow-sm shadow-indigo-200">
                      <Sparkles size={16} />
                    </div>

                    <div className="flex-1 space-y-4 max-w-2xl">
                      {/* Live AI Streaming Pipeline Progress */}
                      {msg.stages && msg.stages.length > 0 && (
                        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs space-y-3">
                          <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                            <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">
                              <Zap size={14} className="text-indigo-600" />
                              <span>AI Verification Pipeline Execution</span>
                            </div>
                            {msg.isStreaming ? (
                              <span className="text-[11px] text-indigo-600 font-medium flex items-center gap-1">
                                <Loader2 size={12} className="animate-spin" /> Analyzing...
                              </span>
                            ) : (
                              <span className="text-[11px] text-emerald-600 font-medium flex items-center gap-1">
                                <CheckCircle2 size={12} /> Complete
                              </span>
                            )}
                          </div>

                          <div className="grid grid-cols-2 gap-2 text-xs">
                            {msg.stages.map(stg => (
                              <div key={stg.id} className="flex items-center gap-2 py-0.5">
                                {stg.status === 'completed' && <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />}
                                {stg.status === 'running' && <Loader2 size={13} className="text-indigo-600 animate-spin shrink-0" />}
                                {stg.status === 'warning' && <AlertTriangle size={13} className="text-amber-500 shrink-0" />}
                                {stg.status === 'failed' && <XCircle size={13} className="text-rose-500 shrink-0" />}
                                {stg.status === 'pending' && <div className="w-3 h-3 rounded-full border border-slate-300 shrink-0" />}
                                <span className={`text-[11px] truncate ${
                                  stg.status === 'completed' ? 'text-slate-700 font-medium' :
                                  stg.status === 'running' ? 'text-indigo-700 font-semibold' :
                                  stg.status === 'warning' ? 'text-amber-700 font-medium' :
                                  stg.status === 'failed' ? 'text-rose-700 font-medium' : 'text-slate-400'
                                }`}>
                                  {stg.label}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* OCR Extraction Result Card */}
                      {msg.ocrResult && (
                        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs space-y-3 font-sans">
                          <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                            <div className="flex items-center gap-2 text-xs font-bold text-slate-900 tracking-tight">
                              <CheckCircle2 size={15} className="text-emerald-600" />
                              <span className="uppercase">✓ OCR EXTRACTION COMPLETED</span>
                            </div>
                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/60">
                              {msg.ocrResult.confidencePercent}% Confidence
                            </span>
                          </div>

                          {/* Metadata Summary */}
                          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs text-slate-600 border-b border-slate-100 pb-3">
                            <div><span className="font-semibold text-slate-800">OCR Status:</span> {msg.ocrResult.status}</div>
                            <div><span className="font-semibold text-slate-800">OCR Engine:</span> {msg.ocrResult.engine}</div>
                            <div><span className="font-semibold text-slate-800">Pages Processed:</span> {msg.ocrResult.pagesProcessed}</div>
                            <div><span className="font-semibold text-slate-800">Text Extracted:</span> {msg.ocrResult.textExtractedSummary}</div>
                            <div><span className="font-semibold text-slate-800">Fields Detected:</span> {msg.ocrResult.fieldsDetectedCount}</div>
                            <div><span className="font-semibold text-slate-800">Confidence:</span> {msg.ocrResult.confidencePercent}%</div>
                          </div>

                          {/* Extracted Information Section */}
                          <div className="space-y-2">
                            <div className="text-[11px] font-bold uppercase tracking-wider text-indigo-700">EXTRACTED INFORMATION</div>
                            <div className="bg-slate-50/80 border border-slate-200/80 rounded-xl p-3 text-xs space-y-1.5 text-slate-700">
                              <div className="flex justify-between">
                                <span className="font-semibold text-slate-800">Student Name:</span>
                                <span className="font-medium text-slate-900">{msg.ocrResult.extractedInfo.studentName || 'Not detected'}</span>
                              </div>
                              <div className="flex justify-between border-t border-slate-200/50 pt-1">
                                <span className="font-semibold text-slate-800">Register Number:</span>
                                <span className="font-mono text-slate-900">{msg.ocrResult.extractedInfo.registerNumber || 'Not detected'}</span>
                              </div>
                              <div className="flex justify-between border-t border-slate-200/50 pt-1">
                                <span className="font-semibold text-slate-800">Institution:</span>
                                <span className="font-medium text-slate-900">{msg.ocrResult.extractedInfo.institution || 'Not detected'}</span>
                              </div>
                              <div className="flex justify-between border-t border-slate-200/50 pt-1">
                                <span className="font-semibold text-slate-800">Semester / Course:</span>
                                <span className="font-medium text-slate-900">{msg.ocrResult.extractedInfo.semesterCourse || 'Not detected'}</span>
                              </div>
                              <div className="flex justify-between border-t border-slate-200/50 pt-1">
                                <span className="font-semibold text-slate-800">Marks / CGPA:</span>
                                <span className="font-medium text-slate-900">{msg.ocrResult.extractedInfo.marksCgpa || 'Not detected'}</span>
                              </div>
                              <div className="flex justify-between border-t border-slate-200/50 pt-1">
                                <span className="font-semibold text-slate-800">Result Status:</span>
                                <span className="font-semibold text-emerald-700">{msg.ocrResult.extractedInfo.result || 'Not detected'}</span>
                              </div>
                            </div>
                          </div>

                          {/* Expandable OCR Transcript View */}
                          {msg.ocrResult.rawText && (
                            <div className="pt-1">
                              <button
                                onClick={() => toggleTranscript(msg.id)}
                                className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1 cursor-pointer transition"
                              >
                                <FileText size={14} />
                                <span>{expandedTranscriptsMap[msg.id] ? 'Hide Full OCR Transcript' : 'View Full OCR Transcript'}</span>
                                {expandedTranscriptsMap[msg.id] ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                              </button>

                              {expandedTranscriptsMap[msg.id] && (
                                <div className="mt-2.5 p-3 bg-slate-900 text-slate-100 rounded-xl text-[11px] font-mono whitespace-pre-wrap max-h-60 overflow-y-auto leading-relaxed border border-slate-800 shadow-inner">
                                  <div className="text-[10px] text-slate-400 font-sans font-semibold uppercase mb-2 border-b border-slate-800 pb-1">
                                    Raw Extracted OCR Text Transcript
                                  </div>
                                  {msg.ocrResult.rawText}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {/* AI Response Narrative text with Evidence Citations */}
                      {msg.summaryNarrative && (
                        <div className="text-slate-800 text-sm leading-relaxed space-y-3 font-normal">
                          <p>
                            {msg.summaryNarrative.split(/(\[\d+\])/g).map((part, idx) => {
                              const match = part.match(/^\[(\d+)\]$/);
                              if (match) {
                                const evId = parseInt(match[1], 10);
                                return (
                                  <button
                                    key={idx}
                                    onClick={() => setActiveEvidenceId(evId)}
                                    className="inline-flex items-center px-1.5 py-0.5 mx-0.5 rounded bg-indigo-100 text-indigo-700 text-[11px] font-bold hover:bg-indigo-200 transition cursor-pointer"
                                    title="Click to view evidence citation"
                                  >
                                    [{evId}]
                                  </button>
                                );
                              }
                              return part;
                            })}
                          </p>

                          {/* Verification Verdict Box */}
                          {msg.trustScore !== undefined && msg.verdict && (
                            <div className={`p-4 rounded-2xl border flex items-center justify-between shadow-2xs ${
                              msg.verdict === 'genuine' ? 'bg-emerald-50/70 border-emerald-200/80' :
                              msg.verdict === 'suspicious' ? 'bg-amber-50/70 border-amber-200/80' :
                              'bg-rose-50/70 border-rose-200/80'
                            }`}>
                              <div>
                                <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-0.5">
                                  VERIFICATION RESULT
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className={`text-base font-bold capitalize ${
                                    msg.verdict === 'genuine' ? 'text-emerald-800' :
                                    msg.verdict === 'suspicious' ? 'text-amber-800' :
                                    'text-rose-800'
                                  }`}>
                                    {msg.verdict} Certificate
                                  </span>
                                  {msg.confidence && (
                                    <span className="text-xs text-slate-500 font-medium">
                                      ({msg.confidence}% confidence)
                                    </span>
                                  )}
                                </div>
                              </div>

                              <div className="text-right">
                                <div className="text-[10px] text-slate-500 font-medium uppercase">Trust Score</div>
                                <div className={`text-2xl font-bold font-mono ${
                                  msg.trustScore >= 85 ? 'text-emerald-700' :
                                  msg.trustScore >= 50 ? 'text-amber-700' :
                                  'text-rose-700'
                                }`}>
                                  {msg.trustScore} <span className="text-xs text-slate-400 font-normal">/ 100</span>
                                </div>
                              </div>
                            </div>
                          )}

                          {/* Suspicious / Fake Guidance Card */}
                          {msg.verdict === 'suspicious' && (
                            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 text-xs text-amber-900 space-y-2">
                              <div className="flex items-center gap-2 font-semibold">
                                <AlertTriangle size={15} className="text-amber-600" />
                                <span>I found several signals that require review:</span>
                              </div>
                              <ul className="list-disc list-inside space-y-1 text-amber-800 text-[11px]">
                                <li>⚠ QR Code payload cryptographic signature could not be verified</li>
                                <li>⚠ Font family and line spacing anomaly on marks row</li>
                              </ul>
                              <p className="text-[11px] font-medium pt-1">
                                Would you like me to investigate these signals further?
                              </p>
                            </div>
                          )}

                          {msg.verdict === 'fake' && (
                            <div className="bg-rose-50 border border-rose-200 rounded-xl p-3.5 text-xs text-rose-900 space-y-2">
                              <div className="flex items-center gap-2 font-semibold">
                                <XCircle size={15} className="text-rose-600" />
                                <span>CertiVerify identified high-risk forgery markers:</span>
                              </div>
                              <ul className="list-disc list-inside space-y-1 text-rose-800 text-[11px]">
                                <li>CRITICAL: QR Code points to unverified phishing domain</li>
                                <li>CRITICAL: Digital emblem compression noise matches copy-paste alteration</li>
                                <li>CRITICAL: Zero hash record exists on public or private ledger</li>
                              </ul>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Expandable 8-Signal Verification Activity Drawer */}
                      {msg.signals && msg.signals.length > 0 && (
                        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
                          <button
                            onClick={() => toggleSignals(msg.id)}
                            className="w-full px-4 py-2.5 flex items-center justify-between text-xs font-semibold text-slate-700 bg-slate-50/80 hover:bg-slate-100 transition cursor-pointer"
                          >
                            <div className="flex items-center gap-2">
                              <FileCheck size={14} className="text-indigo-600" />
                              <span>CertiVerify analyzed {msg.signals.length} verification signals</span>
                            </div>
                            {expandedSignalsMap[msg.id] ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                          </button>

                          {expandedSignalsMap[msg.id] && (
                            <div className="p-3.5 border-t border-slate-200 space-y-2.5 bg-white text-xs">
                              {msg.signals.map(sig => (
                                <div key={sig.id} className="flex items-center justify-between py-1 border-b border-slate-100 last:border-none">
                                  <div className="flex items-center gap-2">
                                    {sig.status === 'verified' && <CheckCircle2 size={13} className="text-emerald-600" />}
                                    {sig.status === 'warning' && <AlertTriangle size={13} className="text-amber-600" />}
                                    {sig.status === 'failed' && <XCircle size={13} className="text-rose-600" />}
                                    <span className="font-medium text-slate-800">{sig.name}</span>
                                  </div>
                                  <div className="flex items-center gap-3">
                                    <span className="text-[11px] text-slate-500 truncate max-w-[240px]">{sig.details}</span>
                                    <span className="font-mono text-[11px] font-semibold text-slate-700">{sig.confidence}%</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Contextual Action Buttons */}
                      {msg.contextualActions && msg.contextualActions.length > 0 && (
                        <div className="flex flex-wrap items-center gap-2 pt-1">
                          {msg.contextualActions.map(act => (
                            <button
                              key={act.id}
                              onClick={() => executeAction(act.action)}
                              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition flex items-center gap-1.5 cursor-pointer shadow-2xs ${
                                act.primary
                                  ? 'bg-indigo-600 hover:bg-indigo-700 text-white'
                                  : 'bg-white hover:bg-slate-100 text-slate-700 border border-slate-200'
                              }`}
                            >
                              {act.action === 'view_evidence' && <Eye size={13} />}
                              {act.action === 'generate_report' && <Maximize2 size={13} />}
                              {act.action === 'download_pdf' && <Download size={13} />}
                              <span>{act.label}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Integrated Prompt Input Dock */}
      <div className="p-4 bg-white border-t border-slate-200/80 shrink-0 z-10 shadow-lg shadow-slate-100">
        <div className="max-w-3xl mx-auto space-y-2">
          {/* File Upload Drop Overlay Indicator */}
          {isDragging && (
            <div className="absolute inset-0 bg-indigo-600/10 border-2 border-dashed border-indigo-600 backdrop-blur-xs flex items-center justify-center z-50 text-indigo-950 font-semibold text-sm rounded-xl">
              Drop certificate PDF or image to verify instantly
            </div>
          )}

          {/* Selected File Attachment Card inside Composer Dock */}
          {selectedFile && (
            <div className="bg-indigo-50/80 border border-indigo-200 rounded-xl p-2.5 flex items-center justify-between text-xs mb-1">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center shrink-0 shadow-xs">
                  <FileText size={18} />
                </div>
                <div className="min-w-0">
                  <p className="font-semibold text-slate-900 truncate">{selectedFile.name}</p>
                  <p className="text-[10px] text-slate-500">
                    {selectedFile.type.includes('pdf') ? 'PDF Document' : 'Document Image'} • {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedFile(null)}
                className="px-2 py-1 bg-white hover:bg-slate-100 text-slate-600 rounded-lg text-xs font-semibold border border-slate-200 transition cursor-pointer flex items-center gap-1 shadow-2xs"
                title="Remove attachment"
              >
                <span>Remove</span>
              </button>
            </div>
          )}

          <div className="bg-slate-50 border border-slate-200 rounded-2xl p-2.5 focus-within:border-indigo-500 focus-within:bg-white focus-within:ring-2 focus-within:ring-indigo-100 transition-all">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask CertiVerify anything... (e.g. 'Verify this certificate', 'Why is the trust score 96?', 'Show OCR transcript')"
              rows={2}
              className="w-full bg-transparent text-sm text-slate-900 placeholder-slate-400 focus:outline-none resize-none px-1 py-0.5"
            />

            <div className="flex items-center justify-between pt-2 border-t border-slate-200/60">
              {/* Attachment Actions */}
              <div className="flex items-center gap-1">
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  accept=".pdf,.png,.jpg,.jpeg"
                  className="hidden"
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="p-2 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg text-xs font-medium flex items-center gap-1 transition cursor-pointer"
                  title="Attach Document"
                >
                  <Paperclip size={15} />
                  <span className="hidden sm:inline">Attach</span>
                </button>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="p-2 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg text-xs font-medium flex items-center gap-1 transition cursor-pointer"
                  title="Upload Image"
                >
                  <ImageIcon size={15} />
                  <span className="hidden sm:inline">Image</span>
                </button>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="p-2 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg text-xs font-medium flex items-center gap-1 transition cursor-pointer"
                  title="Upload PDF"
                >
                  <FileText size={15} />
                  <span className="hidden sm:inline">PDF</span>
                </button>
              </div>

              {/* Input Action Controls */}
              <div className="flex items-center gap-2">
                <button
                  onClick={toggleVoice}
                  className={`p-2 rounded-xl transition cursor-pointer ${
                    isVoiceActive
                      ? 'bg-rose-100 text-rose-600 animate-pulse'
                      : 'text-slate-400 hover:text-slate-700 hover:bg-slate-200/60'
                  }`}
                  title="Voice Input"
                >
                  {isVoiceActive ? <MicOff size={16} /> : <Mic size={16} />}
                </button>
                <button
                  onClick={handleSend}
                  disabled={!input.trim() && !selectedFile}
                  className={`p-2.5 rounded-xl transition shadow-xs flex items-center justify-center cursor-pointer ${
                    (input.trim() || selectedFile)
                      ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                      : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                  }`}
                >
                  <Send size={16} />
                </button>
              </div>
            </div>
          </div>
          <p className="text-[11px] text-center text-slate-400">
            CertiVerify AI Engine v2.4 • Optical Forensic Verification & Multi-Ledger Check
          </p>
        </div>
      </div>
    </div>
  );
};
