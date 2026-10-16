"use client";

import React, { createContext, useContext, useState, useCallback } from 'react';
import {
  AIConversation,
  AIMessage,
  AIMode,
  ActiveView,
  DocumentArtifact,
  EvidenceItem,
  VerificationSignal,
  AnalysisStage,
  AINotification,
  CertificateRecord,
  CertificateStatus
} from '../types/ai-workspace';
import {
  certificateApi,
  ocrApi,
  documentTypeApi,
  verificationApi,
  fraudApi,
  trustScoreApi,
  predictionApi,
  reportApi,
  pipelineApi,
  getAccessToken,
} from '../lib/api';
import { INITIAL_ARTIFACTS } from '../lib/ai-sample-data';

export const INITIAL_CERTIFICATE_RECORDS: CertificateRecord[] = [];
export const INITIAL_NOTIFICATIONS: AINotification[] = [];

interface AIWorkspaceContextType {
  currentCertificateId: string | null;
  setCurrentCertificateId: (id: string | null) => void;
  conversations: AIConversation[];
  activeConversationId: string;
  activeConversation: AIConversation | undefined;
  activeView: ActiveView;
  setActiveView: (view: ActiveView) => void;
  mode: AIMode;
  setMode: (mode: AIMode) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  activeArtifact: DocumentArtifact | null;
  setActiveArtifact: (artifact: DocumentArtifact | null) => void;
  activeEvidenceId: number | null;
  setActiveEvidenceId: (id: number | null) => void;
  isSettingsOpen: boolean;
  setIsSettingsOpen: (open: boolean) => void;
  isNotificationsOpen: boolean;
  setIsNotificationsOpen: (open: boolean) => void;
  notifications: AINotification[];
  markNotificationAsRead: (id: string) => void;
  clearAllNotifications: () => void;
  certificateRecords: CertificateRecord[];
  isVoiceActive: boolean;
  toggleVoice: () => void;
  createNewConversation: () => void;
  selectConversation: (id: string) => void;
  sendMessage: (text: string, file?: File | { name: string; size: string; type: string; url?: string }) => Promise<void>;
  executeAction: (actionId: string, param?: string) => void;
}

const AIWorkspaceContext = createContext<AIWorkspaceContextType | undefined>(undefined);

