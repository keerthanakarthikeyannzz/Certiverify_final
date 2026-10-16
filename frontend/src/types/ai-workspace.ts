export type AIMode = 'verify' | 'analyze' | 'investigate' | 'compare' | 'report';

export type CertificateStatus = 'genuine' | 'suspicious' | 'fake' | 'inconclusive' | 'analyzing';

export type ActiveView =
  | 'chat'
  | 'dashboard'
  | 'certificates'
  | 'upload'
  | 'pipeline'
  | 'cockpit'
  | 'detail'
  | 'evidence'
  | 'investigation'
  | 'compare'
  | 'search'
  | 'reports'
  | 'history'
  | 'review'
  | 'settings';

export interface VerificationSignal {
  id: string;
  name: string;
  category: 'ocr' | 'qr' | 'blockchain' | 'tamper' | 'duplicate' | 'metadata' | 'structure' | 'field';
  status: 'verified' | 'warning' | 'failed' | 'pending';
  confidence: number;
  details: string;
}

export interface EvidenceItem {
  id: number;
  title: string;
  sourceType: 'OCR' | 'QR Code' | 'Blockchain' | 'Document Metadata' | 'Image Analysis' | 'Certificate Fields' | 'Database Index';
  snippet: string;
  targetField?: string;
  confidence: number;
  coordinates?: { x: number; y: number; width: number; height: number };
}

export interface AnalysisStage {
  id: string;
  label: string;
  status: 'completed' | 'running' | 'pending' | 'warning' | 'failed';
  timestamp?: string;
  metrics?: {
    engine?: string;
    confidence?: number;
    processingTimeMs?: number;
    detectedCount?: number;
  };
}

export interface DocumentArtifact {
  id: string;
  title: string;
  type: 'verification_report' | 'ocr_json' | 'tamper_map' | 'blockchain_receipt';
  certificateId: string;
  trustScore: number;
  verdict: CertificateStatus;
  candidateName: string;
  institution: string;
  degreeTitle: string;
  issueDate: string;
  verificationId: string;
  qrPayload?: string;
  blockchainTxHash?: string;
  tamperScore?: number;
  summaryText: string;
  findings: string[];
}

export interface AIMessage {
  id: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  text?: string;
  mode?: AIMode;
  attachedFile?: {
    name: string;
    size: string;
    type: string;
    url?: string;
  };
  isStreaming?: boolean;
  verdict?: CertificateStatus;
  trustScore?: number;
  confidence?: number;
  summaryNarrative?: string;
  positiveSignals?: string[];
  potentialLimitations?: string[];
  signals?: VerificationSignal[];
  evidenceList?: EvidenceItem[];
  stages?: AnalysisStage[];
  ocrResult?: {
    status: string;
    engine: string;
    pagesProcessed: number;
    textExtractedSummary: string;
    fieldsDetectedCount: number;
    confidencePercent: number;
    rawText?: string;
    extractedInfo: {
      studentName?: string;
      registerNumber?: string;
      institution?: string;
      semesterCourse?: string;
      marksCgpa?: string;
      result?: string;
      issueDate?: string;
    };
  };
  artifactId?: string;
  contextualActions?: Array<{
    id: string;
    label: string;
    action: string;
    primary?: boolean;
  }>;
}

export interface AIConversation {
  id: string;
  title: string;
  category: 'Today' | 'Yesterday' | 'This Week' | 'Older';
  updatedAt: string;
  mode: AIMode;
  certificateName?: string;
  certificateId?: string;
  verdict?: CertificateStatus;
  trustScore?: number;
  previewUrl?: string;
  messages: AIMessage[];
  artifact?: DocumentArtifact;
}

export interface AISearchResult {
  id: string;
  certificateName: string;
  certificateId: string;
  verdict: CertificateStatus;
  trustScore: number;
  date: string;
  snippet: string;
  matchedRule: string;
  conversationId: string;
}

export interface AINotification {
  id: string;
  title: string;
  message: string;
  timestamp: string;
  type: 'success' | 'warning' | 'danger' | 'info';
  read: boolean;
}

export interface CertificateRecord {
  id: string;
  name: string;
  certificateId: string;
  owner: string;
  documentType: string;
  institution: string;
  trustScore: number;
  verdict: CertificateStatus;
  lastVerified: string;
  fileSize: string;
}
