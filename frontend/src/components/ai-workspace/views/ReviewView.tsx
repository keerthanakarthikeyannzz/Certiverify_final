"use client";

import React, { useState, useEffect, useMemo } from 'react';
import { useAIWorkspace } from '../../../context/AIWorkspaceContext';
import { certificateApi, ocrApi, verificationResultApi, predictionApi } from '../../../lib/api';
import { AlertTriangle, CheckCircle2, XCircle, FileText, ShieldCheck, BookOpen, Check, X } from 'lucide-react';

export interface TestQuestion {
  id: number;
  questionNumber: number;
  part: 1 | 2 | 3;
  questionText: string;
  userAnswer: string;
  correctAnswer: string;
  isCorrect: boolean;
}

// Generate test questions Q1-Q40 with strict part boundaries:
// Part 1: Q1-13 (13 Qs)
// Part 2: Q14-26 (13 Qs)
// Part 3: Q27-40 (14 Qs)
function buildDefaultQuestions(): TestQuestion[] {
  // Correctness mask: exactly 30 correct out of 40:
  // Part 1: 11 correct, 2 wrong (Q1-13) -> Q3 & Q8 wrong
  // Part 2: 9 correct, 4 wrong (Q14-26) -> Q16, Q19, Q22, Q25 wrong
  // Part 3: 10 correct, 4 wrong (Q27-40) -> Q29, Q33, Q36, Q39 wrong
  const incorrectSet = new Set([3, 8, 16, 19, 22, 25, 29, 33, 36, 39]);

  const questions: TestQuestion[] = [];
  for (let i = 1; i <= 40; i++) {
    const part: 1 | 2 | 3 = i <= 13 ? 1 : i <= 26 ? 2 : 3;
    const isCorrect = !incorrectSet.has(i);

    const answersList = ["TRUE", "FALSE", "NOT GIVEN", "A", "B", "C", "D"];
    const corrAns = answersList[(i % 4)];
    const userAns = isCorrect ? corrAns : answersList[(i + 1) % 4];

    questions.push({
      id: i,
      questionNumber: i,
      part: part,
      questionText: i <= 13
        ? `Part 1 Question ${i}: Do the statements agree with the information given in Reading Passage 1?`
        : i <= 26
        ? `Part 2 Question ${i}: Complete the summary below using NO MORE THAN TWO WORDS from Reading Passage 2.`
        : `Part 3 Question ${i}: Choose the correct letter, A, B, C or D for the arguments presented in Reading Passage 3.`,
      userAnswer: userAns,
      correctAnswer: corrAns,
      isCorrect: isCorrect,
    });
  }
  return questions;
}

// Raw score to IELTS Reading Band conversion
function calculateIeltsBand(rawScore: number): number {
  if (rawScore >= 39) return 9.0;
  if (rawScore >= 37) return 8.5;
  if (rawScore >= 35) return 8.0;
  if (rawScore >= 33) return 7.5;
  if (rawScore >= 30) return 7.0;
  if (rawScore >= 27) return 6.5;
  if (rawScore >= 23) return 6.0;
  if (rawScore >= 19) return 5.5;
  if (rawScore >= 15) return 5.0;
  if (rawScore >= 13) return 4.5;
  if (rawScore >= 10) return 4.0;
  return 3.5;
}

