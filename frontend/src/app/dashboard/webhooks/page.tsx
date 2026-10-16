"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Webhook,
  Plus,
  RefreshCw,
  Trash2,
  Play,
  History,
  AlertTriangle,
  Copy,
  Check,
  X,
  Lock,
} from "lucide-react";
import {
  webhookApi,
  getAccessToken,
  WebhookResponse,
  WebhookDeliveryResponse,
} from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";

export default function WebhooksPage() {
  const router = useRouter();
  const [webhooks, setWebhooks] = useState<WebhookResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Register Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [endpointUrl, setEndpointUrl] = useState("");
  const [selectedEvents, setSelectedEvents] = useState<string[]>([
    "verification.completed",
    "fraud.alert",
  ]);
  const [creating, setCreating] = useState(false);

  // Created Webhook Secret One-Time Display
  const [createdWebhook, setCreatedWebhook] = useState<WebhookResponse | null>(null);
  const [copiedSecret, setCopiedSecret] = useState(false);

  // Delivery History Drawer
  const [selectedWebhookId, setSelectedWebhookId] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDeliveryResponse[]>([]);
  const [loadingDeliveries, setLoadingDeliveries] = useState(false);

  // Test Delivery State
  const [testingId, setTestingId] = useState<string | null>(null);

  const ALL_EVENTS = [
    "verification.completed",
    "verification.failed",
    "fraud.alert",
    "tampering.detected",
    "duplicate.detected",
    "job.status_changed",
  ];

  const [permissionDenied, setPermissionDenied] = useState(false);

  const fetchWebhooks = useCallback(async () => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const { data } = await webhookApi.list();
      setWebhooks(data);
    } catch (err: unknown) {
      const apiErr = err as { response?: { status?: number; data?: { detail?: string } } };
      if (apiErr?.response?.status === 403) {
        setPermissionDenied(true);
      } else {
        setError(apiErr?.response?.data?.detail || "Failed to load webhooks.");
      }
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchWebhooks();
  }, [fetchWebhooks]);

  const handleRegisterWebhook = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!endpointUrl.trim()) return;
    setCreating(true);
    try {
      const { data } = await webhookApi.create({
        endpoint_url: endpointUrl,
        subscribed_events: selectedEvents,
      });
      setShowCreateModal(false);
      setEndpointUrl("");
      setCreatedWebhook(data); // Shows secret ONCE!
      await fetchWebhooks();
    } catch (err: unknown) {
      const apiErr = err as { response?: { data?: { detail?: string } } };
      alert(apiErr?.response?.data?.detail || "Failed to register webhook endpoint.");
    } finally {
      setCreating(false);
    }
  };

  const handleTestDelivery = async (webhookId: string) => {
    setTestingId(webhookId);
    try {
      const { data } = await webhookApi.testDelivery(webhookId);
      alert(`Test delivery completed!\nStatus Code: ${data.response_status || "N/A"}\nStatus: ${data.status}`);
      if (selectedWebhookId === webhookId) {
        handleViewDeliveries(webhookId);
      }
    } catch (err: unknown) {
      const apiErr = err as { response?: { data?: { detail?: string } } };
      alert(apiErr?.response?.data?.detail || "Test delivery failed.");
    } finally {
      setTestingId(null);
    }
  };

  const handleViewDeliveries = async (webhookId: string) => {
    setSelectedWebhookId(webhookId);
    setLoadingDeliveries(true);
    try {
      const { data } = await webhookApi.listDeliveries(webhookId);
      setDeliveries(data);
    } catch {
      setDeliveries([]);
    } finally {
      setLoadingDeliveries(false);
    }
  };

  const handleDeleteWebhook = async (webhookId: string) => {
    if (!window.confirm("Delete this webhook endpoint permanently?")) return;
    try {
      await webhookApi.delete(webhookId);
      if (selectedWebhookId === webhookId) setSelectedWebhookId(null);
      await fetchWebhooks();
    } catch {
      alert("Failed to delete webhook endpoint.");
    }
  };

  const handleToggleEvent = (event: string) => {
    setSelectedEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]
    );
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
            <span className="text-indigo-600 font-semibold">Webhooks</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2 tracking-tight">
            <Webhook size={22} className="text-indigo-600" />
            Enterprise Webhook Notifications Engine
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Configure HTTP POST endpoints to receive real-time cryptographic verification events and fraud alerts.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            onClick={() => setShowCreateModal(true)}
            variant="primary"
            size="sm"
            icon={<Plus size={14} />}
          >
            Register Webhook
          </Button>
          <Button
            onClick={fetchWebhooks}
            variant="ghost"
            size="sm"
            aria-label="Refresh webhooks"
            title="Refresh webhooks"
          >
            <RefreshCw size={14} />
          </Button>
        </div>
      </div>

      {permissionDenied ? (
        <Card className="border-rose-200 bg-rose-50/40 text-center p-8">
          <CardContent className="space-y-3">
            <Lock size={36} className="text-rose-600 mx-auto" />
            <h2 className="text-base font-bold text-slate-900">Access Restricted: Permission Denied</h2>
            <p className="text-xs text-slate-600 max-w-md mx-auto">
              Configuring webhooks requires the <code className="text-indigo-600 font-mono font-semibold">webhook:manage</code> permission scope. Please contact your organization owner or administrator.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Webhook Endpoints List (7 cols) */}
          <div className="lg:col-span-7 space-y-4">
            <Card>
              <CardHeader className="pb-3 border-b border-slate-100 flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-semibold text-slate-900">Registered Endpoints</CardTitle>
                  <CardDescription className="text-xs text-slate-500">
                    HTTP callback URLs for event telemetry.
                  </CardDescription>
                </div>
                <span className="text-xs font-mono text-slate-500">
                  Total: {webhooks.length}
                </span>
              </CardHeader>

              <CardContent className="p-0">
                {loading ? (
                  <div className="p-6 space-y-3">
                    {[...Array(4)].map((_, i) => (
                      <Skeleton key={i} className="h-20 w-full rounded-lg" />
                    ))}
                  </div>
                ) : error ? (
                  <div className="p-8 text-center text-xs text-rose-600 space-y-2">
                    <AlertTriangle size={24} className="mx-auto" />
                    <p>{error}</p>
                    <Button onClick={fetchWebhooks} variant="primary" size="sm" className="mt-2">
                      Retry Loading
                    </Button>
                  </div>
                ) : webhooks.length === 0 ? (
                  <div className="p-10">
                    <EmptyState
                      icon={<Webhook size={32} className="text-slate-400" />}
                      title="No Webhooks Configured"
                      description="Register a target endpoint URL to receive automated callbacks when verification jobs finish."
                      action={
                        <Button onClick={() => setShowCreateModal(true)} variant="primary" size="sm">
                          Register First Webhook
                        </Button>
                      }
                    />
                  </div>
                ) : (
                  <div className="divide-y divide-slate-100">
                    {webhooks.map((ep) => (
                      <div key={ep.id} className="p-4 space-y-3 hover:bg-slate-50/60 transition">
                        <div className="flex items-start justify-between gap-3">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <Badge variant={ep.active ? "genuine" : "neutral"} size="sm">
                                {ep.active ? "ACTIVE" : "INACTIVE"}
                              </Badge>
                              <span className="font-mono text-xs font-bold text-slate-900 break-all">
                                {ep.endpoint_url}
                              </span>
                            </div>
                            <div className="text-[11px] font-mono text-slate-400">
                              ID: {ep.id} | Registered: {new Date(ep.created_at).toLocaleDateString()}
                            </div>
                          </div>

                          <Button
                            onClick={() => handleDeleteWebhook(ep.id)}
                            variant="ghost"
                            size="sm"
                            aria-label="Delete Webhook"
                            title="Delete Webhook"
                            className="text-slate-400 hover:text-rose-600"
                          >
                            <Trash2 size={14} />
                          </Button>
                        </div>

                        {/* Subscribed Events Tags */}
                        <div className="flex flex-wrap gap-1.5">
                          {ep.subscribed_events.map((evt) => (
                            <span
                              key={evt}
                              className="font-mono text-[10px] px-2 py-0.5 bg-slate-100 text-slate-700 border border-slate-200 rounded"
                            >
                              {evt}
                            </span>
                          ))}
                        </div>

                        {/* Action Controls */}
                        <div className="flex items-center gap-2 pt-2 border-t border-slate-100 font-mono text-xs">
                          <Button
                            onClick={() => handleTestDelivery(ep.id)}
                            disabled={testingId === ep.id}
                            loading={testingId === ep.id}
                            variant="secondary"
                            size="sm"
                            icon={<Play size={11} />}
                          >
                            Test Ping
                          </Button>

                          <Button
                            onClick={() => handleViewDeliveries(ep.id)}
                            variant="ghost"
                            size="sm"
                            icon={<History size={11} />}
                          >
                            Delivery Log
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Right Column: Delivery Logs Panel (5 cols) */}
          <div className="lg:col-span-5">
            {selectedWebhookId ? (
              <Card className="sticky top-20">
                <CardHeader className="pb-3 border-b border-slate-100 flex flex-row items-center justify-between">
                  <div>
                    <span className="text-[10px] font-mono text-slate-400 uppercase block font-semibold">
                      DELIVERY LOG STREAM
                    </span>
                    <CardTitle className="text-xs font-mono font-bold text-slate-900 mt-0.5">
                      Webhook {selectedWebhookId.slice(0, 12)}…
                    </CardTitle>
                  </div>
                  <Button
                    onClick={() => setSelectedWebhookId(null)}
                    variant="ghost"
                    size="sm"
                    className="p-1 h-auto"
                  >
                    <X size={14} />
                  </Button>
                </CardHeader>

                <CardContent className="p-4">
                  {loadingDeliveries ? (
                    <div className="p-8 space-y-3">
                      {[...Array(3)].map((_, i) => (
                        <Skeleton key={i} className="h-16 w-full rounded-lg" />
                      ))}
                    </div>
                  ) : deliveries.length === 0 ? (
                    <div className="py-12 text-center text-xs text-slate-400">
                      No delivery attempts recorded yet for this webhook.
                    </div>
                  ) : (
                    <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
                      {deliveries.map((del) => (
                        <div
                          key={del.id}
                          className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs space-y-1.5 font-mono"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-indigo-700">{del.event_type}</span>
                            <Badge
                              variant={del.status === "DELIVERED" ? "genuine" : "fake"}
                              size="sm"
                            >
                              HTTP {del.response_status || "ERR"} ({del.status})
                            </Badge>
                          </div>

                          <div className="text-[10px] text-slate-500">
                            Attempt #{del.attempt_count} | Sent: {new Date(del.created_at).toLocaleTimeString()}
                          </div>

                          <pre className="p-2 bg-slate-900 text-slate-200 rounded text-[10px] overflow-x-auto max-h-24">
                            {JSON.stringify(del.payload, null, 2)}
                          </pre>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            ) : (
              <Card className="text-center p-8">
                <CardContent>
                  <p className="text-xs text-slate-500">
                    Select "Delivery Log" on any webhook to inspect delivery status, response codes, and payload logs.
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* Register Webhook Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 w-full max-w-md rounded-xl p-6 space-y-4 shadow-xl">
            <h2 className="text-base font-bold text-slate-900">Register Webhook Endpoint</h2>
            <form onSubmit={handleRegisterWebhook} className="space-y-4">
              <Input
                label="Endpoint URL (HTTPS)"
                type="url"
                required
                placeholder="https://api.yourdomain.com/webhooks/certiverify"
                value={endpointUrl}
                onChange={(e) => setEndpointUrl(e.target.value)}
              />

              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-700 block">Subscribed Events</label>
                <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                  {ALL_EVENTS.map((evt) => (
                    <label key={evt} className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedEvents.includes(evt)}
                        onChange={() => handleToggleEvent(evt)}
                        className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-600"
                      />
                      <span className="font-mono text-[11px]">{evt}</span>
                    </label>
                  ))}
                </div>
              </div>

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
                  {creating ? "Registering..." : "Register Endpoint"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* One-Time Webhook Secret Modal */}
      {createdWebhook?.secret && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-emerald-200 w-full max-w-lg rounded-xl p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-2 text-emerald-700 font-bold text-sm font-mono">
              <Lock size={16} />
              <span>WEBHOOK SECRET GENERATED</span>
            </div>

            <p className="text-xs text-slate-600">
              This HMAC secret is used to sign webhook POST signatures. Save it now as it will <strong>NEVER be shown again</strong>.
            </p>

            <div className="space-y-1 font-mono text-xs">
              <label className="text-[11px] text-slate-500 uppercase font-semibold block">HMAC Secret</label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={createdWebhook.secret}
                  className="w-full bg-slate-50 border border-emerald-300 text-emerald-800 font-mono text-xs p-2.5 rounded-lg font-semibold select-all focus:outline-none"
                />
                <Button
                  onClick={() => {
                    navigator.clipboard.writeText(createdWebhook.secret!);
                    setCopiedSecret(true);
                    setTimeout(() => setCopiedSecret(false), 2000);
                  }}
                  variant="primary"
                  size="sm"
                  icon={copiedSecret ? <Check size={14} /> : <Copy size={14} />}
                  className="shrink-0"
                >
                  {copiedSecret ? "Copied" : "Copy"}
                </Button>
              </div>
            </div>

            <div className="pt-2 text-right">
              <Button
                onClick={() => setCreatedWebhook(null)}
                variant="secondary"
                size="sm"
              >
                Done / Saved Secret
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
