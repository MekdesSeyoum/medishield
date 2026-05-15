from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import openai

from core.config import get_settings
from shared.schemas.agent_io import PolicyInput, PolicyOutput

if TYPE_CHECKING:
    pass  # chromadb.Collection imported lazily to keep module lightweight

_DEFAULT_MODEL = "gpt-4o"
_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "policy_chunks.json"
_COLLECTION_NAME = "policy_chunks"
_TOP_K = 3

_COVERAGE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "coverage_assessment",
        "description": (
            "Determine whether the given CPT codes are covered under MediShield's policy "
            "based on the retrieved policy clauses."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "covered": {
                    "type": "boolean",
                    "description": "True if the procedure(s) are covered by the policy.",
                },
                "coverage_percentage": {
                    "type": "number",
                    "description": "Coverage as a decimal 0.0–1.0 (e.g. 0.80 = 80%). Use 0.0 if not covered.",
                },
                "policy_clause": {
                    "type": "string",
                    "description": "Primary policy section or clause that determines coverage.",
                },
                "exclusions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Applicable exclusion clauses. Empty list if procedure is covered.",
                },
            },
            "required": ["covered", "coverage_percentage", "policy_clause", "exclusions"],
        },
    },
}

_SYSTEM_PROMPT = (
    "You are a MediShield policy compliance analyst. "
    "Using only the policy clauses provided, determine whether the given CPT codes "
    "are covered and at what percentage. "
    "Call coverage_assessment with your findings."
)


class PolicyAgent:
    def __init__(
        self,
        client: openai.OpenAI | None = None,
        model: str = _DEFAULT_MODEL,
        chroma_collection: Any | None = None,
    ) -> None:
        if client is not None:
            self._client = client
            self._model = model
        else:
            s = get_settings()
            self._client = openai.OpenAI(api_key=s.openai_api_key)
            self._model = s.openai_model

        self._collection = chroma_collection if chroma_collection is not None else self._make_collection()

    # ------------------------------------------------------------------
    # Collection setup
    # ------------------------------------------------------------------

    @staticmethod
    def _make_collection() -> Any:
        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.EphemeralClient()
        ef = embedding_functions.DefaultEmbeddingFunction()
        return client.get_or_create_collection(name=_COLLECTION_NAME, embedding_function=ef)

    def ingest_chunks(self, chunks: list[dict]) -> None:
        """Add pre-built chunks (id, text, metadata) to the ChromaDB collection."""
        self._collection.add(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[c.get("metadata", {}) for c in chunks],
        )

    def load_fixture(self) -> None:
        """Ingest the bundled sample policy JSON fixture into the collection."""
        with open(_FIXTURE_PATH) as f:
            self.ingest_chunks(json.load(f))

    def ingest_pdf(self, pdf_path: str) -> int:
        """Parse a policy PDF with Docling, chunk by section, and store in ChromaDB."""
        from docling.document_converter import DocumentConverter  # noqa: PLC0415

        converter = DocumentConverter()
        result = converter.convert(pdf_path)
        markdown = result.document.export_to_markdown()

        raw_chunks = [s.strip() for s in markdown.split("\n\n") if s.strip()]
        chunks = [
            {
                "id": f"pdf_chunk_{i}",
                "text": text,
                "metadata": {"source": pdf_path, "chunk_index": i},
            }
            for i, text in enumerate(raw_chunks)
        ]
        self.ingest_chunks(chunks)
        return len(chunks)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def run(self, input: PolicyInput) -> PolicyOutput:
        query = " ".join(input.cpt_codes)
        results = self._collection.query(query_texts=[query], n_results=_TOP_K)

        clauses: list[str] = results["documents"][0] if results["documents"] else []
        context = "\n\n---\n\n".join(
            f"[Clause {i + 1}]: {text}" for i, text in enumerate(clauses)
        )

        prompt = (
            f"CPT codes to assess: {', '.join(input.cpt_codes)}\n\n"
            f"Relevant policy clauses retrieved from the member policy:\n{context}"
        )

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=512,
            tools=[_COVERAGE_TOOL],
            tool_choice={"type": "function", "function": {"name": "coverage_assessment"}},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        tool_call = response.choices[0].message.tool_calls[0]
        raw = json.loads(tool_call.function.arguments)

        return PolicyOutput(
            covered=bool(raw["covered"]),
            coverage_percentage=float(raw["coverage_percentage"]),
            policy_clause=str(raw["policy_clause"]),
            exclusions=list(raw["exclusions"]),
        )


def policy_node(state: dict) -> dict:
    """LangGraph node: runs PolicyAgent and writes policy_result into graph state."""
    agent = PolicyAgent()
    agent.load_fixture()
    output = agent.run(
        PolicyInput(
            case_id=state["case_id"],
            cpt_codes=state["cpt_codes"],
        )
    )
    return {"policy_result": output.model_dump()}
