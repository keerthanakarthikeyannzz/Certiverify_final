"use client";

import React from "react";
import { FileText, X, UploadCloud, Layers } from "lucide-react";
import { Button } from "@/components/ui/Button";

interface StagedFilesListProps {
  pending: File[];
  pendingDocTypes: string[];
  uploading: boolean;
  onRemove: (index: number) => void;
  onUpload: () => void;
  onClearAll: () => void;
}

export const StagedFilesList: React.FC<StagedFilesListProps> = ({
  pending,
  pendingDocTypes,
  uploading,
  onRemove,
  onUpload,
  onClearAll,
}) => {
  if (pending.length === 0) return null;

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const totalBytes = pending.reduce((sum, f) => sum + f.size, 0);

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <Layers className="w-3.5 h-3.5" />
          </div>
          <h3 className="text-sm font-semibold text-slate-900">
            Staged for Ingestion ({pending.length} {pending.length === 1 ? "file" : "files"})
          </h3>
          <span className="text-xs text-slate-400">
            • {formatFileSize(totalBytes)} total
          </span>
        </div>

        <button
          type="button"
          onClick={onClearAll}
          disabled={uploading}
          className="text-xs text-slate-500 hover:text-red-600 transition-colors cursor-pointer disabled:opacity-50"
        >
          Clear all
        </button>
      </div>

      <div className="space-y-2 max-h-60 overflow-y-auto">
        {pending.map((file, idx) => {
          const docType = pendingDocTypes[idx];
          return (
            <div
              key={`${file.name}-${idx}`}
              className="flex items-center justify-between p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-xs hover:bg-slate-100/60 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                  <FileText className="w-4 h-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-slate-900 truncate">{file.name}</p>
                  <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-0.5">
                    <span>{formatFileSize(file.size)}</span>
                    {docType && (
                      <>
                        <span>•</span>
                        <span className="text-indigo-600 font-medium capitalize">
                          {docType.replace("_", " ")}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() => onRemove(idx)}
                disabled={uploading}
                className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors cursor-pointer shrink-0 disabled:opacity-50"
                aria-label={`Remove ${file.name}`}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>

      <div className="pt-2">
        <Button
          onClick={onUpload}
          loading={uploading}
          className="w-full flex items-center justify-center gap-2"
        >
          <UploadCloud className="w-4 h-4" />
          <span>Start Verification Pipeline ({pending.length})</span>
        </Button>
      </div>
    </div>
  );
};

export default StagedFilesList;
