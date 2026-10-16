"use client";
import React, { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { authApi, setTokens } from "@/lib/api";
import { AxiosError } from "axios";
import { Logo } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { AlertCircle, CheckCircle2, ArrowRight } from "lucide-react";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const justRegistered = params.get("registered") === "1";

  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [unverifiedEmail, setUnverifiedEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setUnverifiedEmail(null);
    setLoading(true);
    try {
      const { data } = await authApi.login(form);
      setTokens(data.access_token, data.refresh_token);
      router.push("/dashboard/upload");
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string }>;
      const detail = axErr.response?.data?.detail || "Login failed. Check your credentials.";
      setError(detail);
      if (axErr.response?.status === 403 && /verif/i.test(detail)) {
        setUnverifiedEmail(form.email);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-md bg-white border border-slate-200/80 rounded-2xl shadow-xl p-8 space-y-6">
      <div className="flex flex-col items-center text-center space-y-2">
        <Logo size="lg" />
        <h1 className="text-xl font-bold text-slate-900 tracking-tight pt-2">Welcome back</h1>
        <p className="text-xs text-slate-500 max-w-xs">
          Sign in to access document verification, forensic auditing, and trust scores.
        </p>
      </div>

      {justRegistered && (
        <div className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-xs font-medium">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>Account created successfully! Please sign in.</span>
        </div>
      )}

      {unverifiedEmail ? (
        <div className="p-3.5 bg-amber-50 border border-amber-200 text-amber-900 rounded-lg space-y-2 text-xs">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <span className="font-semibold">{error}</span>
          </div>
          <Link
            href={`/verify-email?email=${encodeURIComponent(unverifiedEmail)}`}
            className="inline-flex items-center gap-1 font-semibold text-indigo-600 hover:text-indigo-700 hover:underline pt-1"
          >
            Verify your email with OTP <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      ) : error ? (
        <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 text-red-800 rounded-lg text-xs">
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      ) : null}

      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          id="email-input"
          label="Email address"
          type="email"
          required
          autoComplete="email"
          placeholder="name@organization.com"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />

        <div className="space-y-1">
          <div className="flex justify-between items-center">
            <label htmlFor="password-input" className="block text-xs font-semibold text-slate-700 select-none">
              Password
            </label>
            <Link
              href="/forgot-password"
              className="text-xs text-indigo-600 hover:text-indigo-700 font-medium hover:underline"
            >
              Forgot password?
            </Link>
          </div>
          <Input
            id="password-input"
            type="password"
            required
            autoComplete="current-password"
            placeholder="••••••••"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </div>

        <Button type="submit" loading={loading} className="w-full">
          Sign In
        </Button>
      </form>

      <div className="text-center pt-2 border-t border-slate-100">
        <p className="text-xs text-slate-500">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="font-semibold text-indigo-600 hover:text-indigo-700 hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4 sm:p-6">
      <Suspense
        fallback={
          <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl shadow-xl p-8 flex items-center justify-center text-slate-400">
            Loading...
          </div>
        }
      >
        <LoginForm />
      </Suspense>
    </main>
  );
}
