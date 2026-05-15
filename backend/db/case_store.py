from datetime import datetime, timezone
from uuid import UUID

import redis

from core.config import get_settings
from shared.enums import CaseStatus
from shared.schemas.agent_io import (
    ClassifierOutput,
    ClaimsOutput,
    FraudOutput,
    KYCOutput,
    OrchestratorOutput,
    PolicyOutput,
)
from shared.schemas.cases import AuditEntry, CaseRecord

_CASE_KEY = "case:{}"
_CASES_ZSET = "cases"


class CaseStore:
    """Redis-backed store for case metadata."""

    def __init__(self, client: redis.Redis | None = None) -> None:
        if client is None:
            s = get_settings()
            self._r: redis.Redis = redis.Redis.from_url(
                s.redis_url, decode_responses=True
            )
        else:
            self._r = client

    def create(
        self,
        case_id: UUID,
        file_name: str,
        mime_type: str,
        file_key: str,
    ) -> CaseRecord:
        now = datetime.now(tz=timezone.utc)
        record = CaseRecord(
            case_id=case_id,
            status=CaseStatus.PENDING,
            file_name=file_name,
            mime_type=mime_type,
            file_key=file_key,
            created_at=now,
            updated_at=now,
        )
        self._r.set(_CASE_KEY.format(case_id), record.model_dump_json())
        self._r.zadd(_CASES_ZSET, {str(case_id): now.timestamp()})
        return record

    def get(self, case_id: UUID) -> CaseRecord | None:
        raw = self._r.get(_CASE_KEY.format(case_id))
        if raw is None:
            return None
        return CaseRecord.model_validate_json(raw)

    def update_status(self, case_id: UUID, status: CaseStatus) -> CaseRecord | None:
        record = self.get(case_id)
        if record is None:
            return None
        record.status = status
        record.updated_at = datetime.now(tz=timezone.utc)
        self._r.set(_CASE_KEY.format(case_id), record.model_dump_json())
        return record

    def update_result(
        self,
        case_id: UUID,
        status: CaseStatus,
        orchestrator_output: OrchestratorOutput,
        classifier_output: ClassifierOutput | None = None,
        kyc_output: KYCOutput | None = None,
        claims_output: ClaimsOutput | None = None,
        policy_output: PolicyOutput | None = None,
        fraud_output: FraudOutput | None = None,
    ) -> CaseRecord | None:
        record = self.get(case_id)
        if record is None:
            return None
        now = datetime.now(tz=timezone.utc)
        record.status = status
        record.orchestrator_output = orchestrator_output
        record.classifier_output = classifier_output
        record.kyc_output = kyc_output
        record.claims_output = claims_output
        record.policy_output = policy_output
        record.fraud_output = fraud_output
        record.updated_at = now
        record.audit_log.append(
            AuditEntry(
                timestamp=now,
                actor="system",
                action="PIPELINE_DECISION",
                decision=orchestrator_output.decision,
                reason="; ".join(orchestrator_output.reasons[:2]),
            )
        )
        self._r.set(_CASE_KEY.format(case_id), record.model_dump_json())
        return record

    def override_decision(
        self,
        case_id: UUID,
        decision: str,
        reason: str = "",
        actor: str = "reviewer",
    ) -> CaseRecord | None:
        record = self.get(case_id)
        if record is None:
            return None
        record.status = CaseStatus.APPROVED if decision == "APPROVE" else CaseStatus.DENIED
        now = datetime.now(tz=timezone.utc)
        record.updated_at = now
        record.audit_log.append(
            AuditEntry(
                timestamp=now,
                actor=actor,
                action="MANUAL_OVERRIDE",
                decision=decision,
                reason=reason,
            )
        )
        self._r.set(_CASE_KEY.format(case_id), record.model_dump_json())
        return record

    def list_paginated(
        self, page: int, page_size: int, status: str | None = None
    ) -> tuple[list[CaseRecord], int]:
        if status is None:
            total = self._r.zcard(_CASES_ZSET)
            start = (page - 1) * page_size
            end = start + page_size - 1
            ids = self._r.zrevrange(_CASES_ZSET, start, end)
            records = []
            for id_str in ids:
                record = self.get(UUID(id_str))
                if record is not None:
                    records.append(record)
            return records, total
        else:
            all_ids = self._r.zrevrange(_CASES_ZSET, 0, -1)
            filtered: list[CaseRecord] = []
            for id_str in all_ids:
                record = self.get(UUID(id_str))
                if record is not None and record.status.value == status:
                    filtered.append(record)
            total = len(filtered)
            s = (page - 1) * page_size
            return filtered[s : s + page_size], total
