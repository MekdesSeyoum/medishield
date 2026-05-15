"""Integration tests for the full MediShield LangGraph pipeline.

Three end-to-end cases are exercised:
  1. APPROVE  — KYC passes, procedure covered, fraud score 0.0
  2. REJECT   — KYC fails (expired document), pipeline short-circuits
  3. ESCALATE — KYC passes, covered, but fraud score ≥ 0.30 (high-frequency provider)

All agent dependencies (classifier, kyc, claims, policy, fraud) are replaced with
lightweight stubs so the test suite runs without any LLM calls, ChromaDB, or MinIO.
"""

import base64
from datetime import date
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from pipeline.agents.fraud import FraudAgent
from pipeline.agents.orchestrator import OrchestratorAgent
from pipeline.graph import build_graph
from shared.schemas.agent_io import (
    ClassifierOutput,
    ClaimsOutput,
    FraudInput,
    FraudOutput,
    KYCOutput,
    OrchestratorOutput,
    PolicyOutput,
)
from shared.enums import DocumentType

# ---------------------------------------------------------------------------
# Stub agents
# ---------------------------------------------------------------------------

_DUMMY_B64 = base64.b64encode(b"dummy").decode()
_DUMMY_CASE_ID = str(uuid4())


def _classifier_stub(doc_type: str = "CLAIM_FORM"):
    """Returns a mock classifier that always yields the given doc type."""
    agent = MagicMock()
    agent.run.return_value = ClassifierOutput(
        document_type=DocumentType(doc_type),
        confidence=0.99,
        page_count=1,
        is_handwritten=False,
        routing_hints=[],
    )
    return agent


def _kyc_stub(passed: bool, flags: list[str] | None = None):
    agent = MagicMock()
    agent.run.return_value = KYCOutput(
        kyc_passed=passed,
        flags=flags or [],
        confidence=0.95,
    )
    return agent


def _claims_stub(cpt_codes: list[str] | None = None):
    agent = MagicMock()
    agent.run.return_value = ClaimsOutput(
        extracted_fields={
            "cpt_codes": cpt_codes or ["99213"],
            "service_date": "2024-03-20",
            "claim_amount": 150.0,
            "provider_npi": "1111111111",
            "patient_id": "PAT-001",
        },
        schema_valid=True,
        validation_errors=[],
    )
    return agent


def _policy_stub(covered: bool, coverage_pct: float = 0.80):
    agent = MagicMock()
    agent.run.return_value = PolicyOutput(
        covered=covered,
        coverage_percentage=coverage_pct if covered else 0.0,
        policy_clause="Section 4.2" if covered else "Section 9.1",
        exclusions=[] if covered else ["Section 9.1: Cosmetic procedures not covered."],
    )
    return agent


def _fraud_stub_from_agent(fraud_agent: FraudAgent, patient_id: str, provider_npi: str,
                            claim_amount: float, service_date: str) -> MagicMock:
    """Wraps a real FraudAgent as a stub that's pre-configured with specific input."""
    agent = MagicMock()
    from uuid import uuid4 as _uuid4

    def _run(inp):
        return fraud_agent.run(inp)

    agent.run.side_effect = _run
    return agent


def _build_state(
    case_id: str = _DUMMY_CASE_ID,
    patient_id: str = "PAT-001",
    provider_npi: str = "1111111111",
    claim_amount: float = 150.0,
) -> dict:
    return {
        "case_id": case_id,
        "file_key": "test/doc.pdf",
        "file_name": "doc.pdf",
        "mime_type": "application/pdf",
        "raw_bytes_b64": _DUMMY_B64,
        "extracted_text": "Sample claim document",
        "patient_id": patient_id,
        "provider_npi": provider_npi,
        "claim_amount": claim_amount,
        "cpt_codes": ["99213"],
    }


# ---------------------------------------------------------------------------
# Case 1 — APPROVE
# ---------------------------------------------------------------------------


