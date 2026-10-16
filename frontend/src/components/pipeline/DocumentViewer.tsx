"use client";

import React, { useState, useEffect, useCallback } from "react";
import { ZoomIn, ZoomOut, RotateCcw, Eye, Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { certificateApi, api } from "@/lib/api";
import { Button } from "@/components/ui";

interface DocumentViewerProps {
  certificateId?: string;
  originalFilename?: string;
  filename?: string;
  fileType?: string;
}

export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  certificateId,
  originalFilename,
  filename,
  fileType,
}) => {
  const activeFilename = filename || originalFilename || "Certificate Document";
  const [zoom, setZoom] = useState<number>(100);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!certificateId);
  const [error, setError] = useState<string | null>(null);
  const [detectedPdf, setDetectedPdf] = useState<boolean>(false);

  const fetchDocument = useCallback(async () => {
    if (!certificateId) {
      setLoading(false);
      setBlobUrl(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await api.get(`/api/v1/certificates/${certificateId}/preview`, {
        responseType: "blob",
        timeout: 15000,
      });

      const blob: Blob = response.data;
      if (!blob || blob.size === 0) {
        throw new Error("Received empty document file.");
      }

      const contentType = response.headers["content-type"] || blob.type || "";
      const isPdfType =
        contentType.toLowerCase().includes("pdf") ||
        (fileType ? fileType.toLowerCase() === "pdf" : activeFilename.toLowerCase().endsWith(".pdf"));

      setDetectedPdf(isPdfType);

      const objectUrl = URL.createObjectURL(blob);
      setBlobUrl(objectUrl);
    } catch (err: unknown) {
      let statusDetail = "Unable to load document preview.";
      if (err && typeof err === "object") {
        const axiosErr = err as {
          response?: { status?: number; data?: { detail?: string } };
          message?: string;
          code?: string;
        };
        if (axiosErr.code === "ECONNABORTED" || axiosErr.message?.includes("timeout")) {
          statusDetail = "Preview request timed out. Click Retry Load to attempt again.";
        } else if (axiosErr.response?.status === 401) {
          statusDetail = "Status: 401 Unauthorized — Session expired or invalid token.";
        } else if (axiosErr.response?.status === 404) {
          statusDetail = "Status: 404 Not Found — Original certificate file not found in storage.";
        } else if (axiosErr.response?.status) {
          statusDetail = `Status: ${axiosErr.response.status} — ${axiosErr.response.data?.detail || "Failed to retrieve certificate."}`;
        } else if (axiosErr.message) {
          statusDetail = axiosErr.message;
        }
      }
      setError(statusDetail);
    } finally {
      setLoading(false);
    }
  }, [certificateId, activeFilename, fileType]);

  useEffect(() => {
    fetchDocument();
  }, [fetchDocument]);

  useEffect(() => {
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [blobUrl]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm space-y-0">
      {/* Top Bar */}
      <div className="p-3.5 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50">
        <div className="flex items-center gap-2">
          <Eye size={14} className="text-primary" />
          <span className="text-xs font-semibold text-slate-800 uppercase tracking-wider font-mono">
            Document Viewport
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-600 truncate max-w-[200px]">
            {activeFilename}
          </span>
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-1 bg-white px-2 py-1 rounded-lg border border-slate-200 text-xs">
          <button
            onClick={() => setZoom((z) => Math.max(50, z - 15))}
            className="text-slate-500 hover:text-slate-900 transition p-0.5"
            title="Zoom Out"
          >
            <ZoomOut size={13} />
          </button>
          <span className="font-mono text-[11px] text-slate-700 w-9 text-center font-semibold">
            {zoom}%
          </span>
          <button
            onClick={() => setZoom((z) => Math.min(200, z + 15))}
            className="text-slate-500 hover:text-slate-900 transition p-0.5"
            title="Zoom In"
          >
            <ZoomIn size={13} />
          </button>
          <button
            onClick={() => setZoom(100)}
            className="text-slate-400 hover:text-slate-700 transition p-0.5 border-l border-slate-200 pl-1.5 ml-1"
            title="Reset Zoom"
          >
            <RotateCcw size={12} />
          </button>
        </div>
      </div>

      {/* Main Preview Area */}
      <div className="relative min-h-[420px] max-h-[640px] bg-slate-100/80 overflow-auto flex items-center justify-center p-4">
        {loading && (
          <div className="flex flex-col items-center gap-2 text-slate-500 text-xs py-16">
            <Loader2 size={24} className="animate-spin text-primary" />
            <span>Loading authenticated document preview…</span>
          </div>
        )}

        {error && (
          <div className="max-w-md p-6 text-center space-y-3 bg-white border border-slate-200 rounded-xl shadow-xs">
            <AlertCircle size={28} className="text-amber-500 mx-auto" />
            <div>
              <h4 className="text-sm font-semibold text-slate-900">Preview Not Renderable</h4>
              <p className="text-xs text-slate-500 mt-1">{error}</p>
            </div>
            <Button variant="outline" size="sm" onClick={fetchDocument} icon={<RefreshCw size={12} />}>
              Retry Load
            </Button>
          </div>
        )}

        {!loading && !error && blobUrl && (
          <div
            className="transition-transform duration-200 ease-out origin-center flex justify-center w-full"
            style={{ transform: `scale(${zoom / 100})` }}
          >
            {detectedPdf ? (
              <iframe
                src={blobUrl}
                title={activeFilename}
                className="w-full h-[520px] rounded-lg border border-slate-200 bg-white shadow-sm"
              />
            ) : (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={blobUrl}
                alt={activeFilename}
                className="max-w-full max-h-[520px] object-contain rounded-lg border border-slate-200 shadow-sm bg-white"
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
};
