"use client";
import React, { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { authApi } from "@/lib/api";
import { AxiosError } from "axios";
import { Logo } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { AlertCircle, CheckCircle2, Mail } from "lucide-react";

function VerifyEmailForm() {
  const router = useRouter();
  const params = useSearchParams();
  const email = params.get("email") || "";

  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown > 0) {
      const timer = setTimeout(() => setCooldown((c) => c - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [cooldown]);

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setLoading(true);
    try {
      await authApi.verifyEmail({ email, code: code.trim() });
      router.push("/login?registered=1");
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string }>;
      setError(axErr.response?.data?.detail || "Invalid or expired verification code.");
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    if (!email || cooldown > 0) return;
    setError(null);
    setInfo(null);
    try {
      await authApi.resendOtp({ email });
      setInfo("A new verification code has been dispatched.");
      setCooldown(60);
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string }>;
      setError(axErr.response?.data?.detail || "Failed to resend code.");
    }
  }

  return (
    <div className="w-full max-w-md bg-white border border-slate-200/80 rounded-2xl shadow-xl p-8 space-y-6">
      <div className="flex flex-col items-center text-center space-y-2">
        <Logo size="lg" />
        <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mt-2">
          <Mail className="w-6 h-6" />
        </div>
        <h1 className="text-xl font-bold text-slate-900 tracking-tight">Verify your email</h1>
        <p className="text-xs text-slate-500 max-w-xs leading-relaxed">
          We sent a 6-digit verification code to{" "}
          <span className="font-semibold text-slate-800">{email || "your email"}</span>.
        </p>
      </div>

      {info && (
        <div className="flex items-start gap-2 p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-xs">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
          <span>{info}</span>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 text-red-800 rounded-lg text-xs">
          <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleVerify} className="space-y-4">
        <Input
          id="otp-input"
          label="Verification Code"
          type="text"
          maxLength={6}
          required
          autoFocus
          placeholder="123456"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          className="text-center font-mono tracking-widest text-lg font-bold"
        />

        <Button type="submit" loading={loading} className="w-full">
          Verify & Continue
        </Button>
      </form>

      <div className="flex flex-col items-center gap-3 pt-2 border-t border-slate-100 text-xs">
        <button
          type="button"
          onClick={handleResend}
          disabled={cooldown > 0 || !email}
          className="font-medium text-indigo-600 hover:text-indigo-700 disabled:text-slate-400 disabled:cursor-not-allowed hover:underline cursor-pointer"
        >
          {cooldown > 0 ? `Resend code in ${cooldown}s` : "Didn't receive the code? Resend"}
        </button>

        <Link href="/login" className="text-slate-500 hover:text-slate-700 hover:underline">
          Back to sign in
        </Link>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4 sm:p-6">
      <Suspense
        fallback={
          <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl shadow-xl p-8 flex items-center justify-center text-slate-400">
            Loading...
          </div>
        }
      >
        <VerifyEmailForm />
      </Suspense>
    </main>
  );
}
