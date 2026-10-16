"use client";
import { useCallback, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useDropzone } from "react-dropzone";
import {
  ArrowLeft,
  GitCompare,
  Upload,
  FileText,
  Image as ImageIcon,
  X,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  Tag,
  TrendingUp,
  FileDown,
  Plus,
  Sparkles,
  Minus,
  Info,
} from "lucide-react";
import {
  directCompareApi,
  DirectCompareResponse,
  FieldComparisonRow,
  getAccessToken,
  authApi,
} from "@/lib/api";
import { Logo } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";

// ── Document type options ────────────────────────────────────────────────
const MANUAL_DOC_TYPES: { value: string; label: string }[] = [
  { value: "aadhaar_card",         label: "Aadhaar Card" },
  { value: "sslc_marksheet",       label: "SSLC Marksheet" },
  { value: "hsc_marksheet",        label: "HSC Marksheet" },
  { value: "marksheet",            label: "Marksheet (Generic)" },
  { value: "transfer_certificate", label: "Transfer Certificate" },
  { value: "diploma",              label: "Diploma Certificate" },
  { value: "degree_certificate",   label: "Degree Certificate" },
  { value: "resume",               label: "Resume" },
];

function typeLabel(val: string) {
  return MANUAL_DOC_TYPES.find((t) => t.value === val)?.label ?? val.replace(/_/g, " ");
}

// Supported pair hints shown to user
const SUPPORTED_PAIRS = [
  "Degree Certificate ↔ Marksheet",
  "Degree Certificate ↔ Resume",
  "Resume ↔ Aadhaar Card",
  "Marksheet ↔ Aadhaar Card",
  "Transfer Certificate ↔ Marksheet",
  "Diploma Certificate ↔ Resume",
];

type Step = "select" | "comparing" | "results";

interface DocSlotState {
  docType: string;
  file: File | null;
}

const MAX_SLOTS = 5;
const MIN_SLOTS = 2;

// ── Compare stage labels (cycles during OCR) ────────────────────────────
const COMPARE_STAGES = [
  "Loading documents…",
  "Running OCR on Document 1…",
  "Running OCR on Document 2…",
  "Extracting fields…",
  "Comparing fields with RapidFuzz…",
  "Generating AI analysis…",
  "Finalizing results…",
];

