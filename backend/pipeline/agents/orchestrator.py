from typing import Literal

from shared.schemas.agent_io import (
    FraudOutput,
    KYCOutput,
    OrchestratorOutput,
    PolicyOutput,
)

# Fraud score at or above this threshold triggers ESCALATE (not outright REJECT)
_ESCALATE_FRAUD_THRESHOLD = 0.30


def _make_decision(
    kyc: KYCOutput,
    policy: PolicyOutput,
    fraud: FraudOutput,
) -> tuple[Literal["APPROVE", "REJECT", "ESCALATE"], list[str]]:
    reasons: list[str] = []

    # Hard REJECT conditions
    if not kyc.kyc_passed:
        reasons.extend(kyc.flags)
        return "REJECT", reasons

    if not policy.covered:
        reasons.append(f"Procedure not covered under policy ({policy.policy_clause})")
        reasons.extend(policy.exclusions)
        return "REJECT", reasons

    # ESCALATE when fraud risk is elevated
    if fraud.fraud_score >= _ESCALATE_FRAUD_THRESHOLD:
        reasons.extend(fraud.anomalies)
        reasons.append(f"Fraud score {fraud.fraud_score:.2f} (risk: {fraud.risk_level})")
        return "ESCALATE", reasons

    # All clear
    reasons.append(
        f"KYC passed, procedure covered at {policy.coverage_percentage:.0%}, "
        f"fraud score {fraud.fraud_score:.2f}"
    )
    return "APPROVE", reasons


class OrchestratorAgent:
    """Pure rule-based orchestrator — no LLM required."""

    def run(
        self,
        kyc_output: KYCOutput,
        policy_output: PolicyOutput,
        fraud_output: FraudOutput,
    ) -> OrchestratorOutput:
        decision, reasons = _make_decision(kyc_output, policy_output, fraud_output)
        return OrchestratorOutput(
            decision=decision,
            reasons=reasons,
            fraud_score=fraud_output.fraud_score,
            coverage_percentage=policy_output.coverage_percentage,
        )


def orchestrator_node(state: dict) -> dict:
    """LangGraph node: runs OrchestratorAgent and writes orchestrator_output into state."""
    from shared.schemas.agent_io import KYCOutput, PolicyOutput, FraudOutput

    agent = OrchestratorAgent()
    output = agent.run(
        kyc_output=KYCOutput.model_validate(state["kyc_output"]),
        policy_output=PolicyOutput.model_validate(state["policy_output"]),
        fraud_output=FraudOutput.model_validate(state["fraud_output"]),
    )
    return {"orchestrator_output": output.model_dump()}
