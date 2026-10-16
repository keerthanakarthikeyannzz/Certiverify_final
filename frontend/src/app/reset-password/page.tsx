"use client";
import React, { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { authApi } from "@/lib/api";
import { AxiosError } from "axios";
import { Logo } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { AlertCircle, CheckCircle2, Lock } from "lucide-react";

function ResetPasswordForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setLoading(true);
    try {
      await authApi.resetPassword({ token, new_password: password });
      setSuccess(true);
    } catch (err) {
      const axErr = err as AxiosError<{ detail?: string }>;
      setError(axErr.response?.data?.detail || "Invalid or expired reset token.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-md bg-white border border-slate-200/80 rounded-2xl shadow-xl p-8 space-y-6">
      <div className="flex flex-col items-center text-center space-y-2">
        <Logo size="lg" />
        <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mt-2">
          <Lock className="w-6 h-6" />
        </div>
        <h1 className="text-xl font-bold text-slate-900 tracking-tight">Set new password</h1>
        <p className="text-xs text-slate-500 max-w-xs leading-relaxed">
          Create a secure password with at least 8 characters, an uppercase letter, and a number.
        </p>
      </div>

      {success ? (
        <div className="space-y-4">
          <div className="flex items-start gap-2.5 p-3.5 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-xs leading-relaxed">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
            <span>Your password has been successfully updated. You can now sign in with your new credentials.</span>
          </div>
          <Link href="/login" className="block">
            <Button className="w-full">
              Proceed to Sign In
            </Button>
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 text-red-800 rounded-lg text-xs">
              <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <Input
            id="new-password"
            label="New password"
            type="password"
            required
            autoComplete="new-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          <Input
            id="confirm-password"
            label="Confirm new password"
            type="password"
            required
            autoComplete="new-password"
            placeholder="••••••••"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />

          <Button type="submit" loading={loading} className="w-full">
            Reset Password
          </Button>
        </form>
      )}

      <div className="text-center pt-2 border-t border-slate-100">
        <Link href="/login" className="text-xs text-slate-500 hover:text-slate-800 hover:underline">
          Back to sign in
        </Link>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4 sm:p-6">
      <Suspense
        fallback={
          <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl shadow-xl p-8 flex items-center justify-center text-slate-400">
            Loading...
          </div>
        }
      >
        <ResetPasswordForm />
      </Suspense>
    </main>
  );
}
