"""LangGraph pipeline for MediShield document processing.

Topology:
    classifier
        ├── kyc_node
        ├── claims_node   (fan-out)
        └── policy_node
              └── fraud_node → orchestrator_node
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.graph import END, StateGraph

from pipeline.state import MediShieldState


# ---------------------------------------------------------------------------
# Node factories (accept pre-built agents for test injection)
# ---------------------------------------------------------------------------


def _make_classifier_node(classifier: Any | None):
    def classifier_node(state: MediShieldState) -> dict:
        if classifier is None:
            from pipeline.agents.classifier import ClassifierAgent
            agent = ClassifierAgent()
        else:
            agent = classifier

        from shared.schemas.agent_io import ClassifierInput
        output = agent.run(
            ClassifierInput(
                case_id=UUID(state["case_id"]),
                file_key=state["file_key"],
                file_name=state["file_name"],
                mime_type=state["mime_type"],
                raw_bytes_b64=state["raw_bytes_b64"],
            )
        )
        return {"classifier_output": output.model_dump()}

    return classifier_node


def _make_kyc_node(kyc: Any | None):
    def kyc_node(state: MediShieldState) -> dict:
        if kyc is None:
            from pipeline.agents.kyc import KYCAgent
            agent = KYCAgent()
        else:
            agent = kyc

        from shared.schemas.agent_io import KYCInput
        from shared.schemas.agent_io import ClassifierOutput
        import base64
        classifier_out = ClassifierOutput.model_validate(state["classifier_output"])
        raw_b64 = state.get("raw_bytes_b64", "")
        image_bytes = base64.b64decode(raw_b64) if raw_b64 else None
        output = agent.run(
            KYCInput(
                case_id=UUID(state["case_id"]),
                doc_type=classifier_out.document_type,
                extracted_text=state.get("extracted_text", ""),
                image_bytes=image_bytes,
            )
        )
        return {"kyc_output": output.model_dump()}

    return kyc_node


def _make_claims_node(claims: Any | None):
    def claims_node(state: MediShieldState) -> dict:
        if claims is None:
            from pipeline.agents.claims import ClaimsAgent
            agent = ClaimsAgent()
        else:
            agent = claims

        from shared.schemas.agent_io import ClaimsInput
        output = agent.run(
            ClaimsInput(
                case_id=UUID(state["case_id"]),
                extracted_text=state.get("extracted_text", ""),
                raw_fields={},
                raw_bytes_b64=state.get("raw_bytes_b64", ""),
                mime_type=state.get("mime_type", ""),
            )
        )
        result = output.model_dump()
        fields = output.extracted_fields
        cpt_codes = fields.get("cpt_codes") or state.get("cpt_codes") or []
        # Propagate fraud-relevant fields so the fraud node can read them from state
        provider_npi = state.get("provider_npi") or str(fields.get("provider_npi", ""))
        claim_amount = state.get("claim_amount") or float(fields.get("claim_amount") or 0.0)
        return {
            "claims_output": result,
            "cpt_codes": cpt_codes,
            "provider_npi": provider_npi,
            "claim_amount": claim_amount,
        }

    return claims_node


def _make_policy_node(policy: Any | None):
    def policy_node(state: MediShieldState) -> dict:
        if policy is None:
            from pipeline.agents.policy import PolicyAgent
            agent = PolicyAgent()
            agent.load_fixture()
        else:
            agent = policy

        from shared.schemas.agent_io import PolicyInput
        cpt_codes = state.get("cpt_codes") or []
        output = agent.run(PolicyInput(case_id=UUID(state["case_id"]), cpt_codes=cpt_codes))
        return {"policy_output": output.model_dump()}

    return policy_node


def _make_fraud_node(fraud: Any | None):
    def fraud_node(state: MediShieldState) -> dict:
        if fraud is None:
            from pipeline.agents.fraud import FraudAgent
            agent = FraudAgent()
        else:
            agent = fraud

        from shared.schemas.agent_io import FraudInput
        output = agent.run(
            FraudInput(
                case_id=UUID(state["case_id"]),
                extracted_fields=state.get("claims_output", {}).get("extracted_fields", {}),
                patient_id=state.get("patient_id", ""),
                provider_npi=state.get("provider_npi", ""),
                claim_amount=state.get("claim_amount", 0.0),
            )
        )
        return {"fraud_output": output.model_dump()}

    return fraud_node


def _make_orchestrator_node():
    def orchestrator_node(state: MediShieldState) -> dict:
        from pipeline.agents.orchestrator import OrchestratorAgent
        from shared.schemas.agent_io import KYCOutput, PolicyOutput, FraudOutput

        agent = OrchestratorAgent()
        output = agent.run(
            kyc_output=KYCOutput.model_validate(state["kyc_output"]),
            policy_output=PolicyOutput.model_validate(state["policy_output"]),
            fraud_output=FraudOutput.model_validate(state["fraud_output"]),
        )
        return {"orchestrator_output": output.model_dump()}

    return orchestrator_node


# ---------------------------------------------------------------------------
# Fan-out / fan-in helpers
# ---------------------------------------------------------------------------


def _parallel_fan_out(state: MediShieldState) -> list[str]:
    """After classifier, run kyc, claims, and policy in parallel."""
    return ["kyc", "claims", "policy"]


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def build_graph(
    classifier: Any | None = None,
    kyc: Any | None = None,
    claims: Any | None = None,
    policy: Any | None = None,
    fraud: Any | None = None,
) -> StateGraph:
    """Build and compile the MediShield LangGraph pipeline.

    Pass pre-built agent instances to override defaults — used in integration
    tests to inject mocks without touching real services.
    """
    graph = StateGraph(MediShieldState)

    graph.add_node("classifier", _make_classifier_node(classifier))
    graph.add_node("kyc", _make_kyc_node(kyc))
    graph.add_node("claims", _make_claims_node(claims))
    graph.add_node("policy", _make_policy_node(policy))
    graph.add_node("fraud", _make_fraud_node(fraud))
    graph.add_node("orchestrator", _make_orchestrator_node())

    # Entry point
    graph.set_entry_point("classifier")

    # classifier → fan-out to kyc, claims, policy in parallel
    graph.add_conditional_edges("classifier", _parallel_fan_out, ["kyc", "claims", "policy"])

    # fan-in: all three feed into fraud
    graph.add_edge("kyc", "fraud")
    graph.add_edge("claims", "fraud")
    graph.add_edge("policy", "fraud")

    # fraud → orchestrator → end
    graph.add_edge("fraud", "orchestrator")
    graph.add_edge("orchestrator", END)

    return graph.compile()
