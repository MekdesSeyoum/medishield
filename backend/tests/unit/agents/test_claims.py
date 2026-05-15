"""Unit tests for ClaimsAgent.

Three core cases:
  1. Valid claim — all fields present and correctly formatted
  2. Missing required fields — empty icd10_codes list
  3. Invalid code format — malformed ICD-10 code
"""

import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from pipeline.agents.claims import ClaimSchema, ClaimsAgent
from shared.schemas.agent_io import ClaimsInput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(
    claim_amount: float = 1250.00,
    icd10_codes: list[str] | None = None,
    cpt_codes: list[str] | None = None,
    provider_npi: str = "1234567890",
    service_date: str = "2024-03-15",
) -> MagicMock:
    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps({
        "claim_amount": claim_amount,
        "icd10_codes": icd10_codes if icd10_codes is not None else ["J18.9"],
        "cpt_codes": cpt_codes if cpt_codes is not None else ["99213"],
        "provider_npi": provider_npi,
        "service_date": service_date,
    })
    message = MagicMock()
    message.tool_calls = [tool_call]
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_agent(llm_response: MagicMock) -> ClaimsAgent:
    client = MagicMock()
    client.chat.completions.create.return_value = llm_response
    return ClaimsAgent(client=client)


def _base_input(text: str = "Claim for patient Jane Doe, DOB 1985-03-15") -> ClaimsInput:
    return ClaimsInput(case_id=uuid4(), extracted_text=text, raw_fields={})


# ---------------------------------------------------------------------------
# Case 1 — Valid claim
# ---------------------------------------------------------------------------


def test_valid_claim_passes_schema_validation() -> None:
    agent = _make_agent(_make_llm_response())

    result = agent.run(_base_input())

    assert result.schema_valid is True
    assert result.validation_errors == []


def test_valid_claim_returns_correct_extracted_fields() -> None:
    agent = _make_agent(
        _make_llm_response(
            claim_amount=2500.75,
            icd10_codes=["J18.9", "I10"],
            cpt_codes=["99213", "71046"],
            provider_npi="9876543210",
            service_date="2024-06-01",
        )
    )

    result = agent.run(_base_input())

    assert result.extracted_fields["claim_amount"] == 2500.75
    assert result.extracted_fields["icd10_codes"] == ["J18.9", "I10"]
    assert result.extracted_fields["cpt_codes"] == ["99213", "71046"]
    assert result.extracted_fields["provider_npi"] == "9876543210"


# ---------------------------------------------------------------------------
# Case 2 — Missing required fields (empty icd10_codes)
# ---------------------------------------------------------------------------


def test_missing_icd10_codes_fails_validation() -> None:
    agent = _make_agent(_make_llm_response(icd10_codes=[]))

    result = agent.run(_base_input())

    assert result.schema_valid is False
    assert any("icd10_codes" in e for e in result.validation_errors)


def test_extracted_fields_always_returned_even_when_invalid() -> None:
    """extracted_fields must be present regardless of validation outcome."""
    agent = _make_agent(_make_llm_response(icd10_codes=[]))

    result = agent.run(_base_input())

    assert "claim_amount" in result.extracted_fields
    assert "icd10_codes" in result.extracted_fields


def test_zero_claim_amount_fails_validation() -> None:
    agent = _make_agent(_make_llm_response(claim_amount=0.0))

    result = agent.run(_base_input())

    assert result.schema_valid is False
    assert any("claim_amount" in e for e in result.validation_errors)


# ---------------------------------------------------------------------------
# Case 3 — Invalid code format
# ---------------------------------------------------------------------------


def test_malformed_icd10_code_fails_validation() -> None:
    agent = _make_agent(_make_llm_response(icd10_codes=["NOTVALID-999"]))

    result = agent.run(_base_input())

    assert result.schema_valid is False
    assert any("ICD-10" in e or "icd10" in e.lower() for e in result.validation_errors)


def test_malformed_cpt_code_fails_validation() -> None:
    agent = _make_agent(_make_llm_response(cpt_codes=["ABC"]))

    result = agent.run(_base_input())

    assert result.schema_valid is False
    assert any("CPT" in e or "cpt" in e.lower() for e in result.validation_errors)


def test_short_npi_fails_validation() -> None:
    agent = _make_agent(_make_llm_response(provider_npi="12345"))

    result = agent.run(_base_input())

    assert result.schema_valid is False
    assert any("npi" in e.lower() or "NPI" in e for e in result.validation_errors)


# ---------------------------------------------------------------------------
# ClaimSchema unit tests (schema-only, no LLM)
# ---------------------------------------------------------------------------


def test_claim_schema_valid_instance() -> None:
    schema = ClaimSchema.model_validate(
        {
            "claim_amount": 500.0,
            "icd10_codes": ["Z00.00"],
            "cpt_codes": ["99395"],
            "provider_npi": "1234567890",
            "service_date": "2024-01-15",
        }
    )
    assert schema.claim_amount == 500.0


def test_claim_schema_rejects_alpha_npi() -> None:
    with pytest.raises(Exception):
        ClaimSchema.model_validate(
            {
                "claim_amount": 100.0,
                "icd10_codes": ["Z00.00"],
                "cpt_codes": ["99395"],
                "provider_npi": "ABCDEFGHIJ",
                "service_date": "2024-01-15",
            }
        )


def test_claims_agent_calls_llm_once() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response()
    agent = ClaimsAgent(client=mock_client)

    agent.run(_base_input())

    mock_client.chat.completions.create.assert_called_once()


def test_raw_fields_are_included_in_llm_prompt() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_llm_response()
    agent = ClaimsAgent(client=mock_client)

    agent.run(
        ClaimsInput(
            case_id=uuid4(),
            extracted_text="Claim text",
            raw_fields={"ocr_amount": "$1,250.00", "ocr_date": "03/15/2024"},
        )
    )

    # messages[0] = system, messages[1] = user (string content)
    call_messages = mock_client.chat.completions.create.call_args[1]["messages"]
    content_text = call_messages[1]["content"]
    assert "ocr_amount" in content_text
