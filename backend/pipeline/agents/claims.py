import json
import re
from datetime import date as DateType

import openai
from pydantic import BaseModel, Field, ValidationError, field_validator

from core.config import get_settings
from shared.schemas.agent_io import ClaimsInput, ClaimsOutput

_DEFAULT_MODEL = "gpt-4o"

# ---------------------------------------------------------------------------
# MediShield claim schema — also exported so tests can import it directly
# ---------------------------------------------------------------------------

_ICD10_RE = re.compile(r"^[A-Z]\d{2}(\.\w{1,4})?$")
_CPT_RE = re.compile(r"^\d{5}[A-Z0-9]?$")


class ClaimSchema(BaseModel):
    """Pydantic model representing a valid MediShield insurance claim."""

    claim_amount: float = Field(gt=0, description="Claim amount in USD, must be > 0")
    icd10_codes: list[str] = Field(min_length=1, description="At least one ICD-10 code required")
    cpt_codes: list[str] = Field(min_length=1, description="At least one CPT code required")
    provider_npi: str = Field(description="National Provider Identifier")
    service_date: str = Field(description="Service date as YYYY-MM-DD")

    @field_validator("icd10_codes", mode="before")
    @classmethod
    def validate_icd10(cls, v: list) -> list:
        for code in v:
            if not _ICD10_RE.match(str(code).upper()):
                raise ValueError(f"Invalid ICD-10 code: {code!r}")
        return v

    @field_validator("cpt_codes", mode="before")
    @classmethod
    def validate_cpt(cls, v: list) -> list:
        for code in v:
            if not _CPT_RE.match(str(code)):
                raise ValueError(f"Invalid CPT code: {code!r}")
        return v

    @field_validator("provider_npi")
    @classmethod
    def validate_npi(cls, v: str) -> str:
        if not re.match(r"^\d{10}$", v):
            raise ValueError(f"NPI must be exactly 10 digits, got: {v!r}")
        return v

    @field_validator("service_date")
    @classmethod
    def validate_service_date(cls, v: str) -> str:
        if v:
            DateType.fromisoformat(v)
        return v


# ---------------------------------------------------------------------------
# LLM tool definition
# ---------------------------------------------------------------------------

_EXTRACT_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "extract_claim_fields",
        "description": "Extract structured billing fields from insurance claim document text.",
        "parameters": {
            "type": "object",
            "properties": {
                "claim_amount": {
                    "type": "number",
                    "description": "Total claim amount in USD. Use 0 if not found.",
                },
                "icd10_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "ICD-10 diagnosis codes (e.g. 'J18.9'). Empty array if none found.",
                },
                "cpt_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "CPT procedure codes (5-digit). Empty array if none found.",
                },
                "provider_npi": {
                    "type": "string",
                    "description": "Provider NPI (10-digit number). Empty string if not found.",
                },
                "service_date": {
                    "type": "string",
                    "description": "Date of service as YYYY-MM-DD. Empty string if not found.",
                },
            },
            "required": ["claim_amount", "icd10_codes", "cpt_codes", "provider_npi", "service_date"],
        },
    },
}

_SYSTEM_PROMPT = (
    "You are a medical claims processor for MediShield. "
    "Extract structured billing fields from the provided claim document. "
    "Call extract_claim_fields with every field you can identify."
)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ClaimsAgent:
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

    def run(self, input: ClaimsInput) -> ClaimsOutput:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=512,
            tools=[_EXTRACT_TOOL],
            tool_choice={"type": "function", "function": {"name": "extract_claim_fields"}},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": self._build_content(input)},
            ],
        )

        tool_call = response.choices[0].message.tool_calls[0]
        extracted: dict = json.loads(tool_call.function.arguments)
        schema_valid, errors = self._validate(extracted)

        return ClaimsOutput(
            extracted_fields=extracted,
            schema_valid=schema_valid,
            validation_errors=errors,
        )

    @staticmethod
    def _build_content(input: ClaimsInput) -> str | list:
        text_parts = ["Extract all billing fields from this claim document."]
        if input.extracted_text:
            text_parts.append(f"Document text:\n{input.extracted_text}")
        if input.raw_fields:
            raw_str = "\n".join(f"  {k}: {v}" for k, v in input.raw_fields.items())
            text_parts.append(f"Pre-extracted raw fields:\n{raw_str}")
        text_block = {"type": "text", "text": "\n\n".join(text_parts)}

        if input.raw_bytes_b64 and input.mime_type in ("image/jpeg", "image/png"):
            return [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{input.mime_type};base64,{input.raw_bytes_b64}"},
                },
                text_block,
            ]
        return text_block["text"]

    @staticmethod
    def _validate(extracted: dict) -> tuple[bool, list[str]]:
        try:
            ClaimSchema.model_validate(extracted)
            return True, []
        except ValidationError as exc:
            errors = []
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"])
                errors.append(f"{loc}: {err['msg']}")
            return False, errors


def claims_node(state: dict) -> dict:
    """LangGraph node: runs ClaimsAgent and writes claims_result into graph state."""
    agent = ClaimsAgent()
    output = agent.run(
        ClaimsInput(
            case_id=state["case_id"],
            extracted_text=state["extracted_text"],
            raw_fields=state.get("raw_fields", {}),
        )
    )
    return {"claims_result": output.model_dump()}
