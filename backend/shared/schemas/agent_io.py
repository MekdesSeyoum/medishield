from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from shared.enums import DocumentType


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class ClassifierInput(BaseModel):
    case_id: UUID
    file_key: str
    file_name: str
    mime_type: str
    raw_bytes_b64: str


class ClassifierOutput(BaseModel):
    document_type: DocumentType
    confidence: float = Field(ge=0.0, le=1.0)
    page_count: int = Field(ge=1)
    is_handwritten: bool
    routing_hints: list[str]


# ---------------------------------------------------------------------------
# KYC
# ---------------------------------------------------------------------------


class KYCInput(BaseModel):
    case_id: UUID
    doc_type: DocumentType
    extracted_text: str
    image_bytes: bytes | None = None


class KYCOutput(BaseModel):
    kyc_passed: bool
    flags: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


class ClaimsInput(BaseModel):
    case_id: UUID
    extracted_text: str
    raw_fields: dict
    raw_bytes_b64: str = ""
    mime_type: str = ""


class ClaimsOutput(BaseModel):
    extracted_fields: dict
    schema_valid: bool
    validation_errors: list[str]


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


class PolicyInput(BaseModel):
    case_id: UUID
    cpt_codes: list[str]


class PolicyOutput(BaseModel):
    covered: bool
    coverage_percentage: float = Field(ge=0.0, le=1.0)
    policy_clause: str
    exclusions: list[str]


# ---------------------------------------------------------------------------
# Fraud Detection
# ---------------------------------------------------------------------------


class FraudInput(BaseModel):
    case_id: UUID
    extracted_fields: dict
    patient_id: str
    provider_npi: str
    claim_amount: float


class FraudOutput(BaseModel):
    fraud_score: float = Field(ge=0.0, le=1.0)
    anomalies: list[str]
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class OrchestratorOutput(BaseModel):
    decision: Literal["APPROVE", "REJECT", "ESCALATE"]
    reasons: list[str]
    fraud_score: float = Field(ge=0.0, le=1.0)
    coverage_percentage: float = Field(ge=0.0, le=1.0)