def test_pipeline_approve() -> None:
    """All checks pass → APPROVE decision."""
    # FraudAgent with clean provider — no flags fire
    fraud_history = [
        {"claim_id": "H001", "patient_id": "PAT-001", "provider_npi": "1111111111",
         "claim_amount": 150.0, "service_date": "2024-01-05"},
        {"claim_id": "H002", "patient_id": "PAT-001", "provider_npi": "1111111111",
         "claim_amount": 175.0, "service_date": "2024-02-10"},
    ]
    fraud_agent = FraudAgent(claim_history=fraud_history, reference_date=date(2024, 3, 20))

    pipeline = build_graph(
        classifier=_classifier_stub(),
        kyc=_kyc_stub(passed=True),
        claims=_claims_stub(),
        policy=_policy_stub(covered=True, coverage_pct=0.80),
        fraud=_fraud_stub_from_agent(fraud_agent, "PAT-001", "1111111111", 150.0, "2024-03-20"),
    )

    final_state = pipeline.invoke(_build_state())

    orch: dict = final_state["orchestrator_output"]
    assert orch["decision"] == "APPROVE"
    assert orch["fraud_score"] == 0.0
    assert orch["coverage_percentage"] == pytest.approx(0.80)
    assert len(orch["reasons"]) >= 1


def test_pipeline_approve_sets_orchestrator_output() -> None:
    """Verify the orchestrator_output dict has the expected keys."""
    fraud_history: list[dict] = []
    fraud_agent = FraudAgent(claim_history=fraud_history, reference_date=date(2024, 3, 20))

    pipeline = build_graph(
        classifier=_classifier_stub(),
        kyc=_kyc_stub(passed=True),
        claims=_claims_stub(),
        policy=_policy_stub(covered=True),
        fraud=_fraud_stub_from_agent(fraud_agent, "PAT-NEW", "9999999999", 100.0, "2024-03-20"),
    )

    final_state = pipeline.invoke(_build_state(patient_id="PAT-NEW", provider_npi="9999999999"))

    orch = final_state["orchestrator_output"]
    assert {"decision", "reasons", "fraud_score", "coverage_percentage"} <= orch.keys()


# ---------------------------------------------------------------------------
# Case 2 — REJECT
# ---------------------------------------------------------------------------


def test_pipeline_reject_on_kyc_failure() -> None:
    """KYC fails → pipeline produces REJECT regardless of policy/fraud."""
    pipeline = build_graph(
        classifier=_classifier_stub(),
        kyc=_kyc_stub(passed=False, flags=["DOCUMENT_EXPIRED"]),
        claims=_claims_stub(),
        policy=_policy_stub(covered=True),
        fraud=MagicMock(run=MagicMock(return_value=FraudOutput(
            fraud_score=0.0, anomalies=[], risk_level="LOW"
        ))),
    )

    final_state = pipeline.invoke(_build_state())

    orch = final_state["orchestrator_output"]
    assert orch["decision"] == "REJECT"
    assert any("DOCUMENT_EXPIRED" in r for r in orch["reasons"])


def test_pipeline_reject_on_policy_exclusion() -> None:
    """Procedure not covered → REJECT even with clean KYC and fraud."""
    pipeline = build_graph(
        classifier=_classifier_stub(),
        kyc=_kyc_stub(passed=True),
        claims=_claims_stub(cpt_codes=["15820"]),
        policy=_policy_stub(covered=False),
        fraud=MagicMock(run=MagicMock(return_value=FraudOutput(
            fraud_score=0.0, anomalies=[], risk_level="LOW"
        ))),
    )

    final_state = pipeline.invoke(_build_state())

    orch = final_state["orchestrator_output"]
    assert orch["decision"] == "REJECT"
    assert any("not covered" in r.lower() or "9.1" in r for r in orch["reasons"])


# ---------------------------------------------------------------------------
# Case 3 — ESCALATE
# ---------------------------------------------------------------------------


def test_pipeline_escalate_on_high_frequency_fraud() -> None:
    """Provider with high-frequency flag → fraud_score 0.30 → ESCALATE."""
    # Provider 4444444444 has 6 claims in the past 7 days (same fixture as unit tests)
    high_freq_history = [
        {"claim_id": f"H{i:03d}", "patient_id": f"PAT-{i}", "provider_npi": "4444444444",
         "claim_amount": 200.0, "service_date": f"2024-03-{13 + i}"}
        for i in range(1, 7)
    ]
    fraud_agent = FraudAgent(claim_history=high_freq_history, reference_date=date(2024, 3, 20))

    pipeline = build_graph(
        classifier=_classifier_stub(),
        kyc=_kyc_stub(passed=True),
        claims=_claims_stub(),
        policy=_policy_stub(covered=True),
        fraud=_fraud_stub_from_agent(
            fraud_agent, "PAT-NEW", "4444444444", 200.0, "2024-03-20"
        ),
    )

    final_state = pipeline.invoke(
        _build_state(patient_id="PAT-NEW", provider_npi="4444444444", claim_amount=200.0)
    )

    orch = final_state["orchestrator_output"]
    assert orch["decision"] == "ESCALATE"
    assert orch["fraud_score"] == pytest.approx(0.30, abs=1e-4)
    assert any("claims" in r.lower() or "frequency" in r.lower() or "fraud" in r.lower()
               for r in orch["reasons"])


