from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from shared.enums import CaseStatus
from shared.schemas.agent_io import (
    ClassifierOutput,
    ClaimsOutput,
    FraudOutput,
    KYCOutput,
    OrchestratorOutput,
    PolicyOutput,
)


class AuditEntry(BaseModel):
    timestamp: datetime
    actor: str
    action: Literal["PIPELINE_DECISION", "MANUAL_OVERRIDE"]
    decision: str
    reason: str


class CaseRecord(BaseModel):
    """Full case record as stored in Redis and returned by detail/list endpoints."""

    case_id: UUID
    status: CaseStatus
    file_name: str
    mime_type: str
    file_key: str
    created_at: datetime
    updated_at: datetime
    orchestrator_output: OrchestratorOutput | None = None
    classifier_output: ClassifierOutput | None = None
    kyc_output: KYCOutput | None = None
    claims_output: ClaimsOutput | None = None
    policy_output: PolicyOutput | None = None
    fraud_output: FraudOutput | None = None
    audit_log: list[AuditEntry] = Field(default_factory=list)


class CaseUploadResponse(BaseModel):
    """Response body for POST /cases/upload."""

    case_id: UUID
    status: CaseStatus
    file_name: str
    mime_type: str
    created_at: datetime


class PaginatedCasesResponse(BaseModel):
    """Response body for GET /cases/."""

    items: list[CaseRecord]
    total: int = Field(ge=0, description="Total number of cases across all pages")
    page: int = Field(ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(ge=1, description="Number of items per page")


class DecisionOverrideRequest(BaseModel):
    """Request body for PATCH /cases/{case_id}/decision."""

    decision: Literal["APPROVE", "REJECT"]
    reason: str = ""
