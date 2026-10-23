"use client";
import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authApi, setTokens } from "@/lib/api";
import { formatErrorMessage, isBackendUnreachableError } from "@/lib/errorHandler";
import { Logo } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { ConnectionStatus } from "@/components/ui/ConnectionStatus";
import { AlertCircle, Check } from "lucide-react";

function validatePassword(pw: string): string | null {
  if (pw.length < 8) return "Password must be at least 8 characters.";
  if (!/[A-Z]/.test(pw)) return "Password must contain at least one uppercase letter (e.g. A–Z).";
  if (!/[0-9]/.test(pw)) return "Password must contain at least one number (0–9).";
  return null;
}

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "student" });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Auto-clear connection error when backend status becomes online
  useEffect(() => {
    const handleStatus = (e: Event) => {
      const customEvent = e as CustomEvent<{ online: boolean }>;
      if (customEvent.detail?.online && error && error.includes("Can't reach the verification server")) {
        setError(null);
      }
    };
    window.addEventListener("backend-status-change", handleStatus);
    return () => window.removeEventListener("backend-status-change", handleStatus);
  }, [error]);

  const hasLength = form.password.length >= 8;
  const hasUpper = /[A-Z]/.test(form.password);
  const hasNumber = /[0-9]/.test(form.password);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    setError(null);

    const trimmedName = form.full_name.trim();
    const trimmedEmail = form.email.trim();

    if (trimmedName.length < 2) {
      setError("Full name must be at least 2 characters.");
      return;
    }

    if (!trimmedEmail || !/^\S+@\S+\.\S+$/.test(trimmedEmail)) {
      setError("Please enter a valid institutional email address.");
      return;
    }

    const pwError = validatePassword(form.password);
    if (pwError) {
      setError(pwError);
      return;
    }

    setLoading(true);
    try {
      await authApi.register({
        full_name: trimmedName,
        email: trimmedEmail,
        password: form.password,
        role: form.role,
      });

      try {
        const { data } = await authApi.login({
          email: trimmedEmail,
          password: form.password,
        });
        setTokens(data.access_token, data.refresh_token);
        router.push("/dashboard/upload");
      } catch {
        router.push("/login?registered=1");
      }
    } catch (err) {
      setError(formatErrorMessage(err, "Registration failed. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4 sm:p-6">
      <div className="w-full max-w-md bg-white border border-slate-200/80 rounded-2xl shadow-xl p-8 space-y-6">
        <div className="flex flex-col items-center text-center space-y-2">
          <Logo size="lg" />
          <h1 className="text-xl font-bold text-slate-900 tracking-tight pt-2">Create an account</h1>
          <p className="text-xs text-slate-500 max-w-xs">
            Start verifying academic and institutional credentials with tamper detection.
          </p>
          <div className="pt-1">
            <ConnectionStatus />
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 text-red-800 rounded-lg text-xs leading-relaxed">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            id="fullname-input"
            label="Full Name"
            type="text"
            required
            placeholder="Dr. Jane Doe"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          />

          <Input
            id="email-input"
            label="Institutional Email"
            type="email"
            required
            autoComplete="email"
            placeholder="jane.doe@university.edu"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />

          <Input
            id="password-input"
            label="Password"
            type="password"
            required
            autoComplete="new-password"
            placeholder="Min 8 chars, 1 uppercase, 1 digit"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />

          <div className="bg-slate-50 border border-slate-100 rounded-lg p-3 space-y-1.5 text-xs">
            <p className="font-semibold text-slate-600 text-[11px] uppercase tracking-wider">Password Requirements</p>
            <div className="flex items-center gap-2">
              <div className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[10px] ${hasLength ? "bg-emerald-500 text-white" : "bg-slate-200 text-slate-400"}`}>
                <Check className="w-2.5 h-2.5 stroke-[3]" />
              </div>
              <span className={hasLength ? "text-emerald-700 font-medium" : "text-slate-500"}>At least 8 characters</span>
            </div>
            <div className="flex items-center gap-2">
              <div className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[10px] ${hasUpper ? "bg-emerald-500 text-white" : "bg-slate-200 text-slate-400"}`}>
                <Check className="w-2.5 h-2.5 stroke-[3]" />
              </div>
              <span className={hasUpper ? "text-emerald-700 font-medium" : "text-slate-500"}>At least one uppercase letter (A–Z)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[10px] ${hasNumber ? "bg-emerald-500 text-white" : "bg-slate-200 text-slate-400"}`}>
                <Check className="w-2.5 h-2.5 stroke-[3]" />
              </div>
              <span className={hasNumber ? "text-emerald-700 font-medium" : "text-slate-500"}>At least one number (0–9)</span>
            </div>
          </div>

          <Select
            id="role-select"
            label="Role in Organization"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
            options={[
              { value: "student", label: "Student / Candidate" },
              { value: "issuer", label: "Issuing Authority (University / Board)" },
              { value: "verifier", label: "Third-party Verifier (Employer / Embassy)" },
              { value: "admin", label: "Compliance & Security Admin" },
            ]}
          />

          <Button type="submit" variant="primary" className="w-full mt-2" loading={loading}>
            Create Account
          </Button>
        </form>

        <p className="text-center text-xs text-slate-500">
          Already registered?{" "}
          <Link href="/login" className="text-indigo-600 font-medium hover:underline">
            Sign in here
          </Link>
        </p>
      </div>
    </main>
  );
}
