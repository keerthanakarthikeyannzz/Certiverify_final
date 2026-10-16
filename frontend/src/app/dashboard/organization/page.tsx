"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Building2,
  Users,
  Plus,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import {
  orgApi,
  getAccessToken,
  OrganizationResponse,
  OrganizationMemberResponse,
} from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
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

export default function OrganizationPage() {
  const router = useRouter();
  const [org, setOrg] = useState<OrganizationResponse | null>(null);
  const [members, setMembers] = useState<OrganizationMemberResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New org modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [creating, setCreating] = useState(false);

  const fetchOrgData = useCallback(async () => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [orgRes, membersRes] = await Promise.allSettled([
        orgApi.getMyOrg(),
        orgApi.getMembers(),
      ]);

      if (orgRes.status === "fulfilled") setOrg(orgRes.value.data);
      else setError("No organization found for current account.");

      if (membersRes.status === "fulfilled") setMembers(membersRes.value.data || []);
    } catch {
      setError("Failed to load organization data.");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchOrgData();
  }, [fetchOrgData]);

  const handleCreateOrg = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newOrgName.trim()) return;
    setCreating(true);
    try {
      await orgApi.create({ name: newOrgName });
      setShowCreateModal(false);
      setNewOrgName("");
      await fetchOrgData();
    } catch (err: unknown) {
      const apiErr = err as { response?: { data?: { detail?: string } } };
      alert(apiErr?.response?.data?.detail || "Failed to create organization.");
    } finally {
      setCreating(false);
    }
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
            <span className="text-indigo-600 font-semibold">Organizations & Members</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2 tracking-tight">
            <Building2 size={22} className="text-indigo-600" />
            Organization Management & Governance
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Manage current tenant workspace, role-based access control (RBAC), and team members.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            onClick={() => setShowCreateModal(true)}
            variant="primary"
            size="sm"
            icon={<Plus size={14} />}
          >
            Create Organization
          </Button>
          <Button
            onClick={fetchOrgData}
            variant="ghost"
            size="sm"
            aria-label="Refresh organization"
            title="Refresh organization"
          >
            <RefreshCw size={14} />
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="p-8 space-y-4">
          <Skeleton className="h-48 w-full rounded-xl" />
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      ) : error ? (
        <Card className="text-center p-8 border-rose-200 bg-rose-50/30">
          <CardContent className="space-y-3">
            <AlertTriangle size={32} className="text-rose-600 mx-auto" />
            <h3 className="text-sm font-semibold text-slate-900">{error}</h3>
            <Button
              onClick={() => setShowCreateModal(true)}
              variant="primary"
              size="sm"
            >
              Create First Organization
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Current Organization Info (5 cols) */}
          <Card className="lg:col-span-5">
            <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-slate-100">
              <span className="font-mono text-[10px] text-slate-400 uppercase font-bold tracking-wider">
                ACTIVE TENANT DETAILS
              </span>
              <Badge variant="genuine" size="sm">
                {org?.status || "ACTIVE"}
              </Badge>
            </CardHeader>

            <CardContent className="p-5 space-y-4">
              <div>
                <label className="text-[11px] font-semibold text-slate-500 uppercase block">
                  Organization Name
                </label>
                <div className="text-lg font-bold text-slate-900 mt-0.5">{org?.name}</div>
              </div>

              <div className="grid grid-cols-2 gap-3 font-mono text-xs">
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-[10px] text-slate-400 block font-semibold">SLUG</span>
                  <span className="text-indigo-700 font-bold">{org?.slug}</span>
                </div>
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-[10px] text-slate-400 block font-semibold">CREATED</span>
                  <span className="text-slate-600">
                    {org?.created_at ? new Date(org.created_at).toLocaleDateString() : "N/A"}
                  </span>
                </div>
              </div>

              <div className="space-y-1 font-mono text-xs">
                <span className="text-[11px] font-semibold text-slate-500 uppercase block font-sans">
                  ORGANIZATION ID (UUID)
                </span>
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-700 font-mono">
                  {org?.id}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Members & Roles Table (7 cols) */}
          <Card className="lg:col-span-7">
            <CardHeader className="pb-3 border-b border-slate-100 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                <Users size={16} className="text-indigo-600" />
                Organization Members ({members.length})
              </CardTitle>
            </CardHeader>

            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50 text-slate-500 font-mono text-[10px] uppercase">
                      <TableHead className="px-5 py-3">User ID</TableHead>
                      <TableHead className="px-5 py-3">Assigned Role</TableHead>
                      <TableHead className="px-5 py-3">Joined Date</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {members.map((m) => (
                      <TableRow key={m.id} className="hover:bg-slate-50/70 transition">
                        <TableCell className="px-5 py-3.5 font-mono text-xs text-slate-900">
                          {m.user_id}
                        </TableCell>
                        <TableCell className="px-5 py-3.5 whitespace-nowrap">
                          <Badge variant={m.role === "owner" ? "genuine" : "neutral"} size="sm">
                            {m.role}
                          </Badge>
                        </TableCell>
                        <TableCell className="px-5 py-3.5 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                          {new Date(m.created_at).toLocaleDateString()}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Create Organization Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 w-full max-w-md rounded-xl p-6 space-y-4 shadow-xl">
            <h2 className="text-base font-bold text-slate-900">Create New Organization</h2>
            <form onSubmit={handleCreateOrg} className="space-y-4">
              <Input
                label="Organization Name"
                type="text"
                required
                placeholder="e.g. Acme Enterprise Verification"
                value={newOrgName}
                onChange={(e) => setNewOrgName(e.target.value)}
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
                  {creating ? "Creating..." : "Create Organization"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
