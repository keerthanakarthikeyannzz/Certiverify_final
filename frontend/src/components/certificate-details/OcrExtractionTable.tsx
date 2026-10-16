"use client";

import React, { useState } from "react";
import {
  FileSpreadsheet,
  Pencil,
  Check,
  RotateCcw,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  XCircle,
  Sparkles,
} from "lucide-react";
import {
  OCRDataResponse,
  OCRDataUpdate,
  DocumentValidationResponse,
  FieldValidationItem,
} from "@/lib/api";
import { Badge, Button, Input } from "@/components/ui";

const TARGET_FIELDS: Array<{ key: keyof OCRDataUpdate; label: string }> = [
  { key: "student_name", label: "Student Name" },
  { key: "university_name", label: "University / Institute" },
  { key: "register_number", label: "Register Number" },
  { key: "roll_number", label: "Roll Number" },
  { key: "certificate_number", label: "Certificate Number" },
  { key: "department", label: "Department / Major" },
  { key: "course", label: "Degree / Course" },
  { key: "cgpa", label: "CGPA" },
  { key: "percentage", label: "Percentage" },
  { key: "date_of_issue", label: "Date of Issue" },
];

interface OcrExtractionTableProps {
  ocrData: OCRDataResponse | null;
  editValues: OCRDataUpdate;
  onChangeField: (key: keyof OCRDataUpdate, value: string) => void;
  onSave: () => void;
  onReset: () => void;
  saving: boolean;
  validation: DocumentValidationResponse | null;
}

export const OcrExtractionTable: React.FC<OcrExtractionTableProps> = ({
  ocrData,
  editValues,
  onChangeField,
  onSave,
  onReset,
  saving,
  validation,
}) => {
  const [isEditing, setIsEditing] = useState(false);

  const getFieldConfidence = (key: string): number | null => {
    if (!ocrData?.field_confidences) return null;
    const conf = ocrData.field_confidences[key];
    return typeof conf === "number" ? conf : null;
  };

  const getFieldValidation = (key: string): FieldValidationItem | undefined => {
    if (!validation?.field_validations) return undefined;
    return validation.field_validations.find((v) => v.field === key);
  };

  const statusBadge = (item?: FieldValidationItem) => {
    if (!item) return null;
    const s = item.status;
    switch (s) {
      case "VALID":
        return <Badge variant="genuine" size="sm">VALID</Badge>;
      case "INVALID":
        return <Badge variant="fake" size="sm">INVALID</Badge>;
      case "LOW_CONFIDENCE":
        return <Badge variant="suspicious" size="sm">REVIEW</Badge>;
      case "MISSING":
      case "NOT_DETECTED":
        return <Badge variant="neutral" size="sm">MISSING</Badge>;
      default:
        return <Badge variant="neutral" size="sm">{s}</Badge>;
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm space-y-0">
      {/* Table Header */}
      <div className="p-4 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50">
        <div className="flex items-center gap-2">
          <FileSpreadsheet size={16} className="text-primary" />
          <h3 className="text-xs font-semibold text-slate-800 uppercase tracking-wider font-mono">
            Extracted Field Ledger
          </h3>
          {ocrData?.ocr_accuracy != null && (
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-50 border border-emerald-200 text-emerald-700 font-semibold">
              {Math.round(ocrData.ocr_accuracy * 100)}% Confidence
            </span>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {isEditing ? (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  onReset();
                  setIsEditing(false);
                }}
                disabled={saving}
                icon={<RotateCcw size={12} />}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={async () => {
                  await onSave();
                  setIsEditing(false);
                }}
                disabled={saving}
                icon={saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              >
                {saving ? "Saving..." : "Save Changes"}
              </Button>
            </>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsEditing(true)}
              disabled={!ocrData}
              icon={<Pencil size={12} />}
            >
              Edit Fields
            </Button>
          )}
        </div>
      </div>

      {/* Main Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-mono text-[10px] uppercase tracking-wider">
            <tr>
              <th className="px-4 py-2.5 font-semibold">Target Field</th>
              <th className="px-4 py-2.5 font-semibold">Extracted Value</th>
              <th className="px-4 py-2.5 font-semibold text-center w-24">Confidence</th>
              <th className="px-4 py-2.5 font-semibold text-center w-28">Validation</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {TARGET_FIELDS.map(({ key, label }) => {
              const valItem = getFieldValidation(key);
              const conf = getFieldConfidence(key);
              const currentValue = editValues[key] !== undefined ? String(editValues[key]) : "";

              return (
                <tr key={key} className="hover:bg-slate-50/70 transition">
                  {/* Field Label */}
                  <td className="px-4 py-3 font-medium text-slate-700 whitespace-nowrap">
                    {label}
                  </td>

                  {/* Field Value / Input */}
                  <td className="px-4 py-3 font-mono text-slate-900">
                    {isEditing ? (
                      <Input
                        value={currentValue}
                        onChange={(e) => onChangeField(key, e.target.value)}
                        className="py-1 px-2 text-xs font-mono h-8"
                        placeholder={`Enter ${label.toLowerCase()}...`}
                      />
                    ) : (
                      <span className={currentValue ? "text-slate-900 font-medium" : "text-slate-400 italic"}>
                        {currentValue || "— Not detected —"}
                      </span>
                    )}
                  </td>

                  {/* Confidence */}
                  <td className="px-4 py-3 text-center whitespace-nowrap">
                    {conf != null ? (
                      <span
                        className={`font-mono text-[11px] font-semibold px-2 py-0.5 rounded ${
                          conf >= 0.8
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            : conf >= 0.5
                            ? "bg-amber-50 text-amber-700 border border-amber-200"
                            : "bg-rose-50 text-rose-700 border border-rose-200"
                        }`}
                      >
                        {Math.round(conf * 100)}%
                      </span>
                    ) : (
                      <span className="text-slate-400 font-mono text-[11px]">—</span>
                    )}
                  </td>

                  {/* Validation Badge */}
                  <td className="px-4 py-3 text-center whitespace-nowrap">
                    {statusBadge(valItem) || (
                      <span className="text-slate-400 font-mono text-[11px]">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer Info */}
      <div className="p-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-[11px] text-slate-500 font-mono">
        <span className="flex items-center gap-1">
          <Sparkles size={11} className="text-primary" />
          OCR Engine: {ocrData?.ocr_engine || "EasyOCR / Tesseract"}
        </span>
        <span>
          Schema: {validation?.document_type ? validation.document_type.replace(/_/g, " ") : "Standard Marksheet"}
        </span>
      </div>
    </div>
  );
};
