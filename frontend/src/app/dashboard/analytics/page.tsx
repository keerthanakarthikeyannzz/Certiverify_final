"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BarChart3, TrendingUp, Shield, Copy, Building2,
  ChevronLeft, AlertTriangle, Activity,
} from "lucide-react";
import {
  analyticsApi,
  AnalyticsOverview, DocTypeDistribution, TrustDistribution,
  FraudSignals, TimeTrendResponse, UniversityStats,
} from "@/lib/api";
import { Doughnut, Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  ArcElement, Tooltip, Legend, CategoryScale,
  LinearScale, BarElement, PointElement, LineElement, Title as ChartTitle,
  Filler,
} from "chart.js";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

ChartJS.register(
  ArcElement, Tooltip, Legend, CategoryScale, LinearScale,
  BarElement, PointElement, LineElement, ChartTitle, Filler,
);

const DOC_TYPE_LABELS: Record<string, string> = {
  aadhaar: "Aadhaar", degree: "Degree", sslc: "SSLC", hsc: "HSC",
  diploma: "Diploma", transfer_certificate: "Transfer Cert",
  resume: "Resume", marksheet: "Marksheet", unknown: "Unknown",
};

const DOC_COLORS = [
  "#4f46e5","#818cf8","#059669","#d97706","#dc2626","#0284c7","#ea580c","#65a30d",
];

