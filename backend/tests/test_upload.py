"""Smoke tests for POST /cases/upload and the case status endpoints."""

import io
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from api.deps import get_case_store, get_minio_client
from main import app
from shared.enums import CaseStatus
from shared.schemas.cases import CaseRecord

# ---------------------------------------------------------------------------
# Minimal valid-ish PNG header bytes (content is not validated server-side)
# ---------------------------------------------------------------------------
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _make_record(
    file_name: str = "sample.png",
    mime_type: str = "image/png",
) -> CaseRecord:
    cid = uuid4()
    now = datetime.now(tz=timezone.utc)
    return CaseRecord(
        case_id=cid,
        status=CaseStatus.PENDING,
        file_name=file_name,
        mime_type=mime_type,
        file_key=f"{cid}/{file_name}",
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_minio() -> MagicMock:
    m = MagicMock()
    m.bucket_exists.return_value = True
    return m


@pytest.fixture()
def mock_store() -> MagicMock:
    record = _make_record()
    m = MagicMock()
    m.create.return_value = record
    m.get.return_value = record
    m.list_paginated.return_value = ([record], 1)
    return m


@pytest.fixture()
def client(mock_minio: MagicMock, mock_store: MagicMock) -> TestClient:
    app.dependency_overrides[get_minio_client] = lambda: mock_minio
    app.dependency_overrides[get_case_store] = lambda: mock_store
    try:
        with patch("api.cases.process_document") as mock_task:
            mock_task.delay.return_value = MagicMock()
            yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests — upload endpoint
# ---------------------------------------------------------------------------


def test_upload_png_returns_201_with_case_id(client: TestClient) -> None:
    """A valid PNG upload must return HTTP 201 and a UUID case_id."""
    response = client.post(
        "/cases/upload",
        files={"file": ("sample.png", io.BytesIO(_PNG_BYTES), "image/png")},
    )

    assert response.status_code == 201
    body = response.json()
    assert "case_id" in body
    assert body["status"] == CaseStatus.PENDING
    assert body["mime_type"] == "image/png"
    assert body["file_name"] == "sample.png"


def test_upload_pdf_is_accepted(client: TestClient, mock_store: MagicMock) -> None:
    """PDF files must also be accepted."""
    mock_store.create.return_value = _make_record("report.pdf", "application/pdf")

    response = client.post(
        "/cases/upload",
        files={"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json()["mime_type"] == "application/pdf"


def test_upload_invalid_mime_returns_415(client: TestClient) -> None:
    """Plain-text uploads must be rejected with HTTP 415."""
    response = client.post(
        "/cases/upload",
        files={"file": ("doc.txt", io.BytesIO(b"hello"), "text/plain")},
    )

    assert response.status_code == 415
    assert "text/plain" in response.json()["detail"]


def test_upload_stores_file_in_minio(
    client: TestClient, mock_minio: MagicMock
) -> None:
    """put_object must be called exactly once per upload."""
    client.post(
        "/cases/upload",
        files={"file": ("sample.png", io.BytesIO(_PNG_BYTES), "image/png")},
    )

    mock_minio.put_object.assert_called_once()


def test_upload_enqueues_celery_task(
    mock_minio: MagicMock, mock_store: MagicMock
) -> None:
    """process_document.delay must be called with the new case_id."""
    app.dependency_overrides[get_minio_client] = lambda: mock_minio
    app.dependency_overrides[get_case_store] = lambda: mock_store
    try:
        with patch("api.cases.process_document") as mock_task:
            mock_task.delay.return_value = MagicMock()
            tc = TestClient(app)
            tc.post(
                "/cases/upload",
                files={"file": ("sample.png", io.BytesIO(_PNG_BYTES), "image/png")},
            )
            mock_task.delay.assert_called_once()
            call_arg = mock_task.delay.call_args[0][0]
            # The route generates a fresh UUID — just confirm a valid UUID was passed
            UUID(call_arg)  # raises ValueError if not a valid UUID string
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests — status and list endpoints
# ---------------------------------------------------------------------------


def test_get_case_returns_record(client: TestClient, mock_store: MagicMock) -> None:
    """GET /cases/{case_id} must return the stored record."""
    cid = mock_store.get.return_value.case_id

    response = client.get(f"/cases/{cid}")

    assert response.status_code == 200
    assert response.json()["case_id"] == str(cid)


def test_get_case_unknown_id_returns_404(
    client: TestClient, mock_store: MagicMock
) -> None:
    """GET /cases/{case_id} must return 404 for unknown IDs."""
    mock_store.get.return_value = None

    response = client.get(f"/cases/{uuid4()}")

    assert response.status_code == 404


def test_list_cases_returns_paginated_response(client: TestClient) -> None:
    """GET /cases/ must return items, total, page, and page_size."""
    response = client.get("/cases/?page=1&page_size=10")

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert body["total"] == 1
    assert len(body["items"]) == 1
