import base64
import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def dummy_b64() -> str:
    return base64.b64encode(b"fake document bytes for testing").decode()


def make_tool_response(
    document_type: str,
    confidence: float = 0.95,
    page_count: int = 1,
    is_handwritten: bool = False,
    routing_hints: list[str] | None = None,
) -> MagicMock:
    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps({
        "document_type": document_type,
        "confidence": confidence,
        "page_count": page_count,
        "is_handwritten": is_handwritten,
        "routing_hints": routing_hints or [],
    })
    message = MagicMock()
    message.tool_calls = [tool_call]
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response
