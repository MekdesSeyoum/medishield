import base64
import sys
from pathlib import Path
from uuid import UUID

# Ensure the backend root is always on sys.path, regardless of launch directory.
_root = str(Path(__file__).parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from db.case_store import CaseStore
from shared.enums import CaseStatus
from shared.schemas.agent_io import (
    ClassifierOutput,
    ClaimsOutput,
    FraudOutput,
    KYCOutput,
    OrchestratorOutput,
    PolicyOutput,
)
from pipeline.graph import build_graph
from core.config import get_settings
from storage.minio_client import get_minio
from worker.celery_app import celery_app


@celery_app.task(name="medishield.process_document", bind=True, max_retries=3)
def process_document(self, case_id: str) -> dict:
    """Run the full MediShield LangGraph pipeline for a submitted document.

    1. Fetches raw bytes from MinIO.
    2. Marks case PROCESSING in Redis.
    3. Invokes the compiled LangGraph (classifier → kyc+claims+policy → fraud → orchestrator).
    4. Persists all agent outputs and final status to Redis.
    """
    try:
        settings = get_settings()
        store = CaseStore()

        record = store.get(UUID(case_id))
        if record is None:
            return {"case_id": case_id, "error": "not found"}

        store.update_status(UUID(case_id), CaseStatus.PROCESSING)

        minio = get_minio()
        response = minio.get_object(settings.minio_bucket, record.file_key)
        raw_bytes = response.read()
        response.close()
        response.release_conn()
        raw_bytes_b64 = base64.b64encode(raw_bytes).decode()

        initial_state = {
            "case_id": case_id,
            "file_key": record.file_key,
            "file_name": record.file_name,
            "mime_type": record.mime_type,
            "raw_bytes_b64": raw_bytes_b64,
        }

        pipeline = build_graph()
        final_state = pipeline.invoke(initial_state)

        def _load(cls, key):
            data = final_state.get(key)
            return cls.model_validate(data) if data else None

        orch_output = _load(OrchestratorOutput, "orchestrator_output")
        if orch_output is None:
            store.update_status(UUID(case_id), CaseStatus.ESCALATED)
            return {"case_id": case_id, "error": "orchestrator produced no output"}

        decision_to_status = {
            "APPROVE": CaseStatus.APPROVED,
            "REJECT": CaseStatus.DENIED,
            "ESCALATE": CaseStatus.ESCALATED,
        }
        final_status = decision_to_status.get(orch_output.decision, CaseStatus.ESCALATED)

        store.update_result(
            UUID(case_id),
            final_status,
            orch_output,
            classifier_output=_load(ClassifierOutput, "classifier_output"),
            kyc_output=_load(KYCOutput, "kyc_output"),
            claims_output=_load(ClaimsOutput, "claims_output"),
            policy_output=_load(PolicyOutput, "policy_output"),
            fraud_output=_load(FraudOutput, "fraud_output"),
        )
        return {"case_id": case_id, "status": final_status.value, "decision": orch_output.decision}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=2**self.request.retries)
