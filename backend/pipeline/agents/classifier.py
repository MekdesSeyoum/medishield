import json

import openai

from core.config import get_settings
from shared.enums import DocumentType
from shared.schemas.agent_io import ClassifierInput, ClassifierOutput

_DEFAULT_MODEL = "gpt-4o"
_LOW_CONFIDENCE_THRESHOLD = 0.5

_CLASSIFY_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "classify_document",
        "description": "Return a structured classification of the submitted health insurance document.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_type": {
                    "type": "string",
                    "enum": [t.value for t in DocumentType],
                    "description": "The category of the document.",
                },
                "confidence": {
                    "type": "number",
                    "description": "Classification confidence from 0.0 to 1.0.",
                },
                "page_count": {
                    "type": "integer",
                    "description": "Estimated number of pages in the document.",
                },
                "is_handwritten": {
                    "type": "boolean",
                    "description": "True if the document contains significant handwritten content.",
                },
                "routing_hints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Notable document features to inform downstream agents.",
                },
            },
            "required": [
                "document_type",
                "confidence",
                "page_count",
                "is_handwritten",
                "routing_hints",
            ],
        },
    },
}

_SYSTEM_PROMPT = (
    "You are a document classifier for MediShield, a health insurance company. "
    "Analyse the provided document and call classify_document with your findings. "
    "If the document type is unclear or does not match a known category, set "
    "document_type to UNKNOWN and confidence below 0.5."
)


class ClassifierAgent:
    def __init__(
        self,
        client: openai.OpenAI | None = None,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        if client is not None:
            self._client = client
            self._model = model
        else:
            s = get_settings()
            self._client = openai.OpenAI(api_key=s.openai_api_key)
            self._model = s.openai_model

    def run(self, input: ClassifierInput) -> ClassifierOutput:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=512,
            tools=[_CLASSIFY_TOOL],
            tool_choice={"type": "function", "function": {"name": "classify_document"}},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": self._build_content(input)},
            ],
        )

        tool_call = response.choices[0].message.tool_calls[0]
        raw = json.loads(tool_call.function.arguments)

        confidence = float(raw["confidence"])
        doc_type = DocumentType(raw["document_type"])
        if confidence < _LOW_CONFIDENCE_THRESHOLD:
            doc_type = DocumentType.UNKNOWN

        return ClassifierOutput(
            document_type=doc_type,
            confidence=confidence,
            page_count=int(raw["page_count"]),
            is_handwritten=bool(raw["is_handwritten"]),
            routing_hints=list(raw["routing_hints"]),
        )

    def _build_content(self, input: ClassifierInput) -> list[dict]:
        label: dict = {
            "type": "text",
            "text": (
                f"Classify this document.\n"
                f"File name: {input.file_name}\n"
                f"MIME type: {input.mime_type}"
            ),
        }
        # GPT-4o supports JPEG and PNG as base64 image_url; PDF/TIFF are text-only
        if input.mime_type in ("image/jpeg", "image/png"):
            return [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{input.mime_type};base64,{input.raw_bytes_b64}"
                    },
                },
                label,
            ]
        return [label]
