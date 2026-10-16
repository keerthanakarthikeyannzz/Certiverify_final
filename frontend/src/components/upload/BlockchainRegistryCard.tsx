"use client";

import React, { useState } from "react";
import { Copy, Check, Hash, Cpu } from "lucide-react";
import { CertificateResponse } from "@/lib/api";

interface BlockchainRegistryCardProps {
  latestCertificate?: CertificateResponse | null;
}

export const BlockchainRegistryCard: React.FC<BlockchainRegistryCardProps> = ({
  latestCertificate,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopyHash = () => {
    if (!latestCertificate?.sha256_hash) return;
    navigator.clipboard.writeText(latestCertificate.sha256_hash);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
      {/* Card Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
            <Cpu size={15} />
          </div>
          <h2 className="text-sm font-semibold text-slate-900 tracking-tight">
            Cryptographic Fingerprint & Ledger
          </h2>
        </div>
        <span className="text-[11px] font-medium px-2 py-0.5 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-700">
          ACTIVE
        </span>
      </div>

      {/* Network & Ledger Specs */}
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="bg-slate-50 border border-slate-100 rounded-xl p-3">
          <p className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Protocol</p>
          <p className="text-xs font-semibold text-slate-800 mt-0.5">
            EVM Smart Contract
          </p>
        </div>
        <div className="bg-slate-50 border border-slate-100 rounded-xl p-3">
          <p className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">Digest Algorithm</p>
          <p className="text-xs font-semibold text-emerald-700 font-mono mt-0.5">
            SHA-256 (256-bit)
          </p>
        </div>
      </div>

      {/* Latest Ingested Document Anchor */}
      {latestCertificate ? (
        <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700 flex items-center gap-1">
              <Hash size={13} className="text-indigo-600" />
              Latest Hash Digest
            </span>
            <button
              onClick={handleCopyHash}
              className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 transition-colors cursor-pointer"
            >
              {copied ? (
                <>
                  <Check size={12} className="text-emerald-600" />
                  <span className="text-emerald-600">Copied</span>
                </>
              ) : (
                <>
                  <Copy size={12} />
                  <span>Copy</span>
                </>
              )}
            </button>
          </div>
          <p className="text-[11px] font-mono text-slate-600 break-all bg-white p-2 rounded-lg border border-slate-200">
            {latestCertificate.sha256_hash}
          </p>
          <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
            <span className="truncate max-w-[200px]">{latestCertificate.original_filename}</span>
            <span>{new Date(latestCertificate.uploaded_at).toLocaleDateString()}</span>
          </div>
        </div>
      ) : (
        <div className="bg-slate-50 border border-dashed border-slate-200 rounded-xl p-4 text-center">
          <p className="text-xs text-slate-400">
            Upload a certificate to anchor its cryptographic SHA-256 fingerprint.
          </p>
        </div>
      )}
    </div>
  );
};

export default BlockchainRegistryCard;