export default function ComparePage() {
  const router = useRouter();
  const [userName, setUserName] = useState("");
  const [step, setStep] = useState<Step>("select");
  const [showPairHints, setShowPairHints] = useState(false);

  // Slots: start with 2, expandable to 5
  const [slots, setSlots] = useState<DocSlotState[]>([
    { docType: "", file: null },
    { docType: "", file: null },
  ]);

  // Comparison state
  const [comparing, setComparing] = useState(false);
  const [compareStage, setCompareStage] = useState<string | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [result, setResult] = useState<DirectCompareResponse | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) { router.push("/login"); return; }
    authApi.me().then((r) => setUserName(r.data.full_name)).catch(() => router.push("/login"));
  }, [router]);

  // ── Slot management ───────────────────────────────────────────────────
  function addSlot() {
    if (slots.length >= MAX_SLOTS) return;
    setSlots((prev) => [...prev, { docType: "", file: null }]);
  }

  function removeSlot(idx: number) {
    if (slots.length <= MIN_SLOTS) return;
    setSlots((prev) => prev.filter((_, i) => i !== idx));
  }

  function updateSlotType(idx: number, val: string) {
    setSlots((prev) => prev.map((s, i) => (i === idx ? { ...s, docType: val } : s)));
  }

  function setSlotFile(idx: number, file: File) {
    setSlots((prev) => prev.map((s, i) => (i === idx ? { ...s, file } : s)));
  }

  function clearSlotFile(idx: number) {
    setSlots((prev) => prev.map((s, i) => (i === idx ? { ...s, file: null } : s)));
  }

  function handleReset() {
    setResult(null);
    setCompareError(null);
    setCompareStage(null);
    setStep("select");
  }

  async function handleCompare() {
    const validSlots = slots.filter((s) => s.file !== null && s.docType !== "");
    if (validSlots.length < 2) {
      setCompareError("Please upload at least 2 documents and select their document types.");
      return;
    }

    setComparing(true);
    setCompareError(null);
    setStep("comparing");

    let stageIdx = 0;
    setCompareStage(COMPARE_STAGES[0]);
    const timer = setInterval(() => {
      stageIdx = (stageIdx + 1) % COMPARE_STAGES.length;
      setCompareStage(COMPARE_STAGES[stageIdx]);
    }, 2500);

    try {
      const files = validSlots.map((s) => s.file!);
      const docTypes = validSlots.map((s) => s.docType);
      const res = await directCompareApi.compare(files, docTypes);
      clearInterval(timer);
      setResult(res.data);
      setStep("results");
    } catch (err: unknown) {
      clearInterval(timer);
      setStep("select");
      let msg = "Document comparison failed. Please ensure both files are clear certificates/documents.";
      if (err instanceof Error) msg = err.message;
      setCompareError(msg);
    } finally {
      clearInterval(timer);
      setComparing(false);
      setCompareStage(null);
    }
  }

  async function handleDownloadPdf() {
    const validSlots = slots.filter((s) => s.file !== null && s.docType !== "");
    if (validSlots.length < 2) return;
    const files = validSlots.map((s) => s.file!);
    const docTypes = validSlots.map((s) => s.docType);

    setDownloadingPdf(true);
    setPdfError(null);
    try {
      await directCompareApi.downloadPdf(files, docTypes);
    } catch (err: unknown) {
      let msg = "PDF generation failed. Please try again.";
      if (err instanceof Error) msg = err.message;
      setPdfError(msg);
    } finally {
      setDownloadingPdf(false);
    }
  }

  const validCount = slots.filter((s) => s.file !== null).length;
  const validWithTypes = slots.filter((s) => s.file !== null && s.docType !== "").length;
  const canCompare = validCount >= 2 && validCount === validWithTypes;

  return (
    <main className="min-h-screen px-4 sm:px-6 py-8 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <header className="flex items-center justify-between pb-6 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <Logo size="md" />
          <div>
            <span className="text-lg font-bold text-slate-900 block font-sans">CertiVerify AI</span>
            <span className="text-[10px] uppercase font-mono tracking-wider text-slate-600 font-medium">Document Comparison</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs text-slate-500 hidden sm:block">Signed in as {userName || "…"}</span>
          <Link
            href="/dashboard"
            className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-indigo-600 font-medium transition"
          >
            <ArrowLeft size={14} /> Back to Dashboard
          </Link>
        </div>
      </header>

      {/* Page title */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <GitCompare className="text-indigo-600" size={24} />
          Intelligent Document Comparison
        </h1>
        <p className="text-slate-500 mt-1 text-xs sm:text-sm">
          Upload 2–5 documents, run field-by-field AI comparison with fuzzy matching and consistency analysis.
        </p>

        {/* Supported pairs collapsible */}
        <button
          onClick={() => setShowPairHints((v) => !v)}
          className="mt-3 flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-700 font-medium transition"
        >
          <Info size={13} />
          {showPairHints ? "Hide" : "Show"} supported document pairs
          <ChevronDown size={13} className={`transition-transform ${showPairHints ? "rotate-180" : ""}`} />
        </button>
        {showPairHints && (
          <div className="mt-2 flex flex-wrap gap-2">
            {SUPPORTED_PAIRS.map((p) => (
              <span
                key={p}
                className="text-xs bg-indigo-50 border border-indigo-200 text-indigo-700 rounded-full px-3 py-1 font-medium"
              >
                {p}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── SELECT + UPLOAD step ──────────────────────────────────────────── */}
      {step === "select" && (
        <div className="space-y-5">
          {compareError && (
            <div className="flex items-center gap-2 bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded-xl px-4 py-3">
              <AlertTriangle size={16} />
              {compareError}
            </div>
          )}

          {/* Document slots */}
          <div className="space-y-4">
            {slots.map((slot, idx) => (
              <SlotRow
                key={idx}
                slotIndex={idx}
                docType={slot.docType}
                file={slot.file}
                canRemove={slots.length > MIN_SLOTS}
                onDocTypeChange={(v) => updateSlotType(idx, v)}
                onFileClear={() => clearSlotFile(idx)}
                onFileSet={(f) => setSlotFile(idx, f)}
                onRemove={() => removeSlot(idx)}
              />
            ))}
          </div>

          {/* Add document button */}
          {slots.length < MAX_SLOTS && (
            <button
              onClick={addSlot}
              className="w-full rounded-xl border border-dashed border-slate-300 text-slate-600 hover:text-indigo-600 hover:border-indigo-400 py-3 text-sm transition flex items-center justify-center gap-2 bg-white"
            >
              <Plus size={15} /> Add Document {slots.length + 1}
              <span className="text-xs text-slate-400">(max {MAX_SLOTS})</span>
            </button>
          )}

          {/* Requirements hint */}
          {!canCompare && (
            <div className="text-xs text-slate-500 text-center space-y-0.5">
              {validCount < 2 && <p>→ Select and upload at least 2 documents</p>}
              {validCount >= 2 && validWithTypes < validCount && <p>→ Select a document type for each uploaded document</p>}
            </div>
          )}

          <Button
            id="run-comparison-btn"
            onClick={handleCompare}
            disabled={!canCompare || comparing}
            loading={comparing}
            variant="primary"
            size="lg"
            className="w-full text-sm font-semibold"
            icon={<GitCompare size={18} />}
          >
            {comparing ? (compareStage ?? "Running…") : "Run Comparison"}
          </Button>
        </div>
      )}

      {/* ── COMPARING ───────────────────────────────────────────────────── */}
      {step === "comparing" && (
        <div className="text-center py-20 space-y-5 bg-white border border-slate-200 rounded-xl p-8 shadow-sm">
          <div className="relative inline-block">
            <Loader2 size={56} className="animate-spin text-indigo-600 mx-auto" />
            <Sparkles size={20} className="absolute -top-1 -right-1 text-emerald-500 animate-pulse" />
          </div>
          <div>
            <p className="text-slate-900 font-semibold text-lg">{compareStage ?? "Processing…"}</p>
            <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-md mx-auto">
              Running OCR on all uploaded documents and performing intelligent field comparison.
            </p>
          </div>
          {/* Stage progress pills */}
          <div className="flex justify-center flex-wrap gap-2 max-w-lg mx-auto">
            {COMPARE_STAGES.map((s) => (
              <span
                key={s}
                className={`text-[10px] font-mono px-2.5 py-1 rounded-full border transition ${
                  s === compareStage
                    ? "bg-indigo-50 border-indigo-300 text-indigo-700 font-bold"
                    : "bg-slate-50 border-slate-200 text-slate-400"
                }`}
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── RESULTS ─────────────────────────────────────────────────────── */}
      {step === "results" && result && (
        <ComparisonResults
          result={result}
          onReset={handleReset}
          onDownloadPdf={handleDownloadPdf}
          downloadingPdf={downloadingPdf}
          pdfError={pdfError}
        />
      )}
    </main>
  );
}

// ── SlotRow sub-component ────────────────────────────────────────────────

interface SlotRowProps {
  slotIndex: number;
  docType: string;
  file: File | null;
  canRemove: boolean;
  onDocTypeChange: (val: string) => void;
  onFileClear: () => void;
  onFileSet: (f: File) => void;
  onRemove: () => void;
}

function SlotRow({
  slotIndex, docType, file, canRemove,
  onDocTypeChange, onFileClear, onFileSet, onRemove,
}: SlotRowProps) {
  const onDrop = useCallback(
    (accepted: File[]) => { if (accepted[0]) onFileSet(accepted[0]); },
    [onFileSet],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, maxFiles: 1,
    accept: {
      "application/pdf": [".pdf"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
    },
    maxSize: 15 * 1024 * 1024,
  });

  const num = slotIndex + 1;
  const isRequired = slotIndex < 2;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
      <div className="flex items-start gap-3">
        {/* Slot number badge */}
        <div className="flex flex-col items-center gap-1 pt-0.5 shrink-0">
          <span className={`w-6 h-6 rounded-full text-white text-xs font-bold flex items-center justify-center ${
            isRequired ? "bg-indigo-600" : "bg-slate-400"
          }`}>
            {num}
          </span>
          {!isRequired && (
            <span className="text-[9px] text-slate-400 font-mono">opt</span>
          )}
        </div>

        <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Doc type selector */}
          <div>
            <label className="text-xs font-semibold text-slate-700 mb-1 block">
              Document Type {isRequired ? "*" : "(optional)"}
            </label>
            <div className="relative">
              <select
                id={`doc-type-${num}`}
                value={docType}
                onChange={(e) => onDocTypeChange(e.target.value)}
                className="w-full appearance-none bg-white border border-slate-300 rounded-lg px-3 py-2 pr-8 text-xs sm:text-sm text-slate-900 font-medium focus:outline-none focus:border-indigo-600 focus:ring-2 focus:ring-indigo-600/20 transition cursor-pointer"
              >
                <option value="" className="text-slate-400">— Select type —</option>
                {MANUAL_DOC_TYPES.map((t) => (
                  <option key={t.value} value={t.value} className="text-slate-900 font-medium py-1">
                    {t.label}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            </div>
            {docType && (
              <p className="text-xs text-indigo-600 mt-1 flex items-center gap-1 font-medium">
                <Tag size={10} /> {typeLabel(docType)}
              </p>
            )}
          </div>

          {/* Dropzone or file preview */}
          <div>
            <label className="text-xs font-semibold text-slate-700 mb-1 block">Document File</label>
            {!file ? (
              <div
                {...getRootProps()}
                className={`rounded-lg border-2 border-dashed px-4 py-3 text-center cursor-pointer transition text-sm bg-slate-50/50 ${
                  isDragActive
                    ? "border-indigo-600 bg-indigo-50/50"
                    : "border-slate-300 hover:border-indigo-400 hover:bg-indigo-50/20"
                }`}
              >
                <input {...getInputProps()} />
                <Upload className="mx-auto mb-1 text-indigo-600" size={18} />
                <p className="text-slate-800 text-xs font-medium">
                  {isDragActive ? "Drop here…" : "Drag & drop or click"}
                </p>
                <p className="text-[10px] text-slate-400 mt-0.5">PDF / JPG / PNG · max 15 MB</p>
              </div>
            ) : (
              <div className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 flex items-center justify-between h-full">
                <div className="flex items-center gap-2 text-sm text-slate-800 min-w-0">
                  {file.type === "application/pdf"
                    ? <FileText size={16} className="text-indigo-600 shrink-0" />
                    : <ImageIcon size={16} className="text-indigo-600 shrink-0" />}
                  <span className="truncate text-xs font-medium">{file.name}</span>
                  <span className="text-slate-400 text-[10px] shrink-0">({(file.size / 1024).toFixed(0)} KB)</span>
                </div>
                <button
                  onClick={onFileClear}
                  className="text-slate-400 hover:text-rose-600 transition ml-2 shrink-0 p-1"
                  aria-label="Clear file"
                >
                  <X size={14} />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Remove slot button */}
        {canRemove && (
          <button
            onClick={onRemove}
            className="text-slate-400 hover:text-rose-600 transition mt-1 shrink-0 p-1"
            title="Remove this slot"
          >
            <Minus size={16} />
          </button>
        )}
      </div>
    </div>
  );
}

// ── ComparisonResults sub-component ──────────────────────────────────────

function ComparisonResults({
  result, onReset, onDownloadPdf, downloadingPdf, pdfError,
}: {
  result: DirectCompareResponse;
  onReset: () => void;
  onDownloadPdf: () => void;
  downloadingPdf: boolean;
  pdfError: string | null;
}) {
  const matchCount   = result.comparison.filter((r) => r.status === "match").length;
  const partialCount = result.comparison.filter((r) => r.status === "partial").length;
  const mismatchCount= result.comparison.filter((r) => r.status === "mismatch").length;
  const missingCount = result.comparison.filter((r) => r.status === "missing").length;
  const pct = result.comparison_score ?? result.similarity_percentage;
  const isIdentical  = result.comparison_type === "identical_document";

  const scoreColor = pct >= 80 ? "text-emerald-700" : pct >= 60 ? "text-amber-700" : "text-rose-700";
  const scoreBg    = pct >= 80 ? "bg-emerald-50/70 border-emerald-200"
                   : pct >= 60 ? "bg-amber-50/70 border-amber-200"
                   : "bg-rose-50/70 border-rose-200";

  return (
    <div className="space-y-6">
      {/* Identical Documents Banner */}
      {isIdentical && (
        <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl px-5 py-3 text-sm font-semibold shadow-sm">
          <CheckCircle2 size={18} className="shrink-0 text-emerald-600" />
          <span>Identical Documents Detected — The uploaded documents are exact copies. No field differences were found.</span>
        </div>
      )}

      {/* ── Score banner ─────────────────────────────────────────────── */}
      <div className={`rounded-xl border px-6 py-5 ${scoreBg} flex flex-col sm:flex-row items-center justify-between gap-4 shadow-sm`}>
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
            Overall Consistency Score
          </p>
          <p className={`text-5xl font-black ${scoreColor} font-mono`}>{pct}%</p>
          <div className="flex items-center flex-wrap gap-3 mt-2 text-xs font-semibold">
            <span className="text-emerald-700">✓ {matchCount} match{matchCount !== 1 ? "es" : ""}</span>
            {partialCount > 0 && (
              <span className="text-amber-700">~ {partialCount} partial</span>
            )}
            <span className="text-rose-700">✗ {mismatchCount} mismatch{mismatchCount !== 1 ? "es" : ""}</span>
            <span className="text-slate-500">— {missingCount} missing</span>
          </div>
        </div>
        <div className="text-right text-xs text-slate-600 space-y-1.5">
          <div className="flex items-center gap-2 justify-end">
            <GitCompare size={12} className="text-indigo-600" />
            <span className="text-slate-800 font-semibold">{result.pair_hint}</span>
          </div>
          <div className="flex items-center gap-2 justify-end font-mono text-[11px] text-slate-500">
            <TrendingUp size={12} />
            <span>OCR: {(result.doc1_ocr_accuracy * 100).toFixed(0)}% / {(result.doc2_ocr_accuracy * 100).toFixed(0)}%</span>
          </div>
        </div>
      </div>

      {/* ── AI Summary ────────────────────────────────────────────────── */}
      {result.ai_summary && result.ai_summary.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 px-5 py-4 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={16} className="text-indigo-600" />
            <h2 className="text-sm font-semibold text-slate-900">AI Consistency Analysis</h2>
          </div>
          <ul className="space-y-2">
            {result.ai_summary.map((bullet, i) => {
              const isGood    = bullet.startsWith("✅");
              const isWarn    = bullet.startsWith("⚠️");
              const isBad     = bullet.startsWith("❌");
              return (
                <li
                  key={i}
                  className={`text-xs rounded-lg px-3 py-2 border leading-relaxed font-sans ${
                    isGood    ? "bg-emerald-50/50 border-emerald-200 text-emerald-800"
                    : isWarn  ? "bg-amber-50/50 border-amber-200 text-amber-800"
                    : isBad   ? "bg-rose-50/50 border-rose-200 text-rose-800"
                    : "bg-slate-50 border-slate-200 text-slate-700"
                  }`}
                >
                  {bullet}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* ── Field-by-field table ───────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-900">Field-by-Field Comparison</h2>
          <span className="text-xs font-mono text-slate-500">{result.comparison.length} fields compared</span>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 px-4 py-2 border-b border-slate-100 bg-slate-50/50 text-[10px] font-semibold">
          <span className="flex items-center gap-1 text-emerald-700"><CheckCircle2 size={10} /> Match (≥82%)</span>
          <span className="flex items-center gap-1 text-amber-700"><AlertTriangle size={10} /> Partial (60–81%)</span>
          <span className="flex items-center gap-1 text-rose-700"><X size={10} /> Mismatch (&lt;60%)</span>
          <span className="text-slate-400">— Missing</span>
        </div>

        {/* Header */}
        <div className="grid grid-cols-[1.1fr_1fr_1fr_0.7fr] text-[10px] font-mono uppercase text-slate-500 bg-slate-50 px-4 py-2.5 border-b border-slate-200">
          <span>Field</span>
          <span>Document 1</span>
          <span>Document 2</span>
          <span className="text-center">Result</span>
        </div>

        <div className="divide-y divide-slate-100">
          {result.comparison.map((row) => (
            <ComparisonRow key={row.field} row={row} />
          ))}
        </div>
      </div>

      {/* ── Actions ───────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row gap-3">
        <Button
          id="download-compare-pdf-btn"
          onClick={onDownloadPdf}
          disabled={downloadingPdf}
          loading={downloadingPdf}
          variant="primary"
          size="md"
          className="flex-1"
          icon={<FileDown size={16} />}
        >
          {downloadingPdf ? "Generating PDF…" : "Download Comparison Report"}
        </Button>
        <Button
          id="compare-reset-btn"
          onClick={onReset}
          variant="secondary"
          size="md"
          className="flex-1"
        >
          Compare Different Documents
        </Button>
      </div>

      {pdfError && (
        <div className="flex items-center gap-2 bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded-xl px-4 py-3">
          <AlertTriangle size={14} /> {pdfError}
        </div>
      )}
    </div>
  );
}

// ── ComparisonRow ─────────────────────────────────────────────────────────

function ComparisonRow({ row }: { row: FieldComparisonRow }) {
  const statusStyles: Record<string, string> = {
    match:    "border-l-4 border-emerald-500",
    partial:  "border-l-4 border-amber-500",
    mismatch: "border-l-4 border-rose-500",
    missing:  "border-l-4 border-slate-300 opacity-60",
  };

  const valueStyles: Record<string, string> = {
    match:    "text-emerald-700 font-medium",
    partial:  "text-amber-700 font-medium",
    mismatch: "text-rose-700 font-medium",
    missing:  "text-slate-400 italic",
  };

  const badge: Record<string, React.ReactNode> = {
    match: (
      <div className="flex flex-col items-center gap-0.5">
        <span className="inline-flex items-center gap-1 text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full px-2 py-0.5 font-semibold">
          <CheckCircle2 size={9} /> Match
        </span>
        {row.similarity != null && (
          <span className="text-[9px] font-mono text-emerald-600">{row.similarity}%</span>
        )}
      </div>
    ),
    partial: (
      <div className="flex flex-col items-center gap-0.5">
        <span className="inline-flex items-center gap-1 text-[10px] bg-amber-50 text-amber-700 border border-amber-200 rounded-full px-2 py-0.5 font-semibold">
          <AlertTriangle size={9} /> Partial
        </span>
        {row.similarity != null && (
          <span className="text-[9px] font-mono text-amber-600">{row.similarity}%</span>
        )}
      </div>
    ),
    mismatch: (
      <div className="flex flex-col items-center gap-0.5">
        <span className="inline-flex items-center gap-1 text-[10px] bg-rose-50 text-rose-700 border border-rose-200 rounded-full px-2 py-0.5 font-semibold">
          <AlertTriangle size={9} /> Mismatch
        </span>
        {row.similarity != null && (
          <span className="text-[9px] font-mono text-rose-600">{row.similarity}%</span>
        )}
      </div>
    ),
    missing: (
      <span className="inline-flex text-[10px] bg-slate-100 text-slate-500 border border-slate-200 rounded-full px-2 py-0.5 font-medium">
        Missing
      </span>
    ),
  };

  return (
    <div className={`grid grid-cols-[1.1fr_1fr_1fr_0.7fr] px-4 py-3 items-start gap-2 hover:bg-slate-50/50 transition-colors ${statusStyles[row.status]}`}>
      <p className="text-xs font-semibold text-slate-700 pt-0.5">{row.field_label}</p>
      <p className={`text-xs break-words font-mono ${valueStyles[row.status]}`}>
        {row.doc1_value ?? "—"}
      </p>
      <p className={`text-xs break-words font-mono ${valueStyles[row.status]}`}>
        {row.doc2_value ?? "—"}
      </p>
      <div className="flex justify-center">
        {badge[row.status]}
      </div>
    </div>
  );
}
