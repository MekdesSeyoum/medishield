import base64
import json
from pathlib import Path

import openai

from core.config import get_settings
from shared.schemas.agent_io import KYCInput, KYCOutput

_DEFAULT_MODEL = "gpt-4o"
_MEMBERS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "members.json"

_KYC_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "kyc_assessment",
        "description": (
            "Analyse a health insurance document and return a structured KYC assessment. "
            "Extract any visible member identifiers and flag expiry or tampering."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "member_id_extracted": {
                    "type": "string",
                    "description": "Member ID found in the document. Empty string if absent.",
                },
                "dob_extracted": {
                    "type": "string",
                    "description": "Date of birth extracted (YYYY-MM-DD). Empty string if absent.",
                },
                "policy_number_extracted": {
                    "type": "string",
                    "description": "Policy number extracted from document. Empty string if absent.",
                },
                "document_expired": {
                    "type": "boolean",
                    "description": (
                        "True if the document itself (ID card / membership card) "
                        "is past its printed expiry date."
                    ),
                },
                "visual_anomalies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Descriptions of visual signs of tampering or forgery "
                        "(e.g. 'mismatched fonts', 'pixelation around photo'). "
                        "Empty array if none detected."
                    ),
                },
                "confidence": {
                    "type": "number",
                    "description": "Overall confidence in the assessment, 0.0–1.0.",
                },
            },
            "required": [
                "member_id_extracted",
                "dob_extracted",
                "policy_number_extracted",
                "document_expired",
                "visual_anomalies",
                "confidence",
            ],
        },
    },
}

_SYSTEM_PROMPT = (
    "You are a KYC analyst for MediShield, a health insurance company. "
    "Analyse the document text (and image if provided) to extract member identifiers "
    "and detect any signs of expiry or tampering. "
    "Call kyc_assessment with your findings."
)


class KYCAgent:
    def __init__(
        self,
        client: openai.OpenAI | None = None,
        model: str = _DEFAULT_MODEL,
        members_fixture: list[dict] | None = None,
    ) -> None:
        if client is not None:
            self._client = client
            self._model = model
        else:
            s = get_settings()
            self._client = openai.OpenAI(api_key=s.openai_api_key)
            self._model = s.openai_model

        if members_fixture is not None:
            self._members = members_fixture
        else:
            with open(_MEMBERS_FIXTURE) as f:
                self._members: list[dict] = json.load(f)["members"]

    def run(self, input: KYCInput) -> KYCOutput:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=512,
            tools=[_KYC_TOOL],
            tool_choice={"type": "function", "function": {"name": "kyc_assessment"}},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": self._build_content(input)},
            ],
        )

        tool_call = response.choices[0].message.tool_calls[0]
        raw = json.loads(tool_call.function.arguments)

        flags: list[str] = list(raw["visual_anomalies"])

        if raw["document_expired"]:
            flags.append("DOCUMENT_EXPIRED")

        member_id = raw["member_id_extracted"].strip()
        policy_number = raw["policy_number_extracted"].strip()
        if member_id or policy_number:
            member = self._lookup_member(
                member_id=member_id,
                policy_number=policy_number,
            )
            if member is None:
                flags.append("MEMBER_NOT_FOUND")

        return KYCOutput(
            kyc_passed=len(flags) == 0,
            flags=flags,
            confidence=float(raw["confidence"]),
        )

    def _lookup_member(
        self, member_id: str, policy_number: str
    ) -> dict | None:
        for m in self._members:
            if (
                m["member_id"] == member_id
                and m["policy_number"] == policy_number
            ):
                return m
        return None

    def _build_content(self, input: KYCInput) -> list[dict]:
        label: dict = {
            "type": "text",
            "text": (
                f"Document type: {input.doc_type.value}\n\n"
                f"Extracted text:\n{input.extracted_text}"
            ),
        }
        if input.image_bytes is not None:
            b64 = base64.b64encode(input.image_bytes).decode()
            return [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                },
                label,
            ]
        return [label]


def kyc_node(state: dict) -> dict:
    """LangGraph node: runs KYCAgent and writes kyc_result into graph state."""
    agent = KYCAgent()
    output = agent.run(
        KYCInput(
            case_id=state["case_id"],
            doc_type=state["doc_type"],
            extracted_text=state["extracted_text"],
            image_bytes=state.get("image_bytes"),
        )
    )
    return {"kyc_result": output.model_dump()}