export const AIWorkspaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentCertificateId, setCurrentCertificateIdState] = useState<string | null>(null);
  const currentCertificateIdRef = React.useRef<string | null>(null);

  const setCurrentCertificateId = useCallback((id: string | null) => {
    setCurrentCertificateIdState(id);
    currentCertificateIdRef.current = id;
    if (typeof window !== 'undefined') {
      if (id) {
        localStorage.setItem("cv_current_certificate_id", id);
      } else {
        localStorage.removeItem("cv_current_certificate_id");
      }
    }
  }, []);

  const [conversations, setConversations] = useState<AIConversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string>('conv-1');
  const [activeView, setActiveView] = useState<ActiveView>('chat');
  const [mode, setMode] = useState<AIMode>('verify');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [activeArtifact, setActiveArtifact] = useState<DocumentArtifact | null>(null);
  const [activeEvidenceId, setActiveEvidenceId] = useState<number | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [isNotificationsOpen, setIsNotificationsOpen] = useState<boolean>(false);
  const [notifications, setNotifications] = useState<AINotification[]>([]);
  const [certificateRecords, setCertificateRecords] = useState<CertificateRecord[]>([]);
  const [isVoiceActive, setIsVoiceActive] = useState<boolean>(false);

  // Load current certificate from backend on mount / refresh
  const loadCertificateById = useCallback(async (certId: string) => {
    if (!certId) return;
    try {
      const [certRes, ocrRes, verifRes] = await Promise.allSettled([
        certificateApi.get(certId),
        ocrApi.get(certId),
        verificationApi.get(certId)
      ]);

      if (certRes.status !== 'fulfilled') {
        if (typeof window !== 'undefined') {
          localStorage.removeItem("cv_current_certificate_id");
        }
        certificateApi.list().then(res => {
          if (res.data && res.data.length > 0) {
            const firstId = res.data[0].id;
            loadCertificateById(firstId);
          } else {
            setCurrentCertificateId(null);
          }
        }).catch(() => {
          setCurrentCertificateId(null);
        });
        return;
      }
      const certData = certRes.value.data;
      const ocrData = ocrRes.status === 'fulfilled' ? ocrRes.value.data : null;
      const verifData = verifRes.status === 'fulfilled' ? verifRes.value.data : null;

      const loadedArtifact: DocumentArtifact = {
        id: `art-${certId}`,
        title: `Verification Report — ${certData.original_filename}`,
        type: 'verification_report',
        certificateId: certId,
        trustScore: verifData?.trust_score != null ? Math.round(verifData.trust_score) : 0,
        verdict: verifData?.prediction ? (verifData.prediction as any) : 'genuine',
        candidateName: ocrData?.student_name || 'Not detected',
        institution: ocrData?.university_name || 'Not detected',
        degreeTitle: ocrData?.course || certData.original_filename || 'Document',
        issueDate: ocrData?.date_of_issue || 'Not detected',
        verificationId: `VER-${certId.slice(0, 8)}`,
        qrPayload: ocrData?.qr_code_data || 'Not detected',
        blockchainTxHash: verifData?.blockchain_tx_hash || (verifData?.evidence?.blockchain?.status === 'verified' ? 'Verified' : 'Not registered'),
        tamperScore: verifData?.evidence?.tampering?.score != null ? verifData.evidence.tampering.score / 100 : 0,
        summaryText: verifData?.explanation || `Loaded document ${certData.original_filename} (${certId}).`,
        findings: verifData?.reasons && verifData.reasons.length > 0 ? verifData.reasons : [
          `OCR Text extraction loaded (${Math.round((ocrData?.ocr_accuracy || 0) * 100)}% confidence)`,
          `Extracted candidate: ${ocrData?.student_name || 'Not detected'}`
        ]
      };

      setCurrentCertificateId(certId);
      setActiveArtifact(loadedArtifact);

      setConversations(prev => prev.map(c => {
        if (c.certificateId === certId || c.id === `conv-${certId}`) {
          return {
            ...c,
            trustScore: verifData?.trust_score != null ? Math.round(verifData.trust_score) : c.trustScore,
            verdict: verifData?.prediction ? (verifData.prediction as any) : c.verdict,
            artifact: loadedArtifact
          };
        }
        return c;
      }));
    } catch (err) {
      console.error("Failed to load current certificate on refresh:", err);
    }
  }, [setCurrentCertificateId]);

  const refreshHistory = useCallback(async () => {
    if (typeof window === 'undefined' || !getAccessToken()) return;
    try {
      const historyRes = await certificateApi.getHistory();
      const historyItems = historyRes.data;

      const loadedConvs: AIConversation[] = historyItems.map(item => {
        const formattedDate = new Date(item.timestamp).toLocaleDateString([], {
          year: 'numeric',
          month: 'short',
          day: 'numeric'
        });

        const convId = `conv-${item.certificate_id}`;
        const docTypeCategory = item.document_type ? item.document_type.replace(/_/g, ' ').toUpperCase() : 'DOCUMENT';

        const artifact: DocumentArtifact = {
          id: `art-${item.certificate_id}`,
          title: `Verification Report — ${item.filename}`,
          type: 'verification_report',
          certificateId: item.certificate_id,
          trustScore: item.trust_score != null ? Math.round(item.trust_score) : 0,
          verdict: item.prediction ? (item.prediction as any) : 'genuine',
          candidateName: 'Loaded from history',
          institution: 'Uploaded Document',
          degreeTitle: item.filename,
          issueDate: formattedDate,
          verificationId: item.report_reference || `VER-${item.certificate_id.slice(0, 8)}`,
          summaryText: `Persisted verification record for ${item.filename} (${item.certificate_id}).`,
          findings: [
            `Persisted Trust Score: ${item.trust_score != null ? item.trust_score : 'N/A'}/100`,
            `Persisted Verdict: ${item.prediction ? item.prediction.toUpperCase() : 'PENDING'}`,
            `Document Type: ${docTypeCategory}`
          ]
        };

        return {
          id: convId,
          title: `Verify ${item.filename}`,
          category: docTypeCategory as any,
          updatedAt: formattedDate,
          mode: 'verify',
          certificateName: item.filename,
          certificateId: item.certificate_id,
          verdict: item.prediction ? (item.prediction as any) : undefined,
          trustScore: item.trust_score != null ? Math.round(item.trust_score) : undefined,
          artifact: artifact,
          messages: [
            {
              id: `msg-hist-${item.certificate_id}`,
              sender: 'assistant',
              timestamp: formattedDate,
              verdict: item.prediction ? (item.prediction as any) : undefined,
              trustScore: item.trust_score != null ? Math.round(item.trust_score) : undefined,
              summaryNarrative: `Persisted backend record for ${item.filename} (ID: ${item.certificate_id}). Trust Score: ${item.trust_score != null ? Math.round(item.trust_score) : 'N/A'}/100. Prediction: ${item.prediction ? item.prediction.toUpperCase() : 'PENDING'}.`,
              artifactId: artifact.id
            }
          ]
        };
      });

      setConversations(loadedConvs);
    } catch (err) {
      console.error("Failed to fetch certificate history from backend:", err);
    }
  }, []);

  React.useEffect(() => {
    if (typeof window === 'undefined' || !getAccessToken()) return;

    refreshHistory();

    const savedId = localStorage.getItem("cv_current_certificate_id");
    if (savedId) {
      loadCertificateById(savedId);
    } else {
      certificateApi.list().then(res => {
        if (res.data && res.data.length > 0) {
          const firstId = res.data[0].id;
          loadCertificateById(firstId);
        }
      }).catch(() => {});
    }
  }, [loadCertificateById, refreshHistory]);

  const activeConversation = conversations.find(c => c.id === activeConversationId);

  const markNotificationAsRead = useCallback((id: string) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
  }, []);

  const clearAllNotifications = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  }, []);

  const toggleVoice = useCallback(() => {
    setIsVoiceActive(prev => {
      const next = !prev;
      if (next && typeof window !== 'undefined' && 'speechSynthesis' in window) {
        const synth = window.speechSynthesis;
        const utterance = new SpeechSynthesisUtterance('CertiVerify AI Voice Assistant active. How can I help verify your document?');
        synth.speak(utterance);
      }
      return next;
    });
  }, []);

  const selectConversation = useCallback((id: string) => {
    setActiveConversationId(id);
    setActiveView('chat');
    const selected = conversations.find(c => c.id === id);
    const targetCertId = selected?.certificateId || (id.startsWith('conv-') ? id.replace('conv-', '') : id);

    if (targetCertId) {
      setCurrentCertificateId(targetCertId);
      loadCertificateById(targetCertId);
    }

    if (selected) {
      if (selected.mode) setMode(selected.mode);
      if (selected.artifact) setActiveArtifact(selected.artifact);
      if (selected.messages && selected.messages.length > 0) {
        const lastMsg = selected.messages[selected.messages.length - 1];
        if (lastMsg.evidenceList && lastMsg.evidenceList.length > 0) {
          setActiveEvidenceId(lastMsg.evidenceList[0].id);
        }
      }
    }
  }, [conversations, setCurrentCertificateId, loadCertificateById]);

  const createNewConversation = useCallback(() => {
    const newId = `conv-${Date.now()}`;
    const newConv: AIConversation = {
      id: newId,
      title: 'New Verification Workspace',
      category: 'Today',
      updatedAt: 'Just now',
      mode: mode,
      messages: []
    };

    setConversations(prev => [newConv, ...prev]);
    setActiveConversationId(newId);
    setActiveView('chat');
    setActiveArtifact(null);
    setActiveEvidenceId(null);
  }, [mode]);

  const sendMessage = useCallback(async (text: string, file?: File | { name: string; size: string; type: string; url?: string }) => {
    if (!text.trim() && !file) return;

    let targetConvId = activeConversationId;
    let currentConv = conversations.find(c => c.id === targetConvId);

    if (!currentConv) {
      targetConvId = `conv-${Date.now()}`;
      currentConv = {
        id: targetConvId,
        title: file ? `Verify ${(file as any).name || 'Document'}` : text.slice(0, 30),
        category: 'Today',
        updatedAt: 'Just now',
        mode: mode,
        messages: []
      };
    }

    const userMsgId = `msg-u-${Date.now()}`;
    const userMessage: AIMessage = {
      id: userMsgId,
      sender: 'user',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text: text.trim(),
      attachedFile: file ? {
        name: (file as any).name || 'uploaded_document',
        size: typeof (file as any).size === 'number' ? `${(((file as any).size) / 1024 / 1024).toFixed(1)} MB` : '1.5 MB',
        type: (file as any).type || 'application/pdf',
        url: 'url' in (file as any) ? (file as any).url : undefined
      } : undefined
    };

    const assistantMsgId = `msg-a-${Date.now()}`;
    const initialStages: AnalysisStage[] = [
      { id: '1', label: 'Document Processing', status: 'running' },
      { id: '2', label: 'OCR Extraction', status: 'pending' },
      { id: '3', label: 'Document Classification', status: 'pending' },
      { id: '4', label: 'Field Extraction', status: 'pending' },
      { id: '5', label: 'QR Verification', status: 'pending' },
      { id: '6', label: 'Blockchain Verification', status: 'pending' },
      { id: '7', label: 'Tamper Detection', status: 'pending' },
      { id: '8', label: 'Duplicate Detection', status: 'pending' },
      { id: '9', label: 'Trust Score Calculation', status: 'pending' }
    ];

    const initialAssistantMessage: AIMessage = {
      id: assistantMsgId,
      sender: 'assistant',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      mode: mode,
      isStreaming: true,
      stages: initialStages
    };

    // Purge previous artifact and evidence context on new file upload
    if (file) {
      setActiveArtifact(null);
      setActiveEvidenceId(null);
    }

    setConversations(prev => {
      const exists = prev.some(c => c.id === targetConvId);
      if (!exists && currentConv) {
        return [{
          ...currentConv,
          artifact: file ? undefined : currentConv.artifact,
          verdict: file ? undefined : currentConv.verdict,
          trustScore: file ? undefined : currentConv.trustScore,
          messages: [userMessage, initialAssistantMessage]
        }, ...prev];
      }
      return prev.map(c => {
        if (c.id === targetConvId) {
          const title = c.messages.length === 0 ? (file ? `Verify ${(file as any).name}` : text.slice(0, 32)) : c.title;
          return {
            ...c,
            title,
            updatedAt: 'Just now',
            certificateName: file ? (file as any).name : c.certificateName,
            artifact: file ? undefined : c.artifact,
            verdict: file ? undefined : c.verdict,
            trustScore: file ? undefined : c.trustScore,
            messages: [...c.messages, userMessage, initialAssistantMessage]
          };
        }
        return c;
      });
    });

    setActiveView('chat');

    let newArtifact: DocumentArtifact | null = null;
    let verdict: CertificateStatus | 'undetermined' | undefined = undefined;
    let trustScore: number | undefined = undefined;
    let confidence = 0.95;
    let narrative = "Verification in progress...";
    let dynamicSignals: VerificationSignal[] = [];
    let dynamicEvidence: EvidenceItem[] = [];
    let computedOcrResult: any = null;
    let currentStages: AnalysisStage[] = [
      { id: '1', label: 'Document Processing', status: 'running' },
      { id: '2', label: 'OCR Extraction', status: 'pending' },
      { id: '3', label: 'Document Classification', status: 'pending' },
      { id: '4', label: 'Field Extraction', status: 'pending' },
      { id: '5', label: 'QR Verification', status: 'pending' },
      { id: '6', label: 'Blockchain Verification', status: 'pending' },
      { id: '7', label: 'Tamper Detection', status: 'pending' },
      { id: '8', label: 'Duplicate Detection', status: 'pending' },
      { id: '9', label: 'Trust Score Calculation', status: 'pending' }
    ];
    let executionSuccess = false;

    // Real Backend Pipeline execution if raw File instance is provided
    if (file && (file instanceof File || (file as any).size)) {
      const rawFile = file instanceof File ? file : null;
      let certId: string | null = null;
      let cert: any = null;

      try {
        if (!rawFile) {
          throw new Error("Invalid file attachment object provided");
        }

        // ── Stage 1: Document Upload ──────────────────────────────────────
        try {
          const uploadRes = await certificateApi.upload([rawFile]);
          cert = uploadRes.data.certificates[0];
          certId = cert.id;

          setCurrentCertificateId(certId);
          setActiveArtifact(null);
          setActiveEvidenceId(null);

          currentStages[0].status = 'completed';
          currentStages[1].status = 'running';

          setConversations(prev => prev.map(c => c.id === targetConvId ? {
            ...c,
            certificateId: certId || undefined,
            messages: c.messages.map(m => m.id === assistantMsgId ? { ...m, stages: [...currentStages] } : m)
          } : c));
        } catch (uploadErr: any) {
          currentStages[0].status = 'failed';
          const errMsg = uploadErr?.response?.data?.detail || uploadErr?.message || "File upload failed";
          narrative = `Document upload failed: ${typeof errMsg === 'object' ? JSON.stringify(errMsg) : errMsg}. Please check file type and size.`;
          throw new Error(`Upload Failed: ${errMsg}`);
        }

        // Stale guard: stop processing if another certificate was selected/uploaded
        if (!certId || certId !== currentCertificateIdRef.current) return;

        // ── Stage 2: OCR & Field Extraction ───────────────────────────────
        let ocrData: any = null;
        try {
          const ocrRes = await ocrApi.extract(certId);
          ocrData = ocrRes.data;
          if (!ocrData || ocrRes.status !== 200) {
            throw new Error(ocrData?.detail || "OCR extraction endpoint returned an unsuccessful status.");
          }

          const rawText = (ocrData as any).raw_text || '';
          const countFields = [
            ocrData.student_name,
            ocrData.university_name,
            ocrData.register_number || ocrData.roll_number,
            ocrData.certificate_number,
            ocrData.course || ocrData.department,
            ocrData.cgpa || ocrData.percentage,
            ocrData.date_of_issue,
            ocrData.qr_code_data
          ].filter(Boolean).length;

          computedOcrResult = {
            status: "Successfully registered",
            engine: ocrData.ocr_engine || "EasyOCR + Tesseract Dual Engine",
            pagesProcessed: 1,
            textExtractedSummary: rawText ? `${rawText.length} characters extracted` : "No usable text extracted",
            fieldsDetectedCount: countFields,
            confidencePercent: Math.round((ocrData.ocr_accuracy || 0.85) * 100),
            rawText: rawText,
            extractedInfo: {
              studentName: ocrData.student_name || "Not detected",
              registerNumber: ocrData.register_number || ocrData.roll_number || "Not detected",
              institution: ocrData.university_name || "Not detected",
              semesterCourse: ocrData.course || ocrData.department || "Not detected",
              marksCgpa: ocrData.cgpa != null ? `CGPA: ${ocrData.cgpa}` : ocrData.percentage != null ? `${ocrData.percentage}%` : "Not detected",
              result: ocrData.ocr_accuracy >= 0.5 ? "Pass (Verified)" : "Requires Review",
              issueDate: ocrData.date_of_issue || "Not detected"
            }
          };

          currentStages[1].status = 'completed';
          currentStages[2].status = 'running';
          currentStages[3].status = 'completed';

          const partialArtifact: DocumentArtifact = {
            id: `art-${certId}`,
            title: `Verification Report — ${cert.original_filename}`,
            type: 'verification_report',
            certificateId: certId,
            trustScore: 0,
            verdict: 'genuine',
            candidateName: ocrData.student_name || 'Not detected',
            institution: ocrData.university_name || 'Not detected',
            degreeTitle: ocrData.course || 'Document',
            issueDate: ocrData.date_of_issue || 'Not detected',
            verificationId: `VER-${certId.slice(0, 8)}`,
            qrPayload: ocrData.qr_code_data || 'Not detected',
            blockchainTxHash: 'Pending',
            tamperScore: 0,
            summaryText: rawText ? `Extracted OCR text (${rawText.length} chars). Field extraction complete.` : 'OCR extraction completed.',
            findings: [
              `OCR text extracted (${Math.round((ocrData.ocr_accuracy || 0) * 100)}% accuracy)`,
              `Extracted candidate: ${ocrData.student_name || 'Not detected'}`
            ]
          };

          setActiveArtifact(partialArtifact);
          setConversations(prev => prev.map(c => c.id === targetConvId ? {
            ...c,
            artifact: partialArtifact,
            messages: c.messages.map(m => m.id === assistantMsgId ? { ...m, stages: [...currentStages], ocrResult: computedOcrResult } : m)
          } : c));
        } catch (ocrErr: any) {
          currentStages[1].status = 'failed';
          // Dependent stages remain pending — DO NOT execute or complete dependent verification
          const ocrErrMsg = ocrErr?.response?.data?.detail?.message || ocrErr?.response?.data?.detail || ocrErr?.message || "OCR engine error";
          narrative = `OCR extraction failed for document (ID: ${certId}): ${typeof ocrErrMsg === 'object' ? JSON.stringify(ocrErrMsg) : ocrErrMsg}. Dependent verification checks have been safely halted.`;
          computedOcrResult = null;
          throw new Error(`OCR Failed: ${ocrErrMsg}`);
        }

        // ── Stage 3: Document Type Classification ─────────────────────────
        let docTypeLabel = 'Document';
        try {
          const dtRes = await documentTypeApi.get(certId);
          docTypeLabel = dtRes.data.predicted_type || docTypeLabel;
        } catch { }

        currentStages[2].status = 'completed';
        currentStages[4].status = 'running';

        setConversations(prev => prev.map(c => c.id === targetConvId ? {
          ...c,
          messages: c.messages.map(m => m.id === assistantMsgId ? { ...m, stages: [...currentStages] } : m)
        } : c));

        // ── Stage 4: Verification (QR, Blockchain, Tamper, Duplicate) ─────
        const verifRes = await verificationApi.verifyAll(certId);
        const verif = verifRes.data;

        currentStages[4].status = verif.qr_valid ? 'completed' : (verif.qr_present ? 'warning' : 'completed');
        currentStages[5].status = verif.blockchain_match ? 'completed' : (verif.blockchain_status === 'unavailable' ? 'warning' : 'failed');
        currentStages[6].status = (verif.tampering_score || 0) < 30 ? 'completed' : 'warning';
        currentStages[7].status = verif.is_duplicate ? 'failed' : 'completed';
        currentStages[8].status = 'running';

        setConversations(prev => prev.map(c => c.id === targetConvId ? {
          ...c,
          messages: c.messages.map(m => m.id === assistantMsgId ? { ...m, stages: [...currentStages] } : m)
        } : c));

        // ── Stage 5: Fraud Analysis ───────────────────────────────────────
        try { await fraudApi.analyze(certId); } catch { }

        // ── Stage 6: Trust Score ──────────────────────────────────────────
        const trustRes = await trustScoreApi.compute(certId);
        trustScore = Math.round(trustRes.data.score != null ? trustRes.data.score : 0);
        currentStages[8].status = 'completed';

        // ── Stage 7: Prediction ───────────────────────────────────────────
        const predRes = await predictionApi.predict(certId);
        const predLabel = (predRes.data as any).predicted_class || predRes.data.label || 'genuine';
        verdict = predLabel === 'fake' ? 'fake' : predLabel === 'suspicious' ? 'suspicious' : (predLabel === 'inconclusive' || predLabel.includes('inconclusive')) ? 'inconclusive' : 'genuine';
        confidence = predRes.data.confidence_score || 0.95;

        // Business rule conflict validation (TEST N20)
        if (trustScore === 0 && verdict === 'genuine') {
          verdict = 'undetermined';
          narrative = `Verification Inconsistency Detected: Trust score is 0/100, which conflicts with Genuine classification. System has set status to Undetermined pending administrative review.`;
        } else {
          narrative = predRes.data.explanation || `Analyzed uploaded file ${cert.original_filename} (ID: ${certId}) across OCR, QR, Blockchain, and Forensic Tamper Detection modules. Final Trust Score: ${trustScore}/100.`;
        }

        // ── Stage 8: PDF Report Generation & Pipeline Telemetry Sync ──────
        try { await reportApi.generate(certId); } catch { }
        try { await pipelineApi.runPipeline(certId); } catch { }

        // Construct Dynamic Artifact
        newArtifact = {
          id: `art-${certId}`,
          title: `Verification Report — ${cert.original_filename}`,
          type: 'verification_report',
          certificateId: certId,
          trustScore: trustScore,
          verdict: verdict as any,
          candidateName: ocrData.student_name || 'Not detected',
          institution: ocrData.university_name || 'Not detected',
          degreeTitle: ocrData.course || docTypeLabel || 'Document',
          issueDate: ocrData.date_of_issue || 'Not detected',
          verificationId: `VER-${certId.slice(0, 8)}`,
          qrPayload: verif.qr_decoded_data ? JSON.stringify(verif.qr_decoded_data) : (ocrData.qr_code_data || 'Not detected'),
          blockchainTxHash: verif.blockchain_tx_hash || (verif.blockchain_match ? 'Verified' : 'Not registered'),
          tamperScore: verif.tampering_score != null ? verif.tampering_score / 100 : 0,
          summaryText: narrative,
          findings: predRes.data.reasons && predRes.data.reasons.length > 0 ? predRes.data.reasons : [
            `OCR Text extraction complete (${Math.round((ocrData.ocr_accuracy || 0) * 100)}% confidence)`,
            `QR Code verification: ${verif.qr_present ? (verif.qr_valid ? 'Verified' : 'Invalid QR payload') : 'Not detected'}`,
            `Blockchain verification: ${verif.blockchain_match ? 'Ledger hash matched' : 'No on-chain registration'}`,
            `Tampering analysis score: ${verif.tampering_score != null ? verif.tampering_score : 0}/100`,
            `Duplicate check: ${verif.is_duplicate ? 'Duplicate certificate detected' : 'Unique issuance record'}`
          ]
        };

        // Dynamic Verification Signals
        const rawTextStr = (ocrData.raw_text || '');
        dynamicSignals = [
          { id: 's1', name: 'OCR Engine', category: 'ocr', status: rawTextStr ? 'verified' : 'failed', confidence: Math.round((ocrData.ocr_accuracy || 0) * 100), details: rawTextStr ? `Extracted ${rawTextStr.length} chars` : 'OCR extraction completed' },
          { id: 's2', name: 'QR Verification', category: 'qr', status: verif.qr_valid ? 'verified' : (verif.qr_present ? 'warning' : 'failed'), confidence: verif.qr_valid ? 100 : 0, details: verif.qr_present ? (verif.qr_valid ? 'QR payload cryptographically verified' : 'QR code invalid/unverified') : 'No QR code detected' },
          { id: 's3', name: 'Blockchain Verification', category: 'blockchain', status: verif.blockchain_match ? 'verified' : 'failed', confidence: verif.blockchain_match ? 100 : 0, details: verif.blockchain_match ? 'On-chain hash match confirmed' : 'No matching block on ledger' },
          { id: 's4', name: 'Tamper Detection', category: 'tamper', status: (verif.tampering_score || 0) < 30 ? 'verified' : 'warning', confidence: 100 - (verif.tampering_score || 0), details: `Tampering score: ${verif.tampering_score || 0}/100` },
          { id: 's5', name: 'Duplicate Detection', category: 'duplicate', status: verif.is_duplicate ? 'failed' : 'verified', confidence: 99.0, details: verif.is_duplicate ? `Duplicate of ${verif.duplicate_of_certificate_id || 'stored document'}` : 'Unique active serial record' },
        ];

        // Dynamic Evidence Items
        dynamicEvidence = [
          { id: 1, title: 'Document SHA-256 Hash', sourceType: 'Database Index', snippet: cert.sha256_hash || 'SHA256 Hash generated', targetField: 'Document Identity', confidence: 100 },
          { id: 2, title: 'OCR Candidate Name', sourceType: 'OCR', snippet: ocrData.student_name || 'Not detected in current document', targetField: 'Student Name', confidence: Math.round((ocrData.ocr_accuracy || 0) * 100) },
          { id: 3, title: 'QR Payload Check', sourceType: 'QR Code', snippet: verif.qr_present ? (verif.qr_valid ? 'Verified signature payload' : 'Unverified payload') : 'Not detected in current file', targetField: 'QR Code', confidence: verif.qr_valid ? 100 : 0 },
          { id: 4, title: 'Blockchain Ledger Audit', sourceType: 'Blockchain', snippet: verif.blockchain_match ? 'Verified hash on-chain' : 'Hash not found on ledger', targetField: 'Ledger Registry', confidence: verif.blockchain_match ? 100 : 0 }
        ];

        // Refresh user's certificate ledger records
        try {
          const listRes = await certificateApi.list();
          setCertificateRecords(listRes.data.map(c => ({
            id: c.id,
            name: c.original_filename,
            certificateId: c.id,
            owner: 'User',
            documentType: c.file_type.toUpperCase(),
            institution: 'Uploaded Document',
            trustScore: c.id === certId ? (trustScore || 0) : 0,
            verdict: (c.id === certId ? ((['genuine', 'suspicious', 'fake', 'inconclusive', 'analyzing'].includes(verdict || '') ? ((verdict || 'suspicious') as CertificateStatus) : 'suspicious')) : 'genuine'),
            lastVerified: new Date(c.uploaded_at).toLocaleDateString(),
            fileSize: `${(c.file_size_bytes / 1024 / 1024).toFixed(1)} MB`
          })));
        } catch { }

        executionSuccess = true;
      } catch (err: any) {
        console.error("Pipeline execution error:", err);
        // Error state handled, stages preserved as actual failure state
      }
    }

    const finalAssistantMsg: AIMessage = {
      id: assistantMsgId,
      sender: 'assistant',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      mode,
      isStreaming: false,
      verdict: verdict as any,
      trustScore,
      confidence,
      summaryNarrative: narrative,
      stages: currentStages,
      signals: dynamicSignals,
      evidenceList: dynamicEvidence,
      ocrResult: computedOcrResult,
      artifactId: newArtifact?.id,
      contextualActions: executionSuccess ? [
        { id: 'a1', label: 'View Evidence', action: 'view_evidence', primary: true },
        { id: 'a2', label: 'Generate Report', action: 'generate_report', primary: true },
        { id: 'a3', label: 'Inspect OCR', action: 'inspect_ocr' },
      ] : [
        { id: 'retry', label: 'Retry Verification', action: 'retry_verification', primary: true }
      ]
    };

    setConversations(prev => prev.map(c => {
      if (c.id === targetConvId) {
        return {
          ...c,
          verdict: verdict as any,
          trustScore,
          artifact: file ? (newArtifact || undefined) : (newArtifact || c.artifact),
          messages: c.messages.map(m => m.id === assistantMsgId ? finalAssistantMsg : m)
        };
      }
      return c;
    }));

    if (newArtifact) {
      setActiveArtifact(newArtifact);
      setActiveEvidenceId(1);
      if (newArtifact.certificateId) {
        setCurrentCertificateId(newArtifact.certificateId);
      }
    }
  }, [activeConversationId, conversations, mode, setCurrentCertificateId]);

  const executeAction = useCallback((actionId: string, param?: string) => {
    if (actionId === 'generate_report' || actionId === 'view_report') {
      if (activeConversation?.artifact) {
        setActiveArtifact(activeConversation.artifact);
      }
    } else if (actionId === 'view_evidence' || actionId === 'inspect_evidence') {
      setActiveView('evidence');
      setActiveEvidenceId(1);
    } else if (actionId === 'inspect_ocr') {
      if (activeConversation?.artifact) {
        setActiveArtifact({
          ...activeConversation.artifact,
          type: 'ocr_json',
          title: `OCR Data Transcript — ${activeConversation.artifact.certificateId}`
        });
      }
    } else if (actionId === 'download_pdf') {
      const art = activeConversation?.artifact || activeArtifact;
      if (!art) return;
      const element = document.createElement("a");
      const file = new Blob([
        `==================================================\nCERTIVERIFY AI OFFICIAL VERIFICATION DOSSIER\n==================================================\nDocument: ${art.title}\nCertificate ID: ${art.certificateId}\nVerification ID: ${art.verificationId}\nTrust Score: ${art.trustScore}/100\nVerdict: ${art.verdict.toUpperCase()}\n\nCANDIDATE DETAILS:\nCandidate Name: ${art.candidateName}\nInstitution: ${art.institution}\nDegree/Title: ${art.degreeTitle}\nIssue Date: ${art.issueDate}\n\nTECHNICAL VERIFICATION EVIDENCE:\n- QR Payload: ${art.qrPayload || 'N/A'}\n- Blockchain TX Hash: ${art.blockchainTxHash || 'N/A'}\n- Tamper Score: ${art.tamperScore}\n\nSUMMARY NARRATIVE:\n${art.summaryText}\n\nFINDINGS:\n${art.findings.map((f: string) => ` - ${f}`).join('\n')}\n\nSigned by CertiVerify AI Autonomous Verification Engine.\n`
      ], { type: 'text/plain' });
      element.href = URL.createObjectURL(file);
      element.download = `CertiVerify_Report_${art.certificateId}.txt`;
      document.body.appendChild(element);
      element.click();
      document.body.removeChild(element);
    } else if (actionId === 'investigate') {
      setActiveView('investigation');
      sendMessage('Investigate this certificate for all suspicious signals and evidence.');
    } else if (actionId === 'compare') {
      setActiveView('compare');
      sendMessage('Compare this certificate with standard institutional baseline.');
    } else if (actionId === 'cockpit') {
      setActiveView('cockpit');
    } else if (actionId === 'pipeline') {
      setActiveView('pipeline');
    } else if (actionId === 'review') {
      setActiveView('review');
    }
  }, [activeConversation, activeArtifact, sendMessage]);

  return (
    <AIWorkspaceContext.Provider
      value={{
        currentCertificateId,
        setCurrentCertificateId,
        conversations,
        activeConversationId,
        activeConversation,
        activeView,
        setActiveView,
        mode,
        setMode,
        searchQuery,
        setSearchQuery,
        activeArtifact,
        setActiveArtifact,
        activeEvidenceId,
        setActiveEvidenceId,
        isSettingsOpen,
        setIsSettingsOpen,
        isNotificationsOpen,
        setIsNotificationsOpen,
        notifications,
        markNotificationAsRead,
        clearAllNotifications,
        certificateRecords,
        isVoiceActive,
        toggleVoice,
        createNewConversation,
        selectConversation,
        sendMessage,
        executeAction
      }}
    >
      {children}
    </AIWorkspaceContext.Provider>
  );
};

export const useAIWorkspace = () => {
  const context = useContext(AIWorkspaceContext);
  if (!context) {
    throw new Error('useAIWorkspace must be used within an AIWorkspaceProvider');
  }
  return context;
};
