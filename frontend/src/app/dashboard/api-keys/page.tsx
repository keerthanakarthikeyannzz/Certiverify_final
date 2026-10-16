"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Key,
  Plus,
  RefreshCw,
  Copy,
  Check,
  AlertTriangle,
  Lock,
} from "lucide-react";
import {
  apiKeyApi,
  getAccessToken,
  ApiKeyResponse,
  ApiKeyCreateResponse,
} from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import {
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableHeader,
  TableCell,
} from "@/components/ui/Table";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";

export default function ApiKeysPage() {
  const router = useRouter();
  const [keys, setKeys] = useState<ApiKeyResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create Key Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [keyName, setKeyName] = useState("");
  const [rateLimit, setRateLimit] = useState(100);
  const [creating, setCreating] = useState(false);

  // One-time Raw Key Modal
  const [createdKey, setCreatedKey] = useState<ApiKeyCreateResponse | null>(null);
  const [copiedRawKey, setCopiedRawKey] = useState(false);

  const [permissionDenied, setPermissionDenied] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const fetchKeys = useCallback(async () => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const { data } = await apiKeyApi.list();
      setKeys(data);
    } catch (err: unknown) {
      const apiErr = err as { response?: { status?: number; data?: { detail?: string } } };
      if (apiErr?.response?.status === 403) {
        setPermissionDenied(true);
      } else {
        setError(apiErr?.response?.data?.detail || "Failed to load API keys.");
      }
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyName.trim()) return;
    setCreating(true);
    try {
      const { data } = await apiKeyApi.create({
        name: keyName,
        permissions: ["certificate:read", "certificate:verify"],
        rate_limit: Number(rateLimit),
      });
      setShowCreateModal(false);
      setKeyName("");
      setCreatedKey(data); // Shows one-time display modal!
      await fetchKeys();
    } catch (err: unknown) {
      const apiErr = err as { response?: { data?: { detail?: string } } };
      alert(apiErr?.response?.data?.detail || "Failed to generate API key.");
    } finally {
      setCreating(false);
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    const confirmed = window.confirm(
      "Are you sure you want to revoke this API Key?\n\nAny external integrations using this key will immediately lose access."
    );
    if (!confirmed) return;

    setRevokingId(keyId);
    try {
      await apiKeyApi.revoke(keyId);
      await fetchKeys();
    } catch (err: unknown) {
      const apiErr = err as { response?: { data?: { detail?: string } } };
      alert(apiErr?.response?.data?.detail || "Failed to revoke API key.");
    } finally {
      setRevokingId(null);
    }
  };

  const handleCopyRawKey = () => {
    if (!createdKey?.raw_key) return;
    navigator.clipboard.writeText(createdKey.raw_key);
    setCopiedRawKey(true);
    setTimeout(() => setCopiedRawKey(false), 2000);
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white border border-slate-200 p-6 rounded-xl shadow-sm">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1.5">
            <Link href="/dashboard" className="hover:text-indigo-600 transition-colors">
              Dashboard
            </Link>
            <span>/</span>
            <span className="text-indigo-600 font-semibold">API Keys</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2 tracking-tight">
            <Key size={22} className="text-indigo-600" />
            Enterprise API Keys Management
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Generate and manage API keys for programmatic verification ingestion and webhook integrations.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            onClick={() => setShowCreateModal(true)}
            variant="primary"
            size="sm"
            icon={<Plus size={14} />}
          >
            Generate New Key
          </Button>
          <Button
            onClick={fetchKeys}
            variant="ghost"
            size="sm"
            aria-label="Refresh keys"
            title="Refresh keys"
          >
            <RefreshCw size={14} />
          </Button>
        </div>
      </div>

      {/* Main Keys Table or Permission Denied */}
      {permissionDenied ? (
        <Card className="border-rose-200 bg-rose-50/40 text-center p-8">
          <CardContent className="space-y-3">
            <Lock size={36} className="text-rose-600 mx-auto" />
            <h2 className="text-base font-bold text-slate-900">Access Restricted: Permission Denied</h2>
            <p className="text-xs text-slate-600 max-w-md mx-auto">
              Managing API keys requires the <code className="text-indigo-600 font-mono font-semibold">api_key:write</code> permission scope. Please contact your organization owner or administrator.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="pb-3 border-b border-slate-100 flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-sm font-semibold text-slate-900">Active API Keys</CardTitle>
              <CardDescription className="text-xs text-slate-500">
                Programmatic access tokens issued for your tenant.
              </CardDescription>
            </div>
            <span className="text-xs font-mono text-slate-500">
              Total Keys: {keys.length}
            </span>
          </CardHeader>

          <CardContent className="p-0">
            {loading ? (
              <div className="p-6 space-y-3">
                {[...Array(4)].map((_, i) => (
                  <Skeleton key={i} className="h-14 w-full rounded-lg" />
                ))}
              </div>
            ) : error ? (
              <div className="p-8 text-center text-xs text-rose-600 space-y-2">
                <AlertTriangle size={24} className="mx-auto" />
                <p>{error}</p>
                <Button onClick={fetchKeys} variant="primary" size="sm" className="mt-2">
                  Retry Loading
                </Button>
              </div>
            ) : keys.length === 0 ? (
              <div className="p-10">
                <EmptyState
                  icon={<Key size={32} className="text-slate-400" />}
                  title="No API Keys Generated"
                  description="Create an API key to allow external systems to ingest certificates and query verification status."
                  action={
                    <Button onClick={() => setShowCreateModal(true)} variant="primary" size="sm">
                      Generate First API Key
                    </Button>
                  }
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50 text-[10px] uppercase font-mono text-slate-500">
                      <TableHead className="px-5 py-3">Key Name</TableHead>
                      <TableHead className="px-5 py-3">Key Prefix</TableHead>
                      <TableHead className="px-5 py-3">Rate Limit</TableHead>
                      <TableHead className="px-5 py-3">Status</TableHead>
                      <TableHead className="px-5 py-3">Created</TableHead>
                      <TableHead className="px-5 py-3">Last Used</TableHead>
                      <TableHead className="px-5 py-3 text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {keys.map((k) => (
                      <TableRow key={k.id} className="hover:bg-slate-50/70 transition">
                        <TableCell className="px-5 py-3.5 font-semibold text-slate-900">
                          {k.name}
                        </TableCell>

                        <TableCell className="px-5 py-3.5 font-mono text-xs text-indigo-700 font-medium">
                          {k.key_prefix}••••••••
                        </TableCell>

                        <TableCell className="px-5 py-3.5 font-mono text-xs text-slate-500">
                          {k.rate_limit} req/min
                        </TableCell>

                        <TableCell className="px-5 py-3.5 whitespace-nowrap">
                          <Badge variant={k.status === "active" ? "genuine" : "fake"} size="sm">
                            {k.status}
                          </Badge>
                        </TableCell>

                        <TableCell className="px-5 py-3.5 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                          {new Date(k.created_at).toLocaleDateString()}
                        </TableCell>

                        <TableCell className="px-5 py-3.5 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                          {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "Never"}
                        </TableCell>

                        <TableCell className="px-5 py-3.5 text-right whitespace-nowrap">
                          {k.status === "active" && (
                            <Button
                              onClick={() => handleRevokeKey(k.id)}
                              disabled={revokingId === k.id}
                              variant="danger"
                              size="sm"
                              className="text-xs"
                            >
                              {revokingId === k.id ? "Revoking..." : "Revoke"}
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Create Key Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 w-full max-w-md rounded-xl p-6 space-y-4 shadow-xl">
            <h2 className="text-base font-bold text-slate-900">Generate Enterprise API Key</h2>
            <form onSubmit={handleCreateKey} className="space-y-4">
              <Input
                label="Key Name / Description"
                type="text"
                required
                placeholder="e.g. Production Ingestion Service"
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
              />

              <Input
                label="Rate Limit (requests / minute)"
                type="number"
                min={10}
                max={10000}
                value={rateLimit}
                onChange={(e) => setRateLimit(Number(e.target.value))}
              />

              <div className="flex items-center justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={creating}
                  loading={creating}
                >
                  {creating ? "Generating..." : "Generate Key"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* One-Time Display Modal for Secret Key */}
      {createdKey && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-emerald-200 w-full max-w-lg rounded-xl p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-2 text-emerald-700 font-bold text-sm font-mono">
              <Lock size={16} />
              <span>API KEY GENERATED SUCCESSFULLY</span>
            </div>

            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 space-y-1">
              <strong className="block font-bold">IMPORTANT SECURITY NOTICE:</strong>
              <p>
                Save this key in a secure location now. For security, it will <strong>NEVER be displayed again</strong>.
              </p>
            </div>

            <div className="space-y-1.5 font-mono text-xs">
              <label className="text-[11px] text-slate-500 uppercase font-semibold block">
                Raw API Key
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={createdKey.raw_key}
                  className="w-full bg-slate-50 border border-emerald-300 text-emerald-800 font-mono text-xs p-2.5 rounded-lg font-semibold select-all focus:outline-none"
                />
                <Button
                  onClick={handleCopyRawKey}
                  variant="primary"
                  size="sm"
                  icon={copiedRawKey ? <Check size={14} /> : <Copy size={14} />}
                  className="shrink-0"
                >
                  {copiedRawKey ? "Copied" : "Copy"}
                </Button>
              </div>
            </div>

            <div className="pt-2 text-right">
              <Button
                onClick={() => setCreatedKey(null)}
                variant="secondary"
                size="sm"
              >
                Done / I Have Saved My Key
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