def test_pipeline_escalate_on_duplicate_fraud() -> None:
    """Duplicate submission (fraud_score 0.65) → ESCALATE.

    The claims stub returns service_date matching the duplicate history so the
    real FraudAgent fires the duplicate check.
    """
    dup_history = [
        {"claim_id": "H001", "patient_id": "PAT-002", "provider_npi": "2222222222",
         "claim_amount": 300.0, "service_date": "2024-03-18"},
    ]
    fraud_agent = FraudAgent(claim_history=dup_history, reference_date=date(2024, 3, 20))

    # Claims stub that returns the matching service_date
    claims_dup = MagicMock()
    claims_dup.run.return_value = ClaimsOutput(
        extracted_fields={
            "cpt_codes": ["99213"],
            "service_date": "2024-03-18",  # matches duplicate anchor
            "claim_amount": 300.0,
            "provider_npi": "2222222222",
            "patient_id": "PAT-002",
        },
        schema_valid=True,
        validation_errors=[],
    )

    pipeline = build_graph(
        classifier=_classifier_stub(),
        kyc=_kyc_stub(passed=True),
        claims=claims_dup,
        policy=_policy_stub(covered=True),
        fraud=_fraud_stub_from_agent(
            fraud_agent, "PAT-002", "2222222222", 300.0, "2024-03-18"
        ),
    )

    final_state = pipeline.invoke(
        _build_state(patient_id="PAT-002", provider_npi="2222222222", claim_amount=300.0)
    )

    orch = final_state["orchestrator_output"]
    assert orch["decision"] == "ESCALATE"
    assert orch["fraud_score"] == pytest.approx(0.65, abs=1e-4)


# ---------------------------------------------------------------------------
# OrchestratorAgent unit tests (pure decision logic)
# ---------------------------------------------------------------------------


def _kyc_ok() -> KYCOutput:
    return KYCOutput(kyc_passed=True, flags=[], confidence=0.99)


def _kyc_fail(flag: str = "DOCUMENT_EXPIRED") -> KYCOutput:
    return KYCOutput(kyc_passed=False, flags=[flag], confidence=0.99)


def _policy_ok(pct: float = 0.80) -> PolicyOutput:
    return PolicyOutput(covered=True, coverage_percentage=pct,
                        policy_clause="Section 4.2", exclusions=[])


def _policy_excluded() -> PolicyOutput:
    return PolicyOutput(covered=False, coverage_percentage=0.0,
                        policy_clause="Section 9.1",
                        exclusions=["Section 9.1: Cosmetic excluded."])


def _fraud_clean() -> FraudOutput:
    return FraudOutput(fraud_score=0.0, anomalies=[], risk_level="LOW")


def _fraud_medium(score: float = 0.30) -> FraudOutput:
    return FraudOutput(fraud_score=score, anomalies=["High frequency"], risk_level="MEDIUM")


def test_orchestrator_approve() -> None:
    result = OrchestratorAgent().run(_kyc_ok(), _policy_ok(), _fraud_clean())
    assert result.decision == "APPROVE"
    assert result.fraud_score == 0.0
    assert result.coverage_percentage == pytest.approx(0.80)


def test_orchestrator_reject_kyc() -> None:
    result = OrchestratorAgent().run(_kyc_fail(), _policy_ok(), _fraud_clean())
    assert result.decision == "REJECT"
    assert "DOCUMENT_EXPIRED" in result.reasons


def test_orchestrator_reject_policy() -> None:
    result = OrchestratorAgent().run(_kyc_ok(), _policy_excluded(), _fraud_clean())
    assert result.decision == "REJECT"
    assert any("not covered" in r.lower() for r in result.reasons)


def test_orchestrator_escalate_fraud() -> None:
    result = OrchestratorAgent().run(_kyc_ok(), _policy_ok(), _fraud_medium(0.30))
    assert result.decision == "ESCALATE"
    assert result.fraud_score == pytest.approx(0.30)


def test_orchestrator_kyc_takes_priority_over_fraud() -> None:
    """KYC failure must produce REJECT even when fraud is also elevated."""
    result = OrchestratorAgent().run(_kyc_fail(), _policy_ok(), _fraud_medium(0.65))
    assert result.decision == "REJECT"
