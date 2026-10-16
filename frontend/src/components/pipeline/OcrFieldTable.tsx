"use client";

import React from "react";
import { Table, Check, Pencil, Loader2, RotateCcw, ShieldCheck } from "lucide-react";
import { OCRDataResponse, OCRDataUpdate } from "@/lib/api";
import { Button, Input } from "@/components/ui";

export const FIELD_LABELS: [keyof OCRDataUpdate, string][] = [
  ["student_name", "Student / Candidate Name"],
  ["university_name", "University / Institution"],
  ["register_number", "Register Number"],
  ["roll_number", "Roll Number"],
  ["certificate_number", "Certificate Serial"],
  ["department", "Department / Branch"],
  ["course", "Degree / Program"],
  ["cgpa", "Cumulative GPA (CGPA)"],
  ["percentage", "Marks Percentage"],
  ["date_of_issue", "Date of Issue / Passing"],
];

interface OcrFieldTableProps {
  ocrData: OCRDataResponse;
  editValues: OCRDataUpdate;
  saving?: boolean;
  onEditChange?: (key: keyof OCRDataUpdate, value: string) => void;
  onChangeField?: (key: keyof OCRDataUpdate, value: string) => void;
  onSaveCorrections?: () => void;
  onSave?: () => void;
  onReset?: () => void;
}

export function getSafeConfidence(
  confidences: Record<string, unknown> | undefined,
  fieldKey: string
): { pct: number | null; label: string; cls: string } {
  if (!confidences || !(fieldKey in confidences)) {
    return { pct: null, label: "—", cls: "text-slate-400 bg-slate-50 border-slate-200" };
  }

  const val = confidences[fieldKey];
  let num: number | null = null;

  if (typeof val === "number" && !isNaN(val)) {
    num = val <= 1.0 ? Math.round(val * 100) : Math.round(val);
  } else if (typeof val === "string") {
    const parsed = parseFloat(val);
    if (!isNaN(parsed)) {
      num = parsed <= 1.0 ? Math.round(parsed * 100) : Math.round(parsed);
    }
  }

  if (num === null) {
    return { pct: null, label: "—", cls: "text-slate-400 bg-slate-50 border-slate-200" };
  }

  if (num === 100) {
    return {
      pct: 100,
      label: "100% (Truth)",
      cls: "text-emerald-700 bg-emerald-50 border-emerald-200",
    };
  }

  if (num >= 80) {
    return {
      pct: num,
      label: `${num}%`,
      cls: "text-emerald-700 bg-emerald-50 border-emerald-200",
    };
  }

  if (num >= 50) {
    return {
      pct: num,
      label: `${num}%`,
      cls: "text-amber-700 bg-amber-50 border-amber-200",
    };
  }

  return {
    pct: num,
    label: `${num}%`,
    cls: "text-rose-700 bg-rose-50 border-rose-200",
  };
}

export const OcrFieldTable: React.FC<OcrFieldTableProps> = ({
  ocrData,
  editValues,
  saving = false,
  onEditChange,
  onChangeField,
  onSaveCorrections,
  onSave,
  onReset,
}) => {
  const handleChange = (key: keyof OCRDataUpdate, value: string) => {
    if (onChangeField) onChangeField(key, value);
    else if (onEditChange) onEditChange(key, value);
  };
  const handleSave = () => {
    if (onSave) onSave();
    else if (onSaveCorrections) onSaveCorrections();
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <Table size={16} className="text-primary" />
          <h2 className="text-xs font-semibold text-slate-800 uppercase tracking-wider font-mono">
            Extracted Structured Entities ({FIELD_LABELS.length} Fields)
          </h2>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          {onReset && (
            <Button
              variant="outline"
              size="sm"
              onClick={onReset}
              disabled={saving}
              icon={<RotateCcw size={11} />}
              title="Reset edits to original AI extraction"
            >
              Reset
            </Button>
          )}
          <Button
            variant="primary"
            size="sm"
            onClick={handleSave}
            disabled={saving}
            icon={saving ? <Loader2 size={12} className="animate-spin" /> : <Pencil size={12} />}
          >
            {saving ? "Saving..." : "Save Corrections"}
          </Button>
        </div>
      </div>

      {/* Table Container */}
      <div className="overflow-x-auto border border-slate-200 rounded-lg shadow-xs">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-50 text-slate-500 border-b border-slate-200 font-mono text-[10px] uppercase">
              <th className="py-2.5 px-3.5 w-1/3 font-semibold">Target Entity</th>
              <th className="py-2.5 px-3.5 w-1/2 font-semibold">
                Extracted Value (Editable)
              </th>
              <th className="py-2.5 px-3.5 w-1/6 text-right font-semibold">
                Confidence
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-800 font-sans">
            {FIELD_LABELS.map(([key, label]) => {
              const conf = getSafeConfidence(
                ocrData.field_confidences as Record<string, unknown>,
                key
              );
              const currentValue =
                (editValues[key] as string | number | undefined) ?? "";

              return (
                <tr key={key} className="hover:bg-slate-50/70 transition">
                  <td className="py-2.5 px-3.5 text-slate-700 font-medium text-xs">
                    {label}
                  </td>
                  <td className="py-2 px-3.5">
                    <Input
                      type="text"
                      value={currentValue}
                      onChange={(e) => handleChange(key, e.target.value)}
                      placeholder="— None Extracted —"
                      className="py-1 px-2 text-xs font-mono h-8"
                    />
                  </td>
                  <td className="py-2.5 px-3.5 text-right font-mono">
                    <span
                      className={`inline-block px-1.5 py-0.5 rounded border text-[10px] font-semibold ${conf.cls}`}
                    >
                      {conf.label}
                    </span>
                  </td>
                </tr>
              );
            })}

            {/* Special Security Fields */}
            <tr className="hover:bg-slate-50/70 transition bg-slate-50/40">
              <td className="py-2.5 px-3.5 text-slate-700 font-medium text-xs">Decoded QR Data</td>
              <td className="py-2.5 px-3.5 text-xs text-slate-600 font-mono break-all" colSpan={2}>
                {ocrData.qr_code_data || "Not detected in document"}
              </td>
            </tr>
            <tr className="hover:bg-slate-50/70 transition bg-slate-50/40">
              <td className="py-2.5 px-3.5 text-slate-700 font-medium text-xs">Official Signature</td>
              <td className="py-2.5 px-3.5 text-xs font-mono" colSpan={2}>
                {ocrData.has_signature ? (
                  <span className="text-emerald-700 flex items-center gap-1 font-semibold">
                    <Check size={12} /> Detected
                  </span>
                ) : (
                  <span className="text-slate-400">Not detected</span>
                )}
              </td>
            </tr>
            <tr className="hover:bg-slate-50/70 transition bg-slate-50/40">
              <td className="py-2.5 px-3.5 text-slate-700 font-medium text-xs">Official Seal</td>
              <td className="py-2.5 px-3.5 text-xs font-mono" colSpan={2}>
                {ocrData.has_seal ? (
                  <span className="text-emerald-700 flex items-center gap-1 font-semibold">
                    <Check size={12} /> Detected
                  </span>
                ) : (
                  <span className="text-slate-400">Not detected</span>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Ground Truth Note */}
      <div className="text-[11px] text-slate-500 font-sans flex items-center gap-1.5 pt-1">
        <ShieldCheck size={13} className="text-emerald-600 shrink-0" />
        <span>
          Saved manual corrections are automatically elevated to 100% confidence ground truth for
          subsequent fraud and cross-document comparison passes.
        </span>
      </div>
    </div>
  );
};
