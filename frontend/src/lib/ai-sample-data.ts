import { AIConversation, DocumentArtifact, AISearchResult } from '../types/ai-workspace';

export const INITIAL_ARTIFACTS: Record<string, DocumentArtifact> = {
  'art-001': {
    id: 'art-001',
    title: 'Verification Dossier — Keerthana K (B.Tech Degree)',
    type: 'verification_report',
    certificateId: 'CERT-2026-88912',
    trustScore: 96,
    verdict: 'genuine',
    candidateName: 'Keerthana K',
    institution: 'Anna University / Department of Computer Science & Engineering',
    degreeTitle: 'Bachelor of Technology in Computer Science & Engineering',
    issueDate: 'May 18, 2025',
    verificationId: 'VER-2026-0928-889',
    qrPayload: 'https://verify.annauniv.edu/cert/CERT-2026-88912?hash=0x8f2a9...c4b1',
    blockchainTxHash: '0x3f71c42b1a89e01c9872e4b891276a0f12c98a76e5d4c3b2a1f0987654321abc',
    tamperScore: 0.02,
    summaryText: 'All 8 forensic verification layers confirmed document authenticity. Cryptographic hash matched the immutable ledger state.',
    findings: [
      'High confidence OCR text extraction (98.2% accuracy)',
      'QR Code payload signature verified against official institution public keys',
      'Blockchain block #18,429,102 confirmed immutable issuance timestamp',
      'Error Level Analysis (ELA) detected zero pixel manipulation or font tampering',
      'Global database index confirmed single valid issuance instance (no duplicate reuse)'
    ]
  },
  'art-002': {
    id: 'art-002',
    title: 'Forensic Audit Report — HSC Higher Secondary Marksheet',
    type: 'verification_report',
    certificateId: 'HSC-2024-55410',
    trustScore: 62,
    verdict: 'suspicious',
    candidateName: 'Rohan Sharma',
    institution: 'State Board of Higher Secondary Education',
    degreeTitle: 'Higher Secondary School Certificate (Class XII)',
    issueDate: 'June 12, 2024',
    verificationId: 'VER-2026-0928-554',
    qrPayload: 'https://hscboard.gov.in/verify?roll=884920&key=INVALID_SIG',
    blockchainTxHash: 'Pending Verification / Ledger Hash Mismatch',
    tamperScore: 0.38,
    summaryText: 'CertiVerify flagged 2 forensic anomalies requiring manual institutional audit.',
    findings: [
      'Font metrics anomaly detected on the Mathematics subject score line',
      'QR Code decoded successfully but signature payload failed public key validation',
      'Document structure pattern matches standard template but metadata date was modified post-export'
    ]
  },
  'art-003': {
    id: 'art-003',
    title: 'Fraud Alert Dossier — Certificate #CERT-2026-001',
    type: 'verification_report',
    certificateId: 'CERT-2026-001',
    trustScore: 18,
    verdict: 'fake',
    candidateName: 'Alex Mercer',
    institution: 'Imperial Institute of Technology (Unaccredited / Unknown)',
    degreeTitle: 'Master of Science in Cybersecurity',
    issueDate: 'January 10, 2026',
    verificationId: 'VER-2026-0928-001',
    qrPayload: 'http://malicious-redirect-domain.xyz/verify/fake',
    blockchainTxHash: 'Not Found on Public or Private Ledger',
    tamperScore: 0.89,
    summaryText: 'Critical forgery markers detected across physical seal, QR redirection, and font alignment.',
    findings: [
      'QR Code points to an unverified third-party phishing domain rather than official university server',
      'Digital seal shows heavy pixel interpolation and compression artifacts from copy-paste operation',
      'Certificate serial number #CERT-2026-001 failed institutional checksum algorithm',
      'Zero record found on decentralized verification ledger'
    ]
  }
};

