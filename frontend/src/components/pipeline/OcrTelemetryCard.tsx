"use client";

import React from "react";
import { ScanText, Cpu, QrCode, PenTool, Stamp, Loader2, Sparkles } from "lucide-react";
import { OCRDataResponse } from "@/lib/api";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Button } from "@/components/ui";

interface OcrTelemetryCardProps {
  ocrData: OCRDataResponse | null;
  running: boolean;
  ocrStage: string | null;
  onRunOcr: () => void;
}

export const OcrTelemetryCard: React.FC<OcrTelemetryCardProps> = ({
  ocrData,
  running,
  ocrStage,
  onRunOcr,
}) => {
  const accuracyPct = ocrData ? Math.round(ocrData.ocr_accuracy * 100) : null;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <ScanText size={16} className="text-primary" />
          <h2 className="text-xs font-semibold text-slate-800 uppercase tracking-wider font-mono">
            Neural OCR Inference Engine
          </h2>
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={onRunOcr}
          disabled={running}
          icon={
            running ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Sparkles size={13} />
            )
          }
        >
          {running ? (ocrStage || "Processing...") : ocrData ? "Re-Run OCR Inference" : "Trigger OCR Extraction"}
        </Button>
      </div>

      {ocrData ? (
        <div className="space-y-4">
          {/* Top Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Accuracy */}
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5 space-y-2">
              <div className="flex items-center justify-between text-[11px] font-mono text-slate-500">
                <span className="uppercase">OCR Accuracy Index</span>
                <span className="text-emerald-700 font-bold">{accuracyPct}%</span>
              </div>
              <ProgressBar
                value={accuracyPct ?? 0}
                size="xs"
                variant={accuracyPct && accuracyPct >= 75 ? "emerald" : "amber"}
              />
              <p className="text-[10px] font-mono text-slate-400">
                Mean character & word confidence
              </p>
            </div>

            {/* Engine */}
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5 space-y-1">
              <span className="text-[11px] font-mono uppercase text-slate-500">Active Engine</span>
              <p className="text-sm font-bold font-mono text-primary flex items-center gap-1.5 pt-0.5">
                <Cpu size={14} />
                {ocrData.ocr_engine}
              </p>
              <p className="text-[10px] font-mono text-slate-400">
                Fused PyMuPDF + EasyOCR + Tesseract
              </p>
            </div>
          </div>

          {/* Forensic Detection Badges */}
          <div className="grid grid-cols-3 gap-2 pt-1">
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-center">
              <PenTool
                size={14}
                className={`mx-auto mb-1 ${
                  ocrData.has_signature ? "text-emerald-600" : "text-slate-400"
                }`}
              />
              <p className="text-[10px] font-mono uppercase text-slate-500">Signature</p>
              <p
                className={`text-[11px] font-mono font-bold mt-0.5 ${
                  ocrData.has_signature ? "text-emerald-700" : "text-slate-400"
                }`}
              >
                {ocrData.has_signature ? "Detected" : "Not Detected"}
              </p>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-center">
              <Stamp
                size={14}
                className={`mx-auto mb-1 ${
                  ocrData.has_seal ? "text-emerald-600" : "text-slate-400"
                }`}
              />
              <p className="text-[10px] font-mono uppercase text-slate-500">Seal / Stamp</p>
              <p
                className={`text-[11px] font-mono font-bold mt-0.5 ${
                  ocrData.has_seal ? "text-emerald-700" : "text-slate-400"
                }`}
              >
                {ocrData.has_seal ? "Detected" : "Not Detected"}
              </p>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-center">
              <QrCode
                size={14}
                className={`mx-auto mb-1 ${
                  ocrData.qr_code_data ? "text-emerald-600" : "text-slate-400"
                }`}
              />
              <p className="text-[10px] font-mono uppercase text-slate-500">QR Code</p>
              <p
                className={`text-[11px] font-mono font-bold mt-0.5 ${
                  ocrData.qr_code_data ? "text-emerald-700" : "text-slate-400"
                }`}
              >
                {ocrData.qr_code_data ? "Detected" : "Not Detected"}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="py-6 text-center text-xs text-slate-400 font-mono">
          Click Trigger OCR Extraction above to run character recognition.
        </div>
      )}
    </div>
  );
};
