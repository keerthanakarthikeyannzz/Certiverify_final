"use client";

import React, { useState, useEffect } from "react";
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Eye,
  Info,
  Layers,
  Loader2,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import { certificateApi, verificationApi, api } from "@/lib/api";
import { Button } from "@/components/ui";

interface DocumentPreviewCanvasProps {
  certificateId: string;
  filename?: string;
  fileType?: string;
  hasElaHeatmap?: boolean;
}

export const DocumentPreviewCanvas: React.FC<DocumentPreviewCanvasProps> = ({
  certificateId,
  filename = "Certificate Document",
  fileType,
  hasElaHeatmap = false,
}) => {
  const [zoom, setZoom] = useState<number>(100);
  const [viewMode, setViewMode] = useState<"document" | "ela">("document");
  
  const [docBlobUrl, setDocBlobUrl] = useState<string | null>(null);
  const [docLoading, setDocLoading] = useState<boolean>(true);
  const [docError, setDocError] = useState<string | null>(null);
  const [detectedPdf, setDetectedPdf] = useState<boolean>(false);

  const [elaBlobUrl, setElaBlobUrl] = useState<string | null>(null);
  const [elaLoading, setElaLoading] = useState<boolean>(false);
  const [elaError, setElaError] = useState<string | null>(null);

  // Fetch document preview Blob
  const fetchDocBlob = async () => {
    setDocLoading(true);
    setDocError(null);
    try {
      const response = await api.get(`/api/v1/certificates/${certificateId}/preview`, {
        responseType: "blob",
      });
      const blob: Blob = response.data;
      if (!blob || blob.size === 0) {
        throw new Error("Received empty document file.");
      }

      const contentType = response.headers["content-type"] || blob.type || "";
      const isPdfType =
        contentType.toLowerCase().includes("pdf") ||
        (fileType ? fileType.toLowerCase() === "pdf" : filename.toLowerCase().endsWith(".pdf"));

      setDetectedPdf(isPdfType);

      const objectUrl = URL.createObjectURL(blob);
      setDocBlobUrl(objectUrl);
    } catch (err: unknown) {
      let statusDetail = "Unable to preview document.";
      if (err && typeof err === "object") {
        const axiosErr = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
        if (axiosErr.response?.status === 401) {
          statusDetail = "Status: 401 Unauthorized — Session expired or invalid token.";
        } else if (axiosErr.response?.status === 404) {
          statusDetail = "Status: 404 Not Found — The original certificate file could not be retrieved.";
        } else if (axiosErr.response?.status) {
          statusDetail = `Status: ${axiosErr.response.status} — ${axiosErr.response.data?.detail || "Failed to load file."}`;
        } else if (axiosErr.message) {
          statusDetail = axiosErr.message;
        }
      }
      setDocError(statusDetail);
    } finally {
      setDocLoading(false);
    }
  };

  useEffect(() => {
    let currentBlobUrl: string | null = null;
    let isSubscribed = true;

    const loadDoc = async () => {
      setDocLoading(true);
      setDocError(null);
      try {
        const response = await api.get(`/api/v1/certificates/${certificateId}/preview`, {
          responseType: "blob",
        });
        if (!isSubscribed) return;

        const blob: Blob = response.data;
        if (!blob || blob.size === 0) {
          throw new Error("Received empty document file.");
        }

        const contentType = response.headers["content-type"] || blob.type || "";
        const isPdfType =
          contentType.toLowerCase().includes("pdf") ||
          (fileType ? fileType.toLowerCase() === "pdf" : filename.toLowerCase().endsWith(".pdf"));

        setDetectedPdf(isPdfType);

        currentBlobUrl = URL.createObjectURL(blob);
        setDocBlobUrl(currentBlobUrl);
      } catch (err: unknown) {
        if (!isSubscribed) return;
        let statusDetail = "Unable to preview document.";
        if (err && typeof err === "object") {
          const axiosErr = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
          if (axiosErr.response?.status === 401) {
            statusDetail = "Status: 401 Unauthorized — Session expired or invalid token.";
          } else if (axiosErr.response?.status === 404) {
            statusDetail = "Status: 404 Not Found — Original file not stored.";
          } else if (axiosErr.response?.status) {
            statusDetail = `Status: ${axiosErr.response.status} — ${axiosErr.response.data?.detail || "Failed to load file."}`;
          } else if (axiosErr.message) {
            statusDetail = axiosErr.message;
          }
        }
        setDocError(statusDetail);
      } finally {
        if (isSubscribed) setDocLoading(false);
      }
    };

    loadDoc();

    return () => {
      isSubscribed = false;
      if (currentBlobUrl) {
        URL.revokeObjectURL(currentBlobUrl);
      }
    };
  }, [certificateId, filename, fileType]);

  // Fetch ELA heatmap Blob when toggled
  useEffect(() => {
    if (viewMode !== "ela") return;
    if (elaBlobUrl) return;

    let currentElaUrl: string | null = null;
    let isSubscribed = true;

    const loadEla = async () => {
      setElaLoading(true);
      setElaError(null);
      try {
        const response = await api.get(`/api/v1/verification/${certificateId}/ela-heatmap`, {
          responseType: "blob",
        });
        if (!isSubscribed) return;

        const blob: Blob = response.data;
        currentElaUrl = URL.createObjectURL(blob);
        setElaBlobUrl(currentElaUrl);
      } catch {
        if (!isSubscribed) return;
        setElaError("Error Level Analysis (ELA) heatmap is pending or unavailable for this file format.");
      } finally {
        if (isSubscribed) setElaLoading(false);
      }
    };

    loadEla();

    return () => {
      isSubscribed = false;
      if (currentElaUrl) {
        URL.revokeObjectURL(currentElaUrl);
      }
    };
  }, [viewMode, certificateId, elaBlobUrl]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm space-y-0">
      {/* Canvas Toolbar */}
      <div className="p-3.5 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-800 uppercase tracking-wider font-mono flex items-center gap-1.5">
            <Eye size={13} className="text-primary" />
            Inspection Canvas
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-600 truncate max-w-[200px]">
            {filename}
          </span>
        </div>

        {/* View Switcher & Zoom Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Layer switcher */}
          <div className="flex items-center bg-white p-0.5 rounded-lg border border-slate-200 text-xs">
            <button
              onClick={() => setViewMode("document")}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition ${
                viewMode === "document"
                  ? "bg-primary text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Document
            </button>
            <button
              onClick={() => setViewMode("ela")}
              className={`px-2.5 py-1 rounded-md text-xs font-medium flex items-center gap-1 transition ${
                viewMode === "ela"
                  ? "bg-primary text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
              title="View OpenCV Error Level Analysis Heatmap"
            >
              <Layers size={11} />
              <span>ELA Heatmap</span>
              {hasElaHeatmap && (
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              )}
            </button>
          </div>

          {/* Zoom controls */}
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
      </div>

      {/* Main Canvas Viewport */}
      <div className="relative min-h-[420px] max-h-[640px] bg-slate-100/80 overflow-auto flex items-center justify-center p-4">
        {/* Document Mode */}
        {viewMode === "document" && (
          <>
            {docLoading && (
              <div className="flex flex-col items-center gap-2 text-slate-500 text-xs py-16">
                <Loader2 size={24} className="animate-spin text-primary" />
                <span>Loading authenticated document preview…</span>
              </div>
            )}

            {docError && (
              <div className="max-w-md p-6 text-center space-y-3 bg-white border border-slate-200 rounded-xl shadow-xs">
                <AlertCircle size={28} className="text-amber-500 mx-auto" />
                <div>
                  <h4 className="text-sm font-semibold text-slate-900">Preview Not Renderable</h4>
                  <p className="text-xs text-slate-500 mt-1">{docError}</p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchDocBlob} icon={<RefreshCw size={12} />}>
                  Retry Loading
                </Button>
              </div>
            )}

            {!docLoading && !docError && docBlobUrl && (
              <div
                className="transition-transform duration-200 ease-out origin-center flex justify-center w-full"
                style={{ transform: `scale(${zoom / 100})` }}
              >
                {detectedPdf ? (
                  <iframe
                    src={docBlobUrl}
                    title={filename}
                    className="w-full h-[520px] rounded-lg border border-slate-200 bg-white shadow-sm"
                  />
                ) : (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img
                    src={docBlobUrl}
                    alt={filename}
                    className="max-w-full max-h-[520px] object-contain rounded-lg border border-slate-200 shadow-sm bg-white"
                  />
                )}
              </div>
            )}
          </>
        )}

        {/* ELA Heatmap Mode */}
        {viewMode === "ela" && (
          <>
            {elaLoading && (
              <div className="flex flex-col items-center gap-2 text-slate-500 text-xs py-16">
                <Loader2 size={24} className="animate-spin text-primary" />
                <span>Generating Error Level Analysis heatmap…</span>
              </div>
            )}

            {elaError && (
              <div className="max-w-md p-6 text-center space-y-3 bg-white border border-slate-200 rounded-xl shadow-xs">
                <Info size={28} className="text-primary mx-auto" />
                <div>
                  <h4 className="text-sm font-semibold text-slate-900">ELA Heatmap Pending</h4>
                  <p className="text-xs text-slate-500 mt-1">{elaError}</p>
                </div>
              </div>
            )}

            {!elaLoading && !elaError && elaBlobUrl && (
              <div
                className="transition-transform duration-200 ease-out origin-center flex justify-center w-full"
                style={{ transform: `scale(${zoom / 100})` }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={elaBlobUrl}
                  alt="Error Level Analysis Heatmap"
                  className="max-w-full max-h-[520px] object-contain rounded-lg border border-slate-200 shadow-sm bg-black"
                />
              </div>
            )}
          </>
        )}
      </div>

      {/* Forensic interpretation footer bar */}
      <div className="p-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
        <span className="flex items-center gap-1.5 text-[11px]">
          <Info size={12} className="text-primary shrink-0" />
          {viewMode === "document"
            ? "High-resolution vector document render"
            : "White/bright noise spikes in ELA indicate differing compression levels and localized tampering"}
        </span>
        <span className="font-mono text-[10px] text-slate-400">
          Render Engine: Browser Canvas Sandbox
        </span>
      </div>
    </div>
  );
};