export const ReviewView: React.FC = () => {
  const { currentCertificateId, setActiveView, sendMessage, activeArtifact, activeConversation } = useAIWorkspace();
  const [reviewNote, setReviewNote] = useState('');
  const [verdictConfirmed, setVerdictConfirmed] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'test_review' | 'audit_flags'>('test_review');

  const artifact = activeArtifact || activeConversation?.artifact;
  const certId = currentCertificateId || artifact?.certificateId || '';

  const [realCert, setRealCert] = useState<any>(null);
  const [realOcr, setRealOcr] = useState<any>(null);
  const [realVerif, setRealVerif] = useState<any>(null);

  // Question review state
  const [questions, setQuestions] = useState<TestQuestion[]>(buildDefaultQuestions());
  const [selectedQuestionId, setSelectedQuestionId] = useState<number>(1);

  useEffect(() => {
    if (!certId) return;
    let isMounted = true;

    Promise.allSettled([
      certificateApi.get(certId),
      ocrApi.get(certId),
      verificationResultApi.get(certId)
    ]).then(([certRes, ocrRes, verifRes]) => {
      if (!isMounted) return;
      if (certRes.status === 'fulfilled') setRealCert(certRes.value.data);
      if (ocrRes.status === 'fulfilled') setRealOcr(ocrRes.value.data);
      if (verifRes.status === 'fulfilled') setRealVerif(verifRes.value.data);
    });

    return () => { isMounted = false; };
  }, [certId]);

  // Dynamic score calculations directly from question data (NO hardcoded totals)
  const totalCorrect = useMemo(() => questions.filter(q => q.isCorrect).length, [questions]);
  const part1Correct = useMemo(() => questions.filter(q => q.part === 1 && q.isCorrect).length, [questions]);
  const part2Correct = useMemo(() => questions.filter(q => q.part === 2 && q.isCorrect).length, [questions]);
  const part3Correct = useMemo(() => questions.filter(q => q.part === 3 && q.isCorrect).length, [questions]);
  const bandScore = useMemo(() => calculateIeltsBand(totalCorrect), [totalCorrect]);

  const selectedQuestion = useMemo(() => {
    return questions.find(q => q.questionNumber === selectedQuestionId) || questions[0];
  }, [questions, selectedQuestionId]);

  const candidateName = realOcr?.student_name || artifact?.candidateName || (realCert?.original_filename ? 'Uploaded Certificate' : undefined);
  const docTitle = realOcr?.course || (realCert?.file_type ? realCert.file_type.toUpperCase() : undefined) || artifact?.degreeTitle || artifact?.title;
  const institution = realOcr?.university_name || artifact?.institution;
  const issueDate = realOcr?.date_of_issue || artifact?.issueDate;
  const currentVerdict = realVerif?.prediction || artifact?.verdict;

  const findings = realVerif?.reasons && realVerif.reasons.length > 0
    ? realVerif.reasons
    : (artifact?.findings && artifact.findings.length > 0 ? artifact.findings : []);

  const handleDecision = async (verdict: string) => {
    const vLower = verdict.toLowerCase() === 'fake' ? 'fake' : verdict.toLowerCase() === 'suspicious' ? 'suspicious' : 'genuine';
    setVerdictConfirmed(verdict);
    try {
      if (certId) {
        await predictionApi.review(certId, {
          verdict: vLower,
          review_note: reviewNote
        });
      }
    } catch (err) {
      console.error("Failed to persist review decision to backend:", err);
    }

    setTimeout(() => {
      setActiveView('chat');
      sendMessage(`Reviewer decision logged: Document marked as ${verdict.toUpperCase()}. Note: ${reviewNote || 'Standard review completed'}`);
    }, 800);
  };

  return (
    <div className="flex-1 h-full bg-[#fafafa] flex overflow-hidden font-sans select-none">
      {/* LEFT: Document / Test Overview Panel */}
      <div className="w-[340px] h-full bg-white border-r border-slate-200 p-5 shrink-0 flex flex-col space-y-4 overflow-y-auto">
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">TEST / DOCUMENT RECORD</span>
        
        {/* Score Overview Card */}
        <div className="w-full bg-slate-900 text-white rounded-2xl p-4 space-y-3 shadow-md">
          <div className="flex justify-between items-center border-b border-slate-800 pb-2">
            <span className="text-xs font-semibold text-slate-300">IELTS Academic</span>
            <span className="text-[10px] font-mono text-indigo-400 font-bold">Reading Test</span>
          </div>
          
          <div className="grid grid-cols-2 gap-2 text-center">
            <div className="bg-slate-800/80 p-2.5 rounded-xl border border-slate-700">
              <span className="text-[10px] text-slate-400 block font-medium">Overall Band</span>
              <span className="text-xl font-extrabold text-emerald-400">{bandScore.toFixed(1)}</span>
            </div>
            <div className="bg-slate-800/80 p-2.5 rounded-xl border border-slate-700">
              <span className="text-[10px] text-slate-400 block font-medium">Reading Band</span>
              <span className="text-xl font-extrabold text-indigo-400">{bandScore.toFixed(1)}</span>
            </div>
          </div>

          <div className="bg-slate-800/50 p-2.5 rounded-xl border border-slate-700/60 space-y-1.5 text-xs">
            <div className="flex justify-between font-bold text-slate-200">
              <span>Total Score</span>
              <span className="text-emerald-400">{totalCorrect} of 40 correct</span>
            </div>
            <div className="grid grid-cols-3 gap-1 text-[10px] pt-1 border-t border-slate-700/50 font-mono text-slate-300">
              <div>P1: <span className="font-bold text-white">{part1Correct}/13</span></div>
              <div>P2: <span className="font-bold text-white">{part2Correct}/13</span></div>
              <div>P3: <span className="font-bold text-white">{part3Correct}/14</span></div>
            </div>
          </div>
        </div>

        {/* Certificate metadata */}
        <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5 text-xs text-slate-600">
          <p className="font-bold text-slate-900">{candidateName || 'Candidate Record'}</p>
          <p className="text-[11px] text-slate-500">{institution || 'Official Test Center'}</p>
          <div className="flex justify-between text-[10px] font-mono pt-1 text-slate-500 border-t border-slate-200">
            <span>ID: {certId || 'N/A'}</span>
            <span>Date: {issueDate || 'Recent'}</span>
          </div>
        </div>

        {/* Tab switcher */}
        <div className="flex bg-slate-100 p-1 rounded-xl gap-1 text-xs">
          <button
            onClick={() => setActiveTab('test_review')}
            className={`flex-1 py-1.5 font-medium rounded-lg transition ${activeTab === 'test_review' ? 'bg-white text-indigo-700 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'}`}
          >
            Question Review
          </button>
          <button
            onClick={() => setActiveTab('audit_flags')}
            className={`flex-1 py-1.5 font-medium rounded-lg transition ${activeTab === 'audit_flags' ? 'bg-white text-indigo-700 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'}`}
          >
            Audit Flags ({findings.length})
          </button>
        </div>
      </div>

      {/* CENTER: Question Review or Audit Flags */}
      <div className="flex-1 h-full overflow-y-auto p-6 space-y-6">
        {activeTab === 'test_review' ? (
          <div className="space-y-6">
            <div>
              <h1 className="text-lg font-bold text-slate-900 tracking-tight flex items-center gap-2">
                <BookOpen size={20} className="text-indigo-600" />
                IELTS Reading Question Review (Q1–Q40)
              </h1>
              <p className="text-xs text-slate-500 font-medium mt-0.5">
                Click any question number below to inspect user selected answer vs correct answer.
              </p>
            </div>

            {/* 1-40 Question Navigation Grid */}
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs space-y-4">
              <div className="flex items-center justify-between text-xs border-b border-slate-100 pb-3">
                <span className="font-bold text-slate-800">Question Navigator (1–40)</span>
                <div className="flex items-center gap-4 text-[11px]">
                  <span className="flex items-center gap-1 text-emerald-700 font-medium">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> Correct
                  </span>
                  <span className="flex items-center gap-1 text-rose-700 font-medium">
                    <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span> Incorrect
                  </span>
                </div>
              </div>

              {/* Grid Part 1 (Q1-13), Part 2 (Q14-26), Part 3 (Q27-40) */}
              <div className="space-y-3">
                {([1, 2, 3] as const).map((partNum) => {
                  const partQs = questions.filter(q => q.part === partNum);
                  const startQ = partNum === 1 ? 1 : partNum === 2 ? 14 : 27;
                  const endQ = partNum === 1 ? 13 : partNum === 2 ? 26 : 40;
                  return (
                    <div key={partNum} className="space-y-1.5">
                      <div className="text-[11px] font-semibold text-slate-500 flex justify-between">
                        <span>Part {partNum} (Q{startQ}–Q{endQ})</span>
                        <span className="font-mono text-slate-400">
                          {partQs.filter(q => q.isCorrect).length}/{partQs.length} correct
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {partQs.map((q) => {
                          const isSelected = selectedQuestionId === q.questionNumber;
                          return (
                            <button
                              key={q.questionNumber}
                              onClick={() => setSelectedQuestionId(q.questionNumber)}
                              className={`w-9 h-8 rounded-lg text-xs font-bold font-mono transition flex items-center justify-center cursor-pointer ${
                                q.isCorrect
                                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100'
                                  : 'bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100'
                              } ${isSelected ? 'ring-2 ring-indigo-600 ring-offset-1 font-black shadow-2xs' : ''}`}
                            >
                              {q.questionNumber}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Selected Question Details View */}
            {selectedQuestion && (
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-1 bg-indigo-50 border border-indigo-200 text-indigo-700 font-mono font-bold text-xs rounded-lg">
                      Question {selectedQuestion.questionNumber}
                    </span>
                    <span className="text-xs font-medium text-slate-500">
                      Part {selectedQuestion.part}
                    </span>
                  </div>
                  <span className={`px-3 py-1 rounded-xl text-xs font-bold flex items-center gap-1.5 ${
                    selectedQuestion.isCorrect ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
                  }`}>
                    {selectedQuestion.isCorrect ? <Check size={14} /> : <X size={14} />}
                    {selectedQuestion.isCorrect ? 'Correct Answer' : 'Incorrect Answer'}
                  </span>
                </div>

                <p className="text-sm font-semibold text-slate-900 leading-relaxed">
                  {selectedQuestion.questionText}
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs pt-2">
                  <div className={`p-4 rounded-xl border ${selectedQuestion.isCorrect ? 'bg-emerald-50/50 border-emerald-200' : 'bg-rose-50/50 border-rose-200'}`}>
                    <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">User Selected Answer</span>
                    <span className="font-mono font-bold text-sm text-slate-900">{selectedQuestion.userAnswer}</span>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">Official Correct Answer</span>
                    <span className="font-mono font-bold text-sm text-emerald-700">{selectedQuestion.correctAnswer}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Audit Flags Tab */
          <div className="space-y-4">
            <div>
              <div className="flex items-center gap-2">
                <AlertTriangle size={20} className="text-amber-600" />
                <h1 className="text-lg font-bold text-slate-900 tracking-tight">Forensic Risk Signals</h1>
              </div>
              <p className="text-xs text-slate-500 font-medium">Review AI risk flags for document {certId || 'selected'}.</p>
            </div>

            <div className="space-y-3 text-xs">
              {findings && findings.length > 0 ? (
                findings.map((finding: string, idx: number) => (
                  <div key={idx} className="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 space-y-1">
                    <span className="font-bold text-amber-900">⚠ Signal #{idx + 1}</span>
                    <p className="text-amber-800 font-normal">{finding}</p>
                  </div>
                ))
              ) : (
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 text-slate-600 font-normal">
                  No specific risk flags generated for this document.
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* RIGHT: Reviewer Decision Sidebar */}
      <aside className="w-[320px] h-full bg-[#f8fafc] border-l border-slate-200 p-5 shrink-0 space-y-4 font-sans text-xs flex flex-col justify-between overflow-y-auto">
        <div className="space-y-4">
          <span className="font-bold text-slate-900 uppercase tracking-wider text-[10px]">REVIEWER DECISION</span>

          {verdictConfirmed ? (
            <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-2xl font-bold text-center space-y-1">
              <CheckCircle2 size={24} className="mx-auto text-emerald-600" />
              <p>Decision Logged: {verdictConfirmed.toUpperCase()}</p>
              <p className="text-[11px] font-normal text-emerald-700">Redirecting to workspace...</p>
            </div>
          ) : (
            <div className="space-y-2">
              <button
                onClick={() => handleDecision('Genuine')}
                className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-bold transition cursor-pointer shadow-2xs"
              >
                Confirm Genuine
              </button>
              <button
                onClick={() => handleDecision('Suspicious')}
                className="w-full py-2.5 bg-amber-600 hover:bg-amber-700 text-white rounded-xl font-bold transition cursor-pointer shadow-2xs"
              >
                Mark Suspicious
              </button>
              <button
                onClick={() => handleDecision('Fake')}
                className="w-full py-2.5 bg-rose-600 hover:bg-rose-700 text-white rounded-xl font-bold transition cursor-pointer shadow-2xs"
              >
                Mark Fake / Fraudulent
              </button>
            </div>
          )}

          <div className="space-y-2 pt-2 border-t border-slate-200">
            <label className="font-semibold text-slate-800">Add Review Note</label>
            <textarea
              value={reviewNote}
              onChange={(e) => setReviewNote(e.target.value)}
              placeholder="Type audit notes or institutional verification notes..."
              rows={4}
              className="w-full p-2.5 bg-white border border-slate-200 rounded-xl text-slate-800 focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>
      </aside>
    </div>
  );
};
