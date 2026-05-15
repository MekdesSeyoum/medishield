from uuid import uuid4

import pytest

from pipeline.agents.classifier import ClassifierAgent, _DEFAULT_MODEL, _LOW_CONFIDENCE_THRESHOLD
from shared.enums import DocumentType
from shared.schemas.agent_io import ClassifierInput, ClassifierOutput
from tests.conftest import make_tool_response


def _make_input(
    mime_type: str = "image/jpeg",
    file_name: str = "test.jpg",
    dummy_b64: str = "ZmFrZQ==",
) -> ClassifierInput:
    return ClassifierInput(
        case_id=uuid4(),
        file_key=f"uploads/{uuid4()}/{file_name}",
        file_name=file_name,
        mime_type=mime_type,
        raw_bytes_b64=dummy_b64,
    )


# ---------------------------------------------------------------------------
# Document type routing
# ---------------------------------------------------------------------------

class TestDocumentTypeClassification:

    def test_claim_form(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "CLAIM_FORM", confidence=0.97, routing_hints=["contains_procedure_codes"]
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.document_type == DocumentType.CLAIM_FORM
        assert "contains_procedure_codes" in result.routing_hints

    def test_id_document(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "ID_DOCUMENT", confidence=0.92, routing_hints=["contains_photo", "has_barcode"]
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.document_type == DocumentType.ID_DOCUMENT

    def test_membership_card(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "MEMBERSHIP_CARD", confidence=0.88
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.document_type == DocumentType.MEMBERSHIP_CARD

    def test_medical_report(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "MEDICAL_REPORT", confidence=0.91, routing_hints=["contains_diagnosis_codes"]
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.document_type == DocumentType.MEDICAL_REPORT

    def test_prescription(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "PRESCRIPTION", confidence=0.89
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.document_type == DocumentType.PRESCRIPTION

    def test_policy_doc(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "POLICY_DOC", confidence=0.85
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.document_type == DocumentType.POLICY_DOC


# ---------------------------------------------------------------------------
# Confidence threshold handling
# ---------------------------------------------------------------------------

class TestConfidenceHandling:

    def test_low_confidence_overrides_type_to_unknown(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "CLAIM_FORM", confidence=0.3
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.document_type == DocumentType.UNKNOWN
        assert result.confidence == pytest.approx(0.3)

    def test_confidence_at_threshold_is_not_overridden(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "CLAIM_FORM", confidence=_LOW_CONFIDENCE_THRESHOLD
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.document_type == DocumentType.CLAIM_FORM

    def test_confidence_just_below_threshold_overrides_to_unknown(self, mock_client, dummy_b64):
        below = round(_LOW_CONFIDENCE_THRESHOLD - 0.01, 4)
        mock_client.chat.completions.create.return_value = make_tool_response(
            "CLAIM_FORM", confidence=below
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.document_type == DocumentType.UNKNOWN

    def test_model_returns_unknown_directly(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "UNKNOWN", confidence=0.6
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.document_type == DocumentType.UNKNOWN


# ---------------------------------------------------------------------------
# Output shape / Pydantic correctness
# ---------------------------------------------------------------------------

class TestOutputShape:

    def test_returns_classifier_output_model(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("CLAIM_FORM")
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert isinstance(result, ClassifierOutput)

    def test_page_count_is_int(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "CLAIM_FORM", page_count=3
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.page_count == 3
        assert isinstance(result.page_count, int)

    def test_is_handwritten_true(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "CLAIM_FORM", is_handwritten=True
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.is_handwritten is True

    def test_routing_hints_list_contents(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response(
            "CLAIM_FORM", routing_hints=["has_signature", "contains_procedure_codes"]
        )
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.routing_hints == ["has_signature", "contains_procedure_codes"]

    def test_empty_routing_hints(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("CLAIM_FORM")
        result = ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        assert result.routing_hints == []


# ---------------------------------------------------------------------------
# Content building (PDF vs image)
# ---------------------------------------------------------------------------

class TestContentBuilding:

    def _get_user_content(self, mock_client) -> list[dict]:
        # messages[0] = system, messages[1] = user
        return mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]

    def test_jpeg_uses_image_url_block(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("ID_DOCUMENT")
        ClassifierAgent(client=mock_client).run(
            _make_input(mime_type="image/jpeg", dummy_b64=dummy_b64)
        )
        content = self._get_user_content(mock_client)
        types = [b["type"] for b in content]
        assert "image_url" in types

    def test_jpeg_url_contains_base64_data(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("ID_DOCUMENT")
        ClassifierAgent(client=mock_client).run(
            _make_input(mime_type="image/jpeg", dummy_b64=dummy_b64)
        )
        content = self._get_user_content(mock_client)
        img_block = next(b for b in content if b["type"] == "image_url")
        assert "image/jpeg" in img_block["image_url"]["url"]
        assert dummy_b64 in img_block["image_url"]["url"]

    def test_png_uses_image_url_block(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("ID_DOCUMENT")
        ClassifierAgent(client=mock_client).run(
            _make_input(mime_type="image/png", file_name="id.png", dummy_b64=dummy_b64)
        )
        content = self._get_user_content(mock_client)
        types = [b["type"] for b in content]
        assert "image_url" in types

    def test_pdf_sends_text_only(self, mock_client, dummy_b64):
        # GPT-4o does not support PDF content blocks; text prompt only
        mock_client.chat.completions.create.return_value = make_tool_response("CLAIM_FORM")
        ClassifierAgent(client=mock_client).run(
            _make_input(mime_type="application/pdf", file_name="claim.pdf", dummy_b64=dummy_b64)
        )
        content = self._get_user_content(mock_client)
        types = [b["type"] for b in content]
        assert "image_url" not in types
        assert "text" in types

    def test_file_name_in_text_block(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("CLAIM_FORM")
        ClassifierAgent(client=mock_client).run(
            _make_input(
                mime_type="application/pdf",
                file_name="annual_claim_2024.pdf",
                dummy_b64=dummy_b64,
            )
        )
        content = self._get_user_content(mock_client)
        text_block = next(b for b in content if b["type"] == "text")
        assert "annual_claim_2024.pdf" in text_block["text"]


# ---------------------------------------------------------------------------
# API call parameters
# ---------------------------------------------------------------------------

class TestApiCallParameters:

    def test_tool_choice_forces_classify_document(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("CLAIM_FORM")
        ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["tool_choice"] == {
            "type": "function",
            "function": {"name": "classify_document"},
        }

    def test_uses_default_model(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("CLAIM_FORM")
        ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == _DEFAULT_MODEL

    def test_custom_model_override(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("CLAIM_FORM")
        ClassifierAgent(client=mock_client, model="gpt-4o-mini").run(
            _make_input(dummy_b64=dummy_b64)
        )
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "gpt-4o-mini"

    def test_calls_chat_completions_exactly_once(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("CLAIM_FORM")
        ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        mock_client.chat.completions.create.assert_called_once()

    def test_classify_document_tool_is_in_tools_list(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("CLAIM_FORM")
        ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        tool_names = [t["function"]["name"] for t in kwargs["tools"]]
        assert "classify_document" in tool_names

    def test_system_message_is_first(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.return_value = make_tool_response("CLAIM_FORM")
        ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["messages"][0]["role"] == "system"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_propagates_api_exception(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.side_effect = RuntimeError("upstream API error")
        with pytest.raises(RuntimeError, match="upstream API error"):
            ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))

    def test_propagates_connection_error(self, mock_client, dummy_b64):
        mock_client.chat.completions.create.side_effect = ConnectionError("timeout")
        with pytest.raises(ConnectionError):
            ClassifierAgent(client=mock_client).run(_make_input(dummy_b64=dummy_b64))
