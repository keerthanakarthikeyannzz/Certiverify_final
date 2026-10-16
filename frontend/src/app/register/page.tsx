"use client";
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authApi } from "@/lib/api";
import { AxiosError } from "axios";
import { Logo } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { AlertCircle, Check } from "lucide-react";

function extractErrorMessage(err: unknown): string {
  if (!err) return "Registration failed. Please try again.";
  const axErr = err as AxiosError<{ detail?: unknown; message?: string }>;
  if (!axErr.response) {
    if (axErr.message?.includes("Network Error") || axErr.code === "ERR_NETWORK") {
      return "Unable to connect to authentication server. Please ensure the backend is running.";
    }
    return axErr.message || "Network error. Please verify your connection.";
  }

  const status = axErr.response.status;
  const detail = axErr.response.data?.detail;

  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: string[] };
    const raw = first?.msg || "Validation error";
    return raw.replace(/^Value error,\s*/i, "");
  }

  if (status === 409) return "An account with this email already exists.";
  if (status >= 500) return "Server error encountered. Please try again later.";

  return "Registration failed. Please try again.";
}

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
      router.push(`/verify-email?email=${encodeURIComponent(trimmedEmail)}`);
    } catch (err) {
      setError(extractErrorMessage(err));
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
        </div>

        {error && (
          <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 text-red-800 rounded-lg text-xs">
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
            placeholder="jane@university.edu"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />

          <Select
            id="role-select"
            label="Account Role"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
            options={[
              { value: "student", label: "Student / Graduate" },
              { value: "verifier", label: "Employer / Background Verifier" },
              { value: "issuer", label: "Academic Registrar / Issuer" },
            ]}
          />

          <div className="space-y-1.5">
            <Input
              id="password-input"
              label="Password"
              type="password"
              required
              autoComplete="new-password"
              placeholder="••••••••"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            {form.password.length > 0 && (
              <div className="grid grid-cols-3 gap-1 pt-1 text-[11px]">
                <div className={`flex items-center gap-1 ${hasLength ? "text-emerald-700" : "text-slate-400"}`}>
                  <Check className="w-3 h-3" /> 8+ chars
                </div>
                <div className={`flex items-center gap-1 ${hasUpper ? "text-emerald-700" : "text-slate-400"}`}>
                  <Check className="w-3 h-3" /> Uppercase
                </div>
                <div className={`flex items-center gap-1 ${hasNumber ? "text-emerald-700" : "text-slate-400"}`}>
                  <Check className="w-3 h-3" /> Number
                </div>
              </div>
            )}
          </div>

          <Button type="submit" loading={loading} disabled={loading} className="w-full">
            Create Account
          </Button>
        </form>

        <div className="text-center pt-2 border-t border-slate-100">
          <p className="text-xs text-slate-500">
            Already have an account?{" "}
            <Link href="/login" className="font-semibold text-indigo-600 hover:text-indigo-700 hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
