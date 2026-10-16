"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ShieldCheck,
  UploadCloud,
  FileSearch,
  Cpu,
  Lock,
  ArrowRight,
  CheckCircle2,
  Sparkles,
  BarChart3,
  FileText,
  Search,
} from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { getAccessToken } from "@/lib/api";

export default function LandingPage() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    if (getAccessToken()) {
      setIsAuthenticated(true);
    }
  }, []);

  const handleQuickLookup = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    if (isAuthenticated) {
      router.push(`/dashboard/certificates?q=${encodeURIComponent(searchQuery.trim())}`);
    } else {
      router.push(`/login?redirect=${encodeURIComponent(`/dashboard/certificates?q=${searchQuery.trim()}`)}`);
    }
  };

  return (
    <div className="min-h-screen bg-[#FAFAFA] text-slate-900 selection:bg-indigo-100 selection:text-indigo-900">
      {/* Navigation Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center">
            <Logo size="md" />
          </div>

          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-600">
            <a href="#features" className="hover:text-indigo-600 transition-colors">
              Features
            </a>
            <a href="#pipeline" className="hover:text-indigo-600 transition-colors">
              How It Works
            </a>
            <a href="#security" className="hover:text-indigo-600 transition-colors">
              Security
            </a>
          </nav>

          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <Link href="/dashboard">
                <Button variant="primary" size="sm" icon={<ArrowRight size={14} />}>
                  Go to Cockpit
                </Button>
              </Link>
            ) : (
              <>
                <Link href="/login">
                  <Button variant="ghost" size="sm">
                    Sign In
                  </Button>
                </Link>
                <Link href="/register">
                  <Button variant="primary" size="sm">
                    Get Started
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative overflow-hidden pt-16 pb-20 lg:pt-24 lg:pb-32">
        {/* Subtle background glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-indigo-50/70 rounded-full blur-3xl pointer-events-none -z-10" />

        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center space-y-6">
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold"
          >
            <Sparkles size={14} className="text-indigo-600" />
            <span>AI-Powered Academic & Professional Credential Verification</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.05 }}
            className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-slate-900 tracking-tight leading-[1.15]"
          >
            Detect Fake Certificates with{" "}
            <span className="bg-gradient-to-r from-indigo-600 to-indigo-800 bg-clip-text text-transparent">
              Forensic Certainty
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.1 }}
            className="max-w-2xl mx-auto text-base sm:text-lg text-slate-600 leading-relaxed"
          >
            Multi-vector optical character recognition, deep learning tampering detection, and
            cryptographic blockchain ledger provenance in one unified forensic cockpit.
          </motion.p>

          {/* Quick Action Buttons */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.15 }}
            className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2"
          >
            <Link href={isAuthenticated ? "/dashboard/upload" : "/login"}>
              <Button
                variant="primary"
                size="lg"
                icon={<UploadCloud size={18} />}
                className="w-full sm:w-auto shadow-md shadow-indigo-600/10"
              >
                Verify a Certificate Now
              </Button>
            </Link>
            <Link href={isAuthenticated ? "/dashboard" : "/login"}>
              <Button
                variant="secondary"
                size="lg"
                icon={<ArrowRight size={16} />}
                className="w-full sm:w-auto"
              >
                Explore Enterprise Cockpit
              </Button>
            </Link>
          </motion.div>

          {/* Quick Lookup Bar */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.2 }}
            className="pt-6 max-w-xl mx-auto"
          >
            <form
              onSubmit={handleQuickLookup}
              className="flex items-center gap-2 p-1.5 bg-white border border-slate-300 rounded-xl shadow-sm focus-within:border-indigo-600 focus-within:ring-2 focus-within:ring-indigo-600/20 transition-all"
            >
              <div className="pl-3 text-slate-400">
                <Search size={16} />
              </div>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Lookup certificate by UUID or filename..."
                className="w-full text-xs bg-transparent border-none text-slate-900 placeholder:text-slate-400 focus:outline-none"
              />
              <Button type="submit" variant="primary" size="sm">
                Verify
              </Button>
            </form>
            <p className="text-[11px] text-slate-600 mt-2">
              Supports PDF, PNG, JPG documents up to 25MB with instant OCR extraction.
            </p>
          </motion.div>
        </div>
      </section>

      {/* Trust & Proof Metrics */}
      <section className="border-y border-slate-200 bg-white py-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
            <div className="space-y-1">
              <div className="text-3xl font-extrabold text-indigo-600 font-mono">99.4%</div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Tamper Accuracy
              </div>
            </div>
            <div className="space-y-1">
              <div className="text-3xl font-extrabold text-emerald-600 font-mono">&lt; 1.2s</div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Average Latency
              </div>
            </div>
            <div className="space-y-1">
              <div className="text-3xl font-extrabold text-indigo-600 font-mono">4-Vector</div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Forensic Analysis
              </div>
            </div>
            <div className="space-y-1">
              <div className="text-3xl font-extrabold text-emerald-600 font-mono">100%</div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Audit Trail Integrity
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section id="features" className="py-20 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-2xl mx-auto mb-14 space-y-3">
          <h2 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
            Complete Multi-Layer Forensic Verification
          </h2>
          <p className="text-sm text-slate-500">
            Every document passes through rigorous neural and cryptographic verification steps to
            ensure absolute authenticity.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card className="hover:shadow-md transition-shadow">
            <CardContent className="p-6 space-y-4">
              <div className="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                <FileSearch size={20} />
              </div>
              <h3 className="text-base font-bold text-slate-900">
                Automated OCR & Layout Extraction
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Extracts student names, roll numbers, GPA, institution credentials, QR codes, and
                official seals with field-level confidence telemetry.
              </p>
              <div className="pt-2 flex items-center gap-2 text-xs font-semibold text-indigo-600">
                <CheckCircle2 size={14} /> Multi-engine EasyOCR & Tesseract
              </div>
            </CardContent>
          </Card>

          <Card className="hover:shadow-md transition-shadow">
            <CardContent className="p-6 space-y-4">
              <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <Cpu size={20} />
              </div>
              <h3 className="text-base font-bold text-slate-900">
                Deep Learning Tamper Detection
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Neural networks identify pixel-level splicing, copy-move clone anomalies, font
                inconsistencies, and digital image artifact alterations.
              </p>
              <div className="pt-2 flex items-center gap-2 text-xs font-semibold text-emerald-600">
                <CheckCircle2 size={14} /> ELA & Frequency Domain Analysis
              </div>
            </CardContent>
          </Card>

          <Card className="hover:shadow-md transition-shadow">
            <CardContent className="p-6 space-y-4">
              <div className="w-10 h-10 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                <Lock size={20} />
              </div>
              <h3 className="text-base font-bold text-slate-900">
                Cryptographic Blockchain Ledger
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Immutable SHA-256 fingerprinting with optional smart-contract verification and
                tamper-proof executive dossier generation.
              </p>
              <div className="pt-2 flex items-center gap-2 text-xs font-semibold text-amber-600">
                <CheckCircle2 size={14} /> Verifiable PDF Audit Reports
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* How It Works Pipeline */}
      <section id="pipeline" className="py-20 bg-white border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-2xl mx-auto mb-14 space-y-3">
            <h2 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
              Three Steps to Guaranteed Verification
            </h2>
            <p className="text-sm text-slate-500">
              From raw document ingestion to executive audit report in under 5 seconds.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="flex flex-col items-center text-center space-y-3">
              <div className="w-12 h-12 rounded-xl bg-indigo-600 text-white font-bold text-lg flex items-center justify-center shadow-md">
                1
              </div>
              <h3 className="text-sm font-bold text-slate-900">Upload Certificate</h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Drag and drop your academic mark sheet, degree certificate, or license into our
                secure intake pipeline.
              </p>
            </div>

            <div className="flex flex-col items-center text-center space-y-3">
              <div className="w-12 h-12 rounded-xl bg-indigo-600 text-white font-bold text-lg flex items-center justify-center shadow-md">
                2
              </div>
              <h3 className="text-sm font-bold text-slate-900">Automated Pipeline Runs</h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Document classifier, OCR engine, tamper detectors, and trust scoring engine compute
                all forensic signals in parallel.
              </p>
            </div>

            <div className="flex flex-col items-center text-center space-y-3">
              <div className="w-12 h-12 rounded-xl bg-indigo-600 text-white font-bold text-lg flex items-center justify-center shadow-md">
                3
              </div>
              <h3 className="text-sm font-bold text-slate-900">Inspect Cockpit & Report</h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Review the 0-100 Trust Score Gauge, inspect highlighted tamper anomalies, and
                download the official PDF dossier.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Footer Banner */}
      <section className="py-16 bg-[#FAFAFA] border-t border-slate-200">
        <div className="max-w-4xl mx-auto px-4 text-center space-y-5">
          <h2 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
            Ready to Protect Your Organization Against Credential Fraud?
          </h2>
          <p className="text-sm text-slate-500 max-w-xl mx-auto">
            Get started with CertiVerify AI today. Test your first document in seconds.
          </p>
          <div className="pt-2">
            <Link href={isAuthenticated ? "/dashboard/upload" : "/register"}>
              <Button variant="primary" size="lg" icon={<ArrowRight size={16} />}>
                {isAuthenticated ? "Go to Upload Ingestion" : "Create Free Account"}
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <Logo size="sm" />
            <span className="font-semibold text-slate-700">CertiVerify AI</span>
            <span>— AI-Powered Credential Forensics</span>
          </div>
          <div className="flex items-center gap-6">
            <Link href="/login" className="hover:text-indigo-600">
              Sign In
            </Link>
            <Link href="/register" className="hover:text-indigo-600">
              Register
            </Link>
            <Link href="/dashboard" className="hover:text-indigo-600">
              Dashboard
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
