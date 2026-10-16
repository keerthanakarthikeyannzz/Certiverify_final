"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Cpu,
  RefreshCw,
  ExternalLink,
  Play,
  RotateCcw,
  FileQuestion,
} from "lucide-react";
import {
  certificateApi,
  jobsApi,
  getAccessToken,
  CertificateResponse,
  VerificationJobResponse,
} from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
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

export default function VerificationJobsPage() {
  const router = useRouter();
  const [certificates, setCertificates] = useState<CertificateResponse[]>([]);
  const [jobs, setJobs] = useState<Record<string, VerificationJobResponse | null>>({});
  const [loading, setLoading] = useState(true);
  const [actionJobId, setActionJobId] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    setLoading(true);
    try {
      const { data: certs } = await certificateApi.list();
      setCertificates(certs);

      // Fetch latest job status for each certificate
      const jobMap: Record<string, VerificationJobResponse | null> = {};
      await Promise.allSettled(
        certs.map(async (c) => {
          try {
            const { data } = await jobsApi.getLatestJobForCertificate(c.id);
            jobMap[c.id] = data;
          } catch {
            jobMap[c.id] = null;
          }
        })
      );
      setJobs(jobMap);
    } catch {
      // ignore errors
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const handleStartJob = async (certId: string) => {
    setActionJobId(certId);
    try {
      await jobsApi.startVerificationJob(certId);
      await fetchJobs();
    } catch {
      alert("Failed to start async verification job.");
    } finally {
      setActionJobId(null);
    }
  };

  const handleRetryJob = async (jobId: string) => {
    setActionJobId(jobId);
    try {
      await jobsApi.retryJob(jobId);
      await fetchJobs();
    } catch {
      alert("Failed to retry verification job.");
    } finally {
      setActionJobId(null);
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white border border-slate-200 p-6 rounded-xl shadow-sm">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 mb-1.5">
            <Link href="/dashboard" className="hover:text-indigo-600 transition-colors">
              Dashboard
            </Link>
            <span>/</span>
            <span className="text-indigo-600 font-semibold">Verification Jobs</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2 tracking-tight">
            <Cpu size={22} className="text-indigo-600" />
            Async Verification Job Execution Queue
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Monitor multi-stage asynchronous verification pipelines across ingested credentials.
          </p>
        </div>

        <Button
          onClick={fetchJobs}
          variant="ghost"
          size="sm"
          aria-label="Refresh jobs status"
          title="Refresh jobs status"
        >
          <RefreshCw size={14} />
        </Button>
      </div>

      {/* Main Jobs Table */}
      <Card>
        <CardHeader className="pb-3 border-b border-slate-100 flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-sm font-semibold text-slate-900">Pipeline Jobs</CardTitle>
            <CardDescription className="text-xs text-slate-500">
              Background job processing telemetry.
            </CardDescription>
          </div>
          <span className="text-xs font-mono text-slate-500">
            Total Certificates: {certificates.length}
          </span>
        </CardHeader>

        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-14 w-full rounded-lg" />
              ))}
            </div>
          ) : certificates.length === 0 ? (
            <div className="p-10">
              <EmptyState
                icon={<FileQuestion size={32} className="text-slate-400" />}
                title="No verification jobs in queue"
                description="Upload certificates to begin background queue execution."
                action={
                  <Link href="/dashboard/upload">
                    <Button variant="primary" size="sm">
                      Upload Certificate
                    </Button>
                  </Link>
                }
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50 text-slate-500 font-mono text-[10px] uppercase">
                    <TableHead className="px-5 py-3">Certificate / Job ID</TableHead>
                    <TableHead className="px-5 py-3">Job Status</TableHead>
                    <TableHead className="px-5 py-3">Current Stage</TableHead>
                    <TableHead className="px-5 py-3">Progress</TableHead>
                    <TableHead className="px-5 py-3">Created / Completed</TableHead>
                    <TableHead className="px-5 py-3 text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {certificates.map((cert) => {
                    const job = jobs[cert.id];
                    const status = job?.status || "NOT_STARTED";
                    const isActioning = Boolean(actionJobId === cert.id || (job?.id && actionJobId === job.id));

                    const badgeVariant =
                      status === "COMPLETED"
                        ? "genuine"
                        : status === "PROCESSING" || status === "QUEUED"
                        ? "suspicious"
                        : status === "FAILED"
                        ? "fake"
                        : "neutral";

                    return (
                      <TableRow key={cert.id} className="hover:bg-slate-50/70 transition-colors">
                        <TableCell className="px-5 py-3.5">
                          <div className="font-semibold text-slate-900 truncate max-w-xs">
                            {cert.original_filename}
                          </div>
                          <div className="font-mono text-[10px] text-slate-400">
                            Job: {job?.job_id || job?.id || "None"}
                          </div>
                        </TableCell>

                        <TableCell className="px-5 py-3.5 whitespace-nowrap">
                          <Badge variant={badgeVariant} size="sm">
                            {status}
                          </Badge>
                        </TableCell>

                        <TableCell className="px-5 py-3.5 font-mono text-xs text-indigo-700 font-medium">
                          {job?.current_stage || "Ready"}
                        </TableCell>

                        <TableCell className="px-5 py-3.5 font-mono text-xs">
                          <div className="flex items-center gap-2 max-w-[140px]">
                            <div className="h-2 flex-1 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                              <div
                                style={{ width: `${job?.progress_percentage ?? 0}%` }}
                                className="bg-indigo-600 h-full transition-all"
                              />
                            </div>
                            <span className="text-slate-600 font-semibold">{job?.progress_percentage ?? 0}%</span>
                          </div>
                        </TableCell>

                        <TableCell className="px-5 py-3.5 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                          {job?.created_at ? new Date(job.created_at).toLocaleString() : "Not triggered"}
                        </TableCell>

                        <TableCell className="px-5 py-3.5 text-right whitespace-nowrap">
                          <div className="inline-flex items-center gap-2 justify-end">
                            {!job || status === "NOT_STARTED" ? (
                              <Button
                                onClick={() => handleStartJob(cert.id)}
                                disabled={isActioning}
                                loading={isActioning}
                                variant="primary"
                                size="sm"
                                icon={<Play size={11} />}
                              >
                                Start Job
                              </Button>
                            ) : status === "FAILED" ? (
                              <Button
                                onClick={() => handleRetryJob(job.id)}
                                disabled={isActioning}
                                loading={isActioning}
                                variant="secondary"
                                size="sm"
                                icon={<RotateCcw size={11} />}
                              >
                                Retry
                              </Button>
                            ) : null}

                            <Link
                              href={`/dashboard/certificates/${cert.id}`}
                              className="p-1.5 text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 rounded transition-colors"
                              title="Open Cockpit"
                            >
                              <ExternalLink size={14} />
                            </Link>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