export default function AnalyticsPage() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [docTypes, setDocTypes] = useState<DocTypeDistribution | null>(null);
  const [trustDist, setTrustDist] = useState<TrustDistribution | null>(null);
  const [fraudSig, setFraudSig] = useState<FraudSignals | null>(null);
  const [trends, setTrends] = useState<TimeTrendResponse | null>(null);
  const [uniStats, setUniStats] = useState<UniversityStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [trendView, setTrendView] = useState<"daily" | "weekly" | "monthly">("daily");

  useEffect(() => {
    Promise.all([
      analyticsApi.overview(),
      analyticsApi.docTypes(),
      analyticsApi.trustDistribution(),
      analyticsApi.fraudSignals(),
      analyticsApi.timeTrends(),
      analyticsApi.universityStats(),
    ]).then(([ov, dt, td, fs, tr, us]) => {
      setOverview(ov.data);
      setDocTypes(dt.data);
      setTrustDist(td.data);
      setFraudSig(fs.data);
      setTrends(tr.data);
      setUniStats(us.data);
    }).catch(() => {
      setError("Failed to load analytics. Please refresh.");
    }).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <main className="p-6 max-w-7xl mx-auto space-y-6">
        <Skeleton className="h-20 w-full rounded-xl" />
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="p-6 flex flex-col items-center justify-center gap-4 min-h-[60vh]">
        <AlertTriangle size={32} className="text-rose-600" />
        <p className="text-rose-700 text-sm">{error}</p>
        <Link href="/dashboard" className="text-indigo-600 text-sm hover:underline font-medium">← Back to Dashboard</Link>
      </main>
    );
  }

  // Trend data for selected view
  const trendData = trends
    ? trendView === "daily" ? trends.daily
      : trendView === "weekly" ? trends.weekly
      : trends.monthly
    : [];

  const trendLabels = trendData.map(t => {
    if (trendView === "daily") return t.period.slice(5); // MM-DD
    if (trendView === "weekly") return `W${t.period.slice(5)}`;
    return t.period;
  });

  return (
    <main className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between bg-white border border-slate-200 p-6 rounded-xl shadow-sm">
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="text-slate-400 hover:text-indigo-600 transition p-1">
            <ChevronLeft size={20} />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
              <BarChart3 size={22} className="text-indigo-600" />
              Institutional Verification Analytics
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Aggregated verification analytics sourced from all your ingested certificates
            </p>
          </div>
        </div>
      </div>

      {/* ── PART D: Overview Metric Cards ──────────────────────────────────── */}
      {overview && (
        <section className="space-y-3">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider font-mono">Overview Metrics</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            {[
              { label: "Total Certs",    value: overview.total_certificates,       color: "text-slate-900" },
              { label: "Genuine",        value: overview.genuine_count,            color: "text-emerald-700" },
              { label: "Suspicious",     value: overview.suspicious_count,         color: "text-amber-700" },
              { label: "Fake",           value: overview.fake_count,               color: "text-rose-700" },
              { label: "Duplicates",     value: overview.duplicate_count,          color: overview.duplicate_count > 0 ? "text-amber-700" : "text-emerald-700" },
              { label: "Tampered",       value: overview.tampered_count,           color: overview.tampered_count > 0 ? "text-rose-700" : "text-emerald-700" },
              { label: "QR Verified",    value: overview.qr_verified_count,        color: "text-indigo-700" },
              { label: "Blockchain",     value: overview.blockchain_verified_count,color: "text-indigo-700" },
              { label: "Avg Trust",      value: overview.avg_trust_score != null ? `${Math.round(overview.avg_trust_score)}/100` : "N/A", color: "text-slate-900" },
              { label: "Avg OCR Conf",   value: overview.avg_ocr_accuracy != null ? `${Math.round(overview.avg_ocr_accuracy * 100)}%` : "N/A", color: "text-slate-900" },
              { label: "Avg Fraud Prob", value: overview.avg_fraud_probability != null ? `${Math.round(overview.avg_fraud_probability * 100)}%` : "N/A",
                color: overview.avg_fraud_probability != null && overview.avg_fraud_probability > 0.5 ? "text-rose-700" : "text-emerald-700" },
              { label: "Completion",     value: overview.verification_completion_rate != null ? `${overview.verification_completion_rate}%` : "N/A", color: "text-slate-900" },
            ].map(card => (
              <div key={card.label} className="bg-white rounded-xl p-4 border border-slate-200 text-center shadow-sm">
                <p className={`text-xl font-bold font-mono ${card.color}`}>{card.value}</p>
                <p className="text-[11px] font-medium text-slate-500 mt-1 leading-tight">{card.label}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── PART E-G: Charts Row — Doc Types + Trust Distribution ────────── */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* PART G: Document Type Distribution */}
        {docTypes && Object.keys(docTypes.doc_types).length > 0 && (
          <Card>
            <CardHeader className="pb-3 border-b border-slate-100 flex flex-row items-center gap-2">
              <Activity size={16} className="text-indigo-600" />
              <CardTitle className="text-sm font-semibold text-slate-900">Document Type Distribution</CardTitle>
            </CardHeader>
            <CardContent className="p-5 flex items-center gap-6">
              <div className="w-44 shrink-0">
                <Doughnut
                  data={{
                    labels: Object.keys(docTypes.doc_types).map(k => DOC_TYPE_LABELS[k] ?? k),
                    datasets: [{
                      data: Object.values(docTypes.doc_types),
                      backgroundColor: DOC_COLORS,
                      borderColor: "#ffffff",
                      borderWidth: 2,
                    }],
                  }}
                  options={{
                    plugins: { legend: { display: false } },
                    maintainAspectRatio: true,
                  }}
                />
              </div>
              <ul className="flex-1 space-y-1.5">
                {Object.entries(docTypes.doc_types)
                  .sort(([, a], [, b]) => b - a)
                  .map(([key, count], i) => {
                    const pct = docTypes.total_classified > 0
                      ? Math.round((count / docTypes.total_classified) * 100) : 0;
                    return (
                      <li key={key} className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: DOC_COLORS[i % DOC_COLORS.length] }} />
                        <span className="text-xs text-slate-700 flex-1">{DOC_TYPE_LABELS[key] ?? key}</span>
                        <span className="text-xs font-mono text-slate-500">{count}</span>
                        <span className="text-xs font-mono text-slate-400 w-10 text-right">{pct}%</span>
                      </li>
                    );
                  })}
              </ul>
            </CardContent>
          </Card>
        )}

        {/* PART J: Trust Score Distribution */}
        {trustDist && trustDist.total_scored > 0 && (
          <Card>
            <CardHeader className="pb-3 border-b border-slate-100 flex flex-row items-center gap-2">
              <Shield size={16} className="text-emerald-600" />
              <CardTitle className="text-sm font-semibold text-slate-900">Trust Score Distribution</CardTitle>
            </CardHeader>
            <CardContent className="p-5 space-y-3.5">
              {trustDist.bands.map((band, i) => {
                const COLORS = ["#059669", "#4f46e5", "#d97706", "#dc2626"];
                return (
                  <div key={band.label}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-700 font-medium">{band.label} <span className="text-slate-400 font-normal">({band.description})</span></span>
                      <span className="text-slate-600 font-mono">{band.count} · {band.percentage}%</span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{ width: `${band.percentage}%`, background: COLORS[i] }}
                      />
                    </div>
                  </div>
                );
              })}
              <p className="text-xs text-slate-400 font-mono mt-2">{trustDist.total_scored} certificates scored</p>
            </CardContent>
          </Card>
        )}
      </section>

      {/* ── PART K: Fraud Signals ─────────────────────────────────────────── */}
      {fraudSig && (
        <Card>
          <CardHeader className="pb-3 border-b border-slate-100 flex flex-row items-center gap-2">
            <Copy size={15} className="text-rose-600" />
            <CardTitle className="text-sm font-semibold text-slate-900">Fraud Signal Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="p-5">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {[
                { label: "Tampering", value: fraudSig.tampering_detected, bad: fraudSig.tampering_detected > 0 },
                { label: "Duplicates", value: fraudSig.duplicates_detected, bad: fraudSig.duplicates_detected > 0 },
                { label: "Cert Conflicts", value: fraudSig.certificate_conflict, bad: fraudSig.certificate_conflict > 0 },
                { label: "Blockchain Mismatch", value: fraudSig.blockchain_mismatch, bad: fraudSig.blockchain_mismatch > 0 },
                { label: "QR Invalid", value: fraudSig.qr_invalid, bad: fraudSig.qr_invalid > 0 },
                { label: "Comparison Mismatch", value: fraudSig.comparison_mismatch, bad: fraudSig.comparison_mismatch > 0 },
              ].map(item => (
                <div key={item.label} className="text-center p-3 bg-slate-50 border border-slate-200 rounded-lg">
                  <p className={`text-2xl font-bold font-mono mb-1 ${item.bad ? "text-rose-700" : "text-emerald-700"}`}>
                    {item.value}
                  </p>
                  <p className="text-xs text-slate-600 font-medium leading-tight">{item.label}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── PART F: Time-based Trends ─────────────────────────────────────── */}
      {trends && (
        <Card>
          <CardHeader className="pb-3 border-b border-slate-100 flex flex-row items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp size={16} className="text-indigo-600" />
              <CardTitle className="text-sm font-semibold text-slate-900">Verification Trends</CardTitle>
            </div>
            <div className="flex gap-1">
              {(["daily", "weekly", "monthly"] as const).map(v => (
                <button
                  key={v}
                  onClick={() => setTrendView(v)}
                  className={`text-xs px-3 py-1 rounded-md font-medium transition ${
                    trendView === v
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-slate-600 hover:text-slate-900 bg-slate-100 border border-slate-200"
                  }`}
                >
                  {v.charAt(0).toUpperCase() + v.slice(1)}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="p-5">
            <Line
              data={{
                labels: trendLabels,
                datasets: [
                  {
                    label: "Uploaded",
                    data: trendData.map(t => t.uploaded),
                    borderColor: "#4f46e5",
                    backgroundColor: "rgba(79,70,229,0.08)",
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                  },
                  {
                    label: "Verified",
                    data: trendData.map(t => t.verified),
                    borderColor: "#059669",
                    backgroundColor: "rgba(5,150,105,0.08)",
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                  },
                ],
              }}
              options={{
                plugins: {
                  legend: { labels: { color: "#475569", font: { size: 11 } } },
                },
                scales: {
                  x: { ticks: { color: "#64748b", font: { size: 10 } }, grid: { color: "rgba(0,0,0,0.04)" } },
                  y: { ticks: { color: "#64748b", font: { size: 10 }, stepSize: 1 }, grid: { color: "rgba(0,0,0,0.04)" }, beginAtZero: true },
                },
                maintainAspectRatio: false,
              }}
              style={{ height: 220 }}
            />
          </CardContent>
        </Card>
      )}

      {/* ── PART H: University Stats ──────────────────────────────────────── */}
      {uniStats && uniStats.universities.length > 0 && (
        <Card>
          <CardHeader className="pb-3 border-b border-slate-100 flex flex-row items-center gap-2">
            <Building2 size={16} className="text-indigo-600" />
            <CardTitle className="text-sm font-semibold text-slate-900">University Breakdown (Top 10)</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-slate-500 font-mono text-[10px] uppercase">
                    <th className="text-left px-5 py-3 font-medium">University</th>
                    <th className="text-center px-3 py-3 font-medium">Total</th>
                    <th className="text-center px-3 py-3 font-medium text-emerald-700">Genuine</th>
                    <th className="text-center px-3 py-3 font-medium text-amber-700">Suspicious</th>
                    <th className="text-center px-3 py-3 font-medium text-rose-700">Fake</th>
                    <th className="text-center px-3 py-3 font-medium">Avg Trust</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {uniStats.universities.map((uni, i) => (
                    <tr key={i} className="hover:bg-slate-50/70 transition">
                      <td className="px-5 py-3.5 text-slate-900 font-medium max-w-[200px] truncate">{uni.university_name}</td>
                      <td className="text-center px-3 py-3.5 font-mono text-slate-600">{uni.total}</td>
                      <td className="text-center px-3 py-3.5 font-mono text-emerald-700 font-semibold">{uni.genuine}</td>
                      <td className="text-center px-3 py-3.5 font-mono text-amber-700 font-semibold">{uni.suspicious}</td>
                      <td className="text-center px-3 py-3.5 font-mono text-rose-700 font-semibold">{uni.fake}</td>
                      <td className="text-center px-3 py-3.5 font-mono text-slate-600">
                        {uni.avg_trust_score != null ? `${uni.avg_trust_score}/100` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <footer className="text-center text-xs text-slate-400 py-6">
        Analytics sourced from your verified certificates. No student PII exposed.
      </footer>
    </main>
  );
}
