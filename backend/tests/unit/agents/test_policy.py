"""Unit tests for PolicyAgent.

Three core cases:
  1. Covered procedure — outpatient office visit (CPT 99213), 80% coverage
  2. Covered procedure — chest X-ray (CPT 71046), 70% coverage
  3. Excluded procedure — cosmetic blepharoplasty (CPT 15820)

ChromaDB collection and OpenAI client are both mocked so tests run without
any external services or model downloads.
"""

import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from pipeline.agents.policy import PolicyAgent
from shared.schemas.agent_io import PolicyInput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(
    covered: bool = True,
    coverage_percentage: float = 0.80,
    policy_clause: str = "Section 4.2",
    exclusions: list[str] | None = None,
) -> MagicMock:
    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps({
        "covered": covered,
        "coverage_percentage": coverage_percentage,
        "policy_clause": policy_clause,
        "exclusions": exclusions or [],
    })
    message = MagicMock()
    message.tool_calls = [tool_call]
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_collection(documents: list[str] | None = None) -> MagicMock:
    docs = documents or [
        "Section 4.2: Outpatient visits (CPT 99201-99215) covered at 80%.",
        "Section 4.1: Preventive care covered at 100%.",
        "Section 6.0: Surgical procedures covered at 75%.",
    ]
    mock = MagicMock()
    mock.query.return_value = {
        "documents": [docs],
        "metadatas": [[{}] * len(docs)],
        "distances": [[0.1 * i for i in range(len(docs))]],
    }
    return mock


def _make_agent(
    llm_response: MagicMock,
    collection_docs: list[str] | None = None,
) -> PolicyAgent:
    client = MagicMock()
    client.chat.completions.create.return_value = llm_response
    collection = _make_collection(collection_docs)
    return PolicyAgent(client=client, chroma_collection=collection)


# ---------------------------------------------------------------------------
# Case 1 — Covered: outpatient office visit (CPT 99213)
# ---------------------------------------------------------------------------


def test_office_visit_is_covered() -> None:
    agent = _make_agent(
        _make_llm_response(covered=True, coverage_percentage=0.80, policy_clause="Section 4.2")
    )

    result = agent.run(PolicyInput(case_id=uuid4(), cpt_codes=["99213"]))

    assert result.covered is True
    assert result.coverage_percentage == pytest.approx(0.80)
    assert "4.2" in result.policy_clause
    assert result.exclusions == []


def test_office_visit_coverage_percentage_in_valid_range() -> None:
    agent = _make_agent(
        _make_llm_response(covered=True, coverage_percentage=0.80, policy_clause="Section 4.2")
    )

    result = agent.run(PolicyInput(case_id=uuid4(), cpt_codes=["99213"]))

    assert 0.0 <= result.coverage_percentage <= 1.0


# ---------------------------------------------------------------------------
# Case 2 — Covered: chest X-ray (CPT 71046)
# ---------------------------------------------------------------------------


def test_chest_xray_is_covered() -> None:
    radiology_docs = [
        "Section 5.1: Diagnostic imaging including chest X-ray (CPT 71046) covered at 70%.",
        "Section 5.0: Radiology requires a valid referral.",
        "Section 4.2: Outpatient visits covered at 80%.",
    ]
    agent = _make_agent(
        _make_llm_response(covered=True, coverage_percentage=0.70, policy_clause="Section 5.1"),
        collection_docs=radiology_docs,
    )

    result = agent.run(PolicyInput(case_id=uuid4(), cpt_codes=["71046"]))

    assert result.covered is True
    assert result.coverage_percentage == pytest.approx(0.70)
    assert "5.1" in result.policy_clause
    assert result.exclusions == []


# ---------------------------------------------------------------------------
# Case 3 — Excluded: cosmetic blepharoplasty (CPT 15820)
# ---------------------------------------------------------------------------


def test_cosmetic_blepharoplasty_is_excluded() -> None:
    cosmetic_docs = [
        "Section 9.1: Cosmetic procedures are excluded. Blepharoplasty (CPT 15820) not covered.",
        "Section 9.2: Experimental treatments not covered.",
        "Section 4.2: Outpatient visits covered at 80%.",
    ]
    agent = _make_agent(
        _make_llm_response(
            covered=False,
            coverage_percentage=0.0,
            policy_clause="Section 9.1",
            exclusions=["Section 9.1: Cosmetic procedures (CPT 15820) are expressly excluded."],
        ),
        collection_docs=cosmetic_docs,
    )

    result = agent.run(PolicyInput(case_id=uuid4(), cpt_codes=["15820"]))

    assert result.covered is False
    assert result.coverage_percentage == pytest.approx(0.0)
    assert len(result.exclusions) > 0
    assert any("15820" in e or "cosmetic" in e.lower() for e in result.exclusions)


# ---------------------------------------------------------------------------
# Behavioural / structural tests
# ---------------------------------------------------------------------------


def test_chroma_queried_with_joined_cpt_codes() -> None:
    mock_collection = _make_collection()
    client = MagicMock()
    client.chat.completions.create.return_value = _make_llm_response()
    agent = PolicyAgent(client=client, chroma_collection=mock_collection)

    agent.run(PolicyInput(case_id=uuid4(), cpt_codes=["99213", "99214"]))

    mock_collection.query.assert_called_once_with(
        query_texts=["99213 99214"], n_results=3
    )


def test_chroma_queried_once_per_run() -> None:
    mock_collection = _make_collection()
    client = MagicMock()
    client.chat.completions.create.return_value = _make_llm_response()
    agent = PolicyAgent(client=client, chroma_collection=mock_collection)

    agent.run(PolicyInput(case_id=uuid4(), cpt_codes=["71046"]))

    assert mock_collection.query.call_count == 1


def test_llm_receives_retrieved_clauses_in_prompt() -> None:
    """The LLM prompt must include the text returned by ChromaDB."""
    clause_text = "Section 4.2: Office visits at 80%."
    mock_collection = _make_collection(documents=[clause_text])
    client = MagicMock()
    client.chat.completions.create.return_value = _make_llm_response()
    agent = PolicyAgent(client=client, chroma_collection=mock_collection)

    agent.run(PolicyInput(case_id=uuid4(), cpt_codes=["99213"]))

    call_messages = client.chat.completions.create.call_args[1]["messages"]
    prompt_text = call_messages[1]["content"]  # index 1 = user message (0 = system)
    assert clause_text in prompt_text


def test_policy_agent_calls_llm_exactly_once() -> None:
    mock_collection = _make_collection()
    client = MagicMock()
    client.chat.completions.create.return_value = _make_llm_response()
    agent = PolicyAgent(client=client, chroma_collection=mock_collection)

    agent.run(PolicyInput(case_id=uuid4(), cpt_codes=["99213"]))

    client.chat.completions.create.assert_called_once()


def test_ingest_chunks_populates_collection() -> None:
    """ingest_chunks must call collection.add with correct ids and documents."""
    mock_collection = MagicMock()
    client = MagicMock()
    agent = PolicyAgent(client=client, chroma_collection=mock_collection)

    chunks = [
        {"id": "c1", "text": "Clause one.", "metadata": {"section": "1.0"}},
        {"id": "c2", "text": "Clause two.", "metadata": {"section": "2.0"}},
    ]
    agent.ingest_chunks(chunks)

    mock_collection.add.assert_called_once_with(
        ids=["c1", "c2"],
        documents=["Clause one.", "Clause two."],
        metadatas=[{"section": "1.0"}, {"section": "2.0"}],
    )
