export type CaseStatus =
  | "PENDING"
  | "PROCESSING"
  | "APPROVED"
  | "DENIED"
  | "ESCALATED"
  | "PENDING_INFO";

export type DocumentType =
  | "CLAIM_FORM"
  | "ID_DOCUMENT"
  | "MEMBERSHIP_CARD"
  | "MEDICAL_REPORT"
  | "PRESCRIPTION"
  | "POLICY_DOC"
  | "UNKNOWN";

export interface ClassifierOutput {
  document_type: DocumentType;
  confidence: number;
  page_count: number;
  is_handwritten: boolean;
  routing_hints: string[];
}

export interface KYCOutput {
  kyc_passed: boolean;
  flags: string[];
  confidence: number;
}

export interface ClaimsOutput {
  extracted_fields: Record<string, unknown>;
  schema_valid: boolean;
  validation_errors: string[];
}

export interface PolicyOutput {
  covered: boolean;
  coverage_percentage: number;
  policy_clause: string;
  exclusions: string[];
}

export interface FraudOutput {
  fraud_score: number;
  anomalies: string[];
  risk_level: "LOW" | "MEDIUM" | "HIGH";
}

export interface OrchestratorOutput {
  decision: "APPROVE" | "REJECT" | "ESCALATE";
  reasons: string[];
  fraud_score: number;
  coverage_percentage: number;
}

export interface AuditEntry {
  timestamp: string;
  actor: string;
  action: "PIPELINE_DECISION" | "MANUAL_OVERRIDE";
  decision: string;
  reason: string;
}

export interface CaseRecord {
  case_id: string;
  status: CaseStatus;
  file_name: string;
  mime_type: string;
  file_key: string;
  created_at: string;
  updated_at: string;
  orchestrator_output: OrchestratorOutput | null;
  classifier_output: ClassifierOutput | null;
  kyc_output: KYCOutput | null;
  claims_output: ClaimsOutput | null;
  policy_output: PolicyOutput | null;
  fraud_output: FraudOutput | null;
  audit_log: AuditEntry[];
}

export interface PaginatedCasesResponse {
  items: CaseRecord[];
  total: number;
  page: number;
  page_size: number;
}
