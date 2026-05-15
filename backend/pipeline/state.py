from typing import TypedDict

from shared.schemas.agent_io import (
    ClassifierOutput,
    ClaimsOutput,
    FraudOutput,
    KYCOutput,
    OrchestratorOutput,
    PolicyOutput,
)


class MediShieldState(TypedDict, total=False):
    # Inputs — populated before graph.invoke()
    case_id: str
    file_key: str
    file_name: str
    mime_type: str
    raw_bytes_b64: str       # base64-encoded document bytes
    extracted_text: str      # optional pre-extracted text
    patient_id: str
    provider_npi: str
    claim_amount: float
    cpt_codes: list[str]     # populated from ClaimsOutput; also accepted as input

    # Agent outputs — written by each node
    classifier_output: ClassifierOutput
    kyc_output: KYCOutput
    claims_output: ClaimsOutput
    policy_output: PolicyOutput
    fraud_output: FraudOutput
    orchestrator_output: OrchestratorOutput
