"""Unit tests for KYCAgent.

Three core cases:
  1. Passing KYC — known member, unexpired document, no visual anomalies
  2. Expired ID — document_expired flag from LLM
  3. Tampered document — visual anomalies returned by LLM
"""

import json
from unittest.mock import MagicMock
from uuid import uuid4

from pipeline.agents.kyc import KYCAgent
from shared.enums import DocumentType
from shared.schemas.agent_io import KYCInput

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MOCK_MEMBERS = [
    {
        "member_id": "M001234",
        "full_name": "Jane Doe",
        "dob": "1985-03-15",
        "policy_number": "POL-2024-001234",
        "plan_type": "GOLD",
    }
]

_VALID_TEXT = (
    "MediShield Membership Card\n"
    "Member: Jane Doe | ID: M001234\n"
    "DOB: 1985-03-15 | Policy: POL-2024-001234\n"
    "Valid through: 2027-01-01"
)


def _make_llm_response(
    member_id: str = "M001234",
    dob: str = "1985-03-15",
    policy_number: str = "POL-2024-001234",
    document_expired: bool = False,
    visual_anomalies: list[str] | None = None,
    confidence: float = 0.95,
) -> MagicMock:
    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps({
        "member_id_extracted": member_id,
        "dob_extracted": dob,
        "policy_number_extracted": policy_number,
        "document_expired": document_expired,
        "visual_anomalies": visual_anomalies or [],
        "confidence": confidence,
    })
    message = MagicMock()
    message.tool_calls = [tool_call]
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_agent(llm_response: MagicMock) -> KYCAgent:
    client = MagicMock()
    client.chat.completions.create.return_value = llm_response
    return KYCAgent(client=client, members_fixture=_MOCK_MEMBERS)


def _valid_input() -> KYCInput:
    return KYCInput(
        case_id=uuid4(),
        doc_type=DocumentType.ID_DOCUMENT,
        extracted_text=_VALID_TEXT,
    )


# ---------------------------------------------------------------------------
# Case 1 — Passing KYC
# ---------------------------------------------------------------------------


def test_kyc_passes_for_known_valid_member() -> None:
    agent = _make_agent(_make_llm_response())

    result = agent.run(_valid_input())

    assert result.kyc_passed is True
    assert result.flags == []
    assert result.confidence == 0.95


# ---------------------------------------------------------------------------
# Case 2 — Expired ID document
# ---------------------------------------------------------------------------


def test_kyc_fails_for_expired_document() -> None:
    agent = _make_agent(_make_llm_response(document_expired=True))

    result = agent.run(_valid_input())

    assert result.kyc_passed is False
    assert "DOCUMENT_EXPIRED" in result.flags


def test_expired_document_preserves_confidence() -> None:
    agent = _make_agent(_make_llm_response(document_expired=True, confidence=0.88))

    result = agent.run(_valid_input())

    assert result.confidence == 0.88


# ---------------------------------------------------------------------------
# Case 3 — Tampered document (visual anomalies from LLM)
# ---------------------------------------------------------------------------


def test_kyc_fails_for_tampered_document() -> None:
    anomalies = [
        "pixelated border around photo",
        "inconsistent font in member ID field",
    ]
    agent = _make_agent(_make_llm_response(visual_anomalies=anomalies))

    result = agent.run(_valid_input())

    assert result.kyc_passed is False
    assert "pixelated border around photo" in result.flags
    assert "inconsistent font in member ID field" in result.flags


def test_tampered_doc_does_not_add_member_not_found_when_member_exists() -> None:
    """Tampering flags and DB-lookup flags must be independent."""
    anomalies = ["signs of digital alteration near expiry date"]
    agent = _make_agent(_make_llm_response(visual_anomalies=anomalies))

    result = agent.run(_valid_input())

    assert "MEMBER_NOT_FOUND" not in result.flags


# ---------------------------------------------------------------------------
# Extra edge cases
# ---------------------------------------------------------------------------


def test_kyc_fails_when_member_not_in_db() -> None:
    agent = _make_agent(
        _make_llm_response(member_id="M999999", policy_number="POL-9999-000000")
    )

    result = agent.run(_valid_input())

    assert result.kyc_passed is False
    assert "MEMBER_NOT_FOUND" in result.flags


def test_kyc_combines_expired_and_tampered_flags() -> None:
    agent = _make_agent(
        _make_llm_response(
            document_expired=True,
            visual_anomalies=["inconsistent laminate texture"],
        )
    )

    result = agent.run(_valid_input())

    assert "DOCUMENT_EXPIRED" in result.flags
    assert "inconsistent laminate texture" in result.flags
    assert result.kyc_passed is False


def test_kyc_agent_calls_llm_exactly_once() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response()
    agent = KYCAgent(client=mock_client, members_fixture=_MOCK_MEMBERS)

    agent.run(_valid_input())

    mock_client.chat.completions.create.assert_called_once()


def test_kyc_with_image_bytes_includes_image_block() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response()
    agent = KYCAgent(client=mock_client, members_fixture=_MOCK_MEMBERS)

    agent.run(
        KYCInput(
            case_id=uuid4(),
            doc_type=DocumentType.ID_DOCUMENT,
            extracted_text=_VALID_TEXT,
            image_bytes=b"\xff\xd8\xff\xe0" + b"\x00" * 50,
        )
    )

    # messages[0] = system, messages[1] = user
    call_messages = mock_client.chat.completions.create.call_args[1]["messages"]
    content = call_messages[1]["content"]
    types = [block["type"] for block in content]
    assert "image_url" in types
    assert "text" in types
