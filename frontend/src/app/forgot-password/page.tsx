"use client";
import React, { useState } from "react";
import Link from "next/link";
import { authApi } from "@/lib/api";
import { Logo } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { CheckCircle2, KeyRound } from "lucide-react";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await authApi.forgotPassword({ email });
    } finally {
      setSent(true);
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4 sm:p-6">
      <div className="w-full max-w-md bg-white border border-slate-200/80 rounded-2xl shadow-xl p-8 space-y-6">
        <div className="flex flex-col items-center text-center space-y-2">
          <Logo size="lg" />
          <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mt-2">
            <KeyRound className="w-6 h-6" />
          </div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Reset password</h1>
          <p className="text-xs text-slate-500 max-w-xs leading-relaxed">
            Enter your account email address and we&apos;ll send instructions to reset your password.
          </p>
        </div>

        {sent ? (
          <div className="space-y-4">
            <div className="flex items-start gap-2.5 p-3.5 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-xs leading-relaxed">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <span>
                If an account exists for <span className="font-semibold">{email}</span>, a password reset link has been dispatched.
              </span>
            </div>
            <Link href="/login" className="block">
              <Button variant="secondary" className="w-full">
                Return to sign in
              </Button>
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              id="reset-email"
              label="Email address"
              type="email"
              required
              autoFocus
              placeholder="you@organization.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />

            <Button type="submit" loading={loading} className="w-full">
              Send Reset Instructions
            </Button>
          </form>
        )}

        <div className="text-center pt-2 border-t border-slate-100">
          <Link href="/login" className="text-xs text-slate-500 hover:text-slate-800 hover:underline">
            Remembered your password? Sign in
          </Link>
        </div>
      </div>
    </main>
  );
}