export const INITIAL_CONVERSATIONS: AIConversation[] = [
  {
    id: 'conv-1',
    title: 'Verify B.Tech Certificate',
    category: 'Today',
    updatedAt: '10:15 AM',
    mode: 'verify',
    certificateName: 'B.Tech_Degree_Keerthana.pdf',
    certificateId: 'CERT-2026-88912',
    verdict: 'genuine',
    trustScore: 96,
    artifact: INITIAL_ARTIFACTS['art-001'],
    messages: [
      {
        id: 'msg-1-1',
        sender: 'user',
        timestamp: '10:14 AM',
        text: 'Verify this certificate for authenticity.',
        attachedFile: {
          name: 'B.Tech_Degree_Keerthana.pdf',
          size: '2.4 MB',
          type: 'application/pdf'
        }
      },
      {
        id: 'msg-1-2',
        sender: 'assistant',
        timestamp: '10:15 AM',
        mode: 'verify',
        verdict: 'genuine',
        trustScore: 96,
        confidence: 96.4,
        summaryNarrative: "I've analyzed the uploaded certificate using multiple independent verification layers. Several strong signals confirm the authenticity of this document [1]. The embedded QR payload [2] matches the cryptographically signed ledger state on the blockchain [3].",
        positiveSignals: [
          'QR payload cryptographically verified with official university public key',
          'Immutable ledger hash matched block #18,429,102',
          'OCR text structure matches official Anna University diploma template',
          'Zero visual tampering or font manipulation detected'
        ],
        potentialLimitations: [
          'Physical paper watermarks cannot be scanned via standard PDF upload'
        ],
        stages: [
          { id: '1', label: 'Document received', status: 'completed' },
          { id: '2', label: 'OCR extraction completed', status: 'completed' },
          { id: '3', label: 'Document type identified', status: 'completed' },
          { id: '4', label: 'Certificate fields extracted', status: 'completed' },
          { id: '5', label: 'QR code detected & verified', status: 'completed' },
          { id: '6', label: 'Document structure analyzed', status: 'completed' },
          { id: '7', label: 'Tamper analysis', status: 'completed' },
          { id: '8', label: 'Blockchain verification', status: 'completed' },
          { id: '9', label: 'Duplicate detection', status: 'completed' },
          { id: '10', label: 'Trust score calculation', status: 'completed' }
        ],
        signals: [
          { id: 's1', name: 'OCR Engine', category: 'ocr', status: 'verified', confidence: 98.2, details: 'Text fields matched database schema with 98.2% optical confidence' },
          { id: 's2', name: 'QR Verification', category: 'qr', status: 'verified', confidence: 99.9, details: 'Decoded signed payload verified via RSA-2048 university key' },
          { id: 's3', name: 'Blockchain Verification', category: 'blockchain', status: 'verified', confidence: 100, details: 'Merkle root confirmed in transaction 0x3f71c...321abc' },
          { id: 's4', name: 'Tamper Detection', category: 'tamper', status: 'verified', confidence: 97.5, details: 'Error Level Analysis (ELA) clean; no copy-paste noise' },
          { id: 's5', name: 'Duplicate Detection', category: 'duplicate', status: 'verified', confidence: 99.0, details: 'Unique certificate ID; single active record in system' },
          { id: 's6', name: 'Metadata Analysis', category: 'metadata', status: 'verified', confidence: 96.0, details: 'Creation software: Adobe Acrobat Pro (Official University Press)' },
          { id: 's7', name: 'Document Structure', category: 'structure', status: 'verified', confidence: 98.0, details: 'Layout geometry matches Anna University CSE B.Tech 2025 standard' },
          { id: 's8', name: 'Field Validation', category: 'field', status: 'verified', confidence: 96.7, details: 'Roll number and candidate name verified against university registry' }
        ],
        evidenceList: [
          { id: 1, title: 'Extracted Certificate ID', sourceType: 'OCR', snippet: 'CERT-2026-88912 extracted cleanly with 99.4% confidence', targetField: 'Certificate ID', confidence: 99.4 },
          { id: 2, title: 'QR Code Payload Verification', sourceType: 'QR Code', snippet: 'https://verify.annauniv.edu/cert/CERT-2026-88912 signed by RSA Key ID 0x48A1', targetField: 'QR Payload', confidence: 99.9 },
          { id: 3, title: 'Decentralized Ledger Proof', sourceType: 'Blockchain', snippet: 'Block #18429102 | Tx: 0x3f71c42b...321abc | Merkle Root Validated', targetField: 'Blockchain Tx', confidence: 100 },
          { id: 4, title: 'Error Level Analysis (ELA)', sourceType: 'Image Analysis', snippet: 'Uniform error compression distribution across seals and fonts', targetField: 'Seal & Signature', confidence: 97.5 }
        ],
        artifactId: 'art-001',
        contextualActions: [
          { id: 'a1', label: 'View Evidence', action: 'view_evidence', primary: true },
          { id: 'a2', label: 'Generate Report', action: 'generate_report', primary: true },
          { id: 'a3', label: 'Inspect OCR', action: 'inspect_ocr' },
          { id: 'a4', label: 'Download PDF', action: 'download_pdf' }
        ]
      }
    ]
  },
  {
    id: 'conv-2',
    title: 'Analyze HSC Marksheet',
    category: 'Today',
    updatedAt: '9:45 AM',
    mode: 'analyze',
    certificateName: 'HSC_Marksheet_Rohan.pdf',
    certificateId: 'HSC-2024-55410',
    verdict: 'suspicious',
    trustScore: 62,
    artifact: INITIAL_ARTIFACTS['art-002'],
    messages: [
      {
        id: 'msg-2-1',
        sender: 'user',
        timestamp: '9:44 AM',
        text: 'Analyze this HSC marksheet for signs of tampering.',
        attachedFile: {
          name: 'HSC_Marksheet_Rohan.pdf',
          size: '1.8 MB',
          type: 'application/pdf'
        }
      },
      {
        id: 'msg-2-2',
        sender: 'assistant',
        timestamp: '9:45 AM',
        mode: 'analyze',
        verdict: 'suspicious',
        trustScore: 62,
        confidence: 62.0,
        summaryNarrative: "CertiVerify found several signals that require review [1]. While the document general structure matches standard Board templates, font alignment on the marks table shows inconsistencies [2] and the QR signature failed cryptographic verification [3].",
        positiveSignals: [
          'Document structure matches official State Board Class XII layout',
          'Candidate name and Roll number exist in state education registry'
        ],
        potentialLimitations: [
          '⚠ Font family and weight on Mathematics score line differs from adjacent lines',
          '⚠ QR code payload signature failed public key verification',
          '⚠ Metadata creation date does not match the official issue date'
        ],
        stages: [
          { id: '1', label: 'Document received', status: 'completed' },
          { id: '2', label: 'OCR extraction completed', status: 'completed' },
          { id: '3', label: 'Document type identified', status: 'completed' },
          { id: '4', label: 'Certificate fields extracted', status: 'completed' },
          { id: '5', label: 'QR code detected', status: 'completed' },
          { id: '6', label: 'QR verification completed', status: 'warning' },
          { id: '7', label: 'Document structure analyzed', status: 'completed' },
          { id: '8', label: 'Tamper analysis', status: 'warning' },
          { id: '9', label: 'Blockchain verification', status: 'pending' },
          { id: '10', label: 'Trust score calculation', status: 'completed' }
        ],
        signals: [
          { id: 's1', name: 'OCR Engine', category: 'ocr', status: 'verified', confidence: 94.0, details: 'Fields extracted successfully' },
          { id: 's2', name: 'QR Verification', category: 'qr', status: 'failed', confidence: 20.0, details: 'Payload signature checksum invalid' },
          { id: 's3', name: 'Tamper Detection', category: 'tamper', status: 'warning', confidence: 45.0, details: 'High ELA noise detected around score values' },
          { id: 's4', name: 'Metadata Analysis', category: 'metadata', status: 'warning', confidence: 50.0, details: 'PDF created using Photoshop CS6 3 days ago' }
        ],
        evidenceList: [
          { id: 1, title: 'Font Metrics Discrepancy', sourceType: 'OCR', snippet: 'Mathematics mark "98" font bounding box offset by 1.4pt vertically', targetField: 'Mathematics Score', confidence: 91.0 },
          { id: 2, title: 'Failed QR Cryptographic Checksum', sourceType: 'QR Code', snippet: 'Decoded URL: https://hscboard.gov.in/verify?key=INVALID_SIG', targetField: 'QR Payload', confidence: 15.0 },
          { id: 3, title: 'Photoshop Creation Metadata', sourceType: 'Document Metadata', snippet: 'Creator Tool: Adobe Photoshop CS6 (Windows)', targetField: 'PDF Metadata', confidence: 99.0 }
        ],
        artifactId: 'art-002',
        contextualActions: [
          { id: 'a1', label: 'Investigate Anomalies', action: 'investigate', primary: true },
          { id: 'a2', label: 'View Evidence', action: 'view_evidence' },
          { id: 'a3', label: 'Generate Audit Report', action: 'generate_report' }
        ]
      }
    ]
  },
  {
    id: 'conv-3',
    title: 'Check Certificate #CERT-2026-001',
    category: 'Yesterday',
    updatedAt: '4:20 PM',
    mode: 'verify',
    certificateName: 'Unverified_Master_Diploma.pdf',
    certificateId: 'CERT-2026-001',
    verdict: 'fake',
    trustScore: 18,
    artifact: INITIAL_ARTIFACTS['art-003'],
    messages: [
      {
        id: 'msg-3-1',
        sender: 'user',
        timestamp: '4:19 PM',
        text: 'Check if this certificate #CERT-2026-001 is genuine or fake.',
        attachedFile: {
          name: 'Unverified_Master_Diploma.pdf',
          size: '3.1 MB',
          type: 'application/pdf'
        }
      },
      {
        id: 'msg-3-2',
        sender: 'assistant',
        timestamp: '4:20 PM',
        mode: 'verify',
        verdict: 'fake',
        trustScore: 18,
        confidence: 94.0,
        summaryNarrative: "CertiVerify found multiple critical inconsistencies that significantly reduce confidence in the document's authenticity [1]. The document displays markers of digital forgery, including an altered institution seal [2], suspicious QR redirection [3], and absence from verified registries.",
        positiveSignals: [],
        potentialLimitations: [
          'CRITICAL: QR Code redirects to an unverified external phishing site',
          'CRITICAL: Official seal has high compression artifacts matching image insertion',
          'CRITICAL: No matching record on public or private verification ledgers'
        ],
        stages: [
          { id: '1', label: 'Document received', status: 'completed' },
          { id: '2', label: 'OCR extraction completed', status: 'completed' },
          { id: '3', label: 'Document type identified', status: 'completed' },
          { id: '4', label: 'Certificate fields extracted', status: 'completed' },
          { id: '5', label: 'QR code detected', status: 'completed' },
          { id: '6', label: 'QR verification completed', status: 'failed' },
          { id: '7', label: 'Document structure analyzed', status: 'failed' },
          { id: '8', label: 'Tamper analysis', status: 'failed' },
          { id: '9', label: 'Blockchain verification', status: 'failed' },
          { id: '10', label: 'Trust score calculation', status: 'completed' }
        ],
        signals: [
          { id: 's1', name: 'QR Redirection', category: 'qr', status: 'failed', confidence: 0, details: 'Target host: malicious-redirect-domain.xyz' },
          { id: 's2', name: 'Seal Tamper', category: 'tamper', status: 'failed', confidence: 10, details: 'Heavy ELA contrast mismatch on institutional emblem' },
          { id: 's3', name: 'Ledger Record', category: 'blockchain', status: 'failed', confidence: 0, details: 'Zero hash match found on chain' }
        ],
        evidenceList: [
          { id: 1, title: 'Malicious QR Redirection', sourceType: 'QR Code', snippet: 'Decoded URL: http://malicious-redirect-domain.xyz/verify/fake', targetField: 'QR URL', confidence: 100 },
          { id: 2, title: 'Copied Digital Emblem', sourceType: 'Image Analysis', snippet: 'Emblem image bounds contain JPEG block compression noise inconsistent with PDF vector elements', targetField: 'Emblem Seal', confidence: 96 }
        ],
        artifactId: 'art-003',
        contextualActions: [
          { id: 'a1', label: 'View Fraud Evidence', action: 'view_evidence', primary: true },
          { id: 'a2', label: 'Generate Fraud Report', action: 'generate_report' }
        ]
      }
    ]
  },
  {
    id: 'conv-4',
    title: 'Compare two certificates',
    category: 'This Week',
    updatedAt: 'Sep 25, 2:10 PM',
    mode: 'compare',
    certificateName: 'B.Tech_v1_vs_v2.pdf',
    certificateId: 'COMPARE-PAIR-0925',
    verdict: 'genuine',
    trustScore: 94,
    messages: [
      {
        id: 'msg-4-1',
        sender: 'user',
        timestamp: '2:10 PM',
        text: 'Compare these two certificates to see if the reissued copy matches original university records.',
        attachedFile: {
          name: 'B.Tech_v1_vs_v2.pdf',
          size: '4.2 MB',
          type: 'application/pdf'
        }
      },
      {
        id: 'msg-4-2',
        sender: 'assistant',
        timestamp: '2:10 PM',
        mode: 'compare',
        verdict: 'genuine',
        trustScore: 94,
        confidence: 94.0,
        summaryNarrative: 'CertiVerify compared Document A (Original 2021 Issue) with Document B (Reissued 2025 Copy). Both certificates share identical student credentials, roll numbers, and cryptographically verified blockchain hashes.',
        positiveSignals: [
          'Candidate credentials match 100% across both documents',
          'Blockchain transaction reissuance token linked to root genesis block',
          'Digital signatures from Registrar office verified'
        ],
        potentialLimitations: [
          'Reissued copy contains updated security QR code format (v2 specification)'
        ],
        contextualActions: [
          { id: 'a1', label: 'View Comparison Matrix', action: 'view_evidence', primary: true },
          { id: 'a2', label: 'Export Comparison Report', action: 'generate_report' }
        ]
      }
    ]
  },
  {
    id: 'conv-5',
    title: 'Why is this document suspicious?',
    category: 'This Week',
    updatedAt: 'Sep 24, 11:30 AM',
    mode: 'investigate',
    certificateName: 'HSC_Marksheet_Rohan.pdf',
    certificateId: 'HSC-2024-55410',
    verdict: 'suspicious',
    trustScore: 62,
    messages: [
      {
        id: 'msg-5-1',
        sender: 'user',
        timestamp: '11:29 AM',
        text: 'Why was this document classified as suspicious?',
        attachedFile: {
          name: 'HSC_Marksheet_Rohan.pdf',
          size: '1.8 MB',
          type: 'application/pdf'
        }
      },
      {
        id: 'msg-5-2',
        sender: 'assistant',
        timestamp: '11:30 AM',
        mode: 'investigate',
        verdict: 'suspicious',
        trustScore: 62,
        confidence: 62.0,
        summaryNarrative: "The document's Trust Score of 62/100 was reduced due to two major risk factors: 1) The embedded QR payload signature is cryptographically invalid when evaluated against the Board's public key, and 2) Optical analysis detected localized font smoothing around the Mathematics mark field [1].",
        positiveSignals: [
          'Roll number #884920 exists in candidate database'
        ],
        potentialLimitations: [
          'QR payload cryptographic signature mismatch (-25 pts)',
          'Local font ELA anomaly on score field (-13 pts)'
        ],
        evidenceList: [
          { id: 1, title: 'Mathematics Field ELA Map', sourceType: 'Image Analysis', snippet: 'Edge luminance frequency anomaly on numbers "98"', targetField: 'Mathematics Score', confidence: 91.0 }
        ],
        contextualActions: [
          { id: 'a1', label: 'Inspect OCR Transcript', action: 'inspect_ocr', primary: true },
          { id: 'a2', label: 'Generate Full Dossier', action: 'generate_report' }
        ]
      }
    ]
  }
];

export const INITIAL_SEARCH_RESULTS: AISearchResult[] = [
  {
    id: 'res-1',
    certificateName: 'HSC_Marksheet_Rohan.pdf',
    certificateId: 'HSC-2024-55410',
    verdict: 'suspicious',
    trustScore: 62,
    date: 'Today, 9:45 AM',
    snippet: 'Font metrics anomaly on Mathematics line + QR payload signature invalid.',
    matchedRule: 'Trust Score < 70',
    conversationId: 'conv-2'
  },
  {
    id: 'res-2',
    certificateName: 'Unverified_Master_Diploma.pdf',
    certificateId: 'CERT-2026-001',
    verdict: 'fake',
    trustScore: 18,
    date: 'Yesterday, 4:20 PM',
    snippet: 'Critical forgery markers detected. Malicious QR redirection host.',
    matchedRule: 'Trust Score < 70',
    conversationId: 'conv-3'
  }
];
