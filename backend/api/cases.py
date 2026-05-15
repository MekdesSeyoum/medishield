import io
from datetime import timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from minio import Minio

from api.deps import get_case_store, get_minio_client
from core.config import get_settings
from db.case_store import CaseStore
from shared.schemas.cases import (
    CaseRecord,
    CaseUploadResponse,
    DecisionOverrideRequest,
    PaginatedCasesResponse,
)
from storage.minio_client import ensure_bucket
from worker.tasks import process_document

router = APIRouter(prefix="/cases", tags=["cases"])

_ALLOWED_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "application/pdf", "image/tiff"}
)


@router.post(
    "/upload",
    response_model=CaseUploadResponse,
    status_code=201,
    summary="Upload a document to open a new case",
)
async def upload_case(
    file: Annotated[
        UploadFile,
        File(description="Insurance document — JPEG, PNG, PDF, or TIFF"),
    ],
    case_store: Annotated[CaseStore, Depends(get_case_store)],
    minio: Annotated[Minio, Depends(get_minio_client)],
) -> CaseUploadResponse:
    """Upload a document to create a new insurance case.

    - Accepts **JPEG**, **PNG**, **PDF**, and **TIFF** files.
    - Stores the raw file in MinIO under `<case_id>/<filename>`.
    - Creates a case record with status `PENDING`.
    - Enqueues a Celery job for async processing.

    Returns a `case_id` you can use to poll `GET /cases/{case_id}`.
    """
    if file.content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported media type '{file.content_type}'. "
                f"Accepted: {sorted(_ALLOWED_MIME_TYPES)}"
            ),
        )

    case_id = uuid4()
    file_name = file.filename or "document"
    s = get_settings()
    file_key = f"{case_id}/{file_name}"

    content = await file.read()

    ensure_bucket(minio, s.minio_bucket)
    minio.put_object(
        bucket_name=s.minio_bucket,
        object_name=file_key,
        data=io.BytesIO(content),
        length=len(content),
        content_type=file.content_type,
    )

    record = case_store.create(
        case_id=case_id,
        file_name=file_name,
        mime_type=file.content_type,
        file_key=file_key,
    )

    process_document.delay(str(case_id))

    return CaseUploadResponse(
        case_id=record.case_id,
        status=record.status,
        file_name=record.file_name,
        mime_type=record.mime_type,
        created_at=record.created_at,
    )


@router.get(
    "/",
    response_model=PaginatedCasesResponse,
    summary="List all cases (paginated)",
)
async def list_cases(
    case_store: Annotated[CaseStore, Depends(get_case_store)],
    page: Annotated[
        int, Query(ge=1, description="Page number — 1-indexed")
    ] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page (max 100)")
    ] = 20,
    status: Annotated[
        str | None,
        Query(description="Filter by status: PENDING, PROCESSING, APPROVED, DENIED, ESCALATED"),
    ] = None,
) -> PaginatedCasesResponse:
    """Return a paginated list of all cases, ordered newest-first.

    Use `status` to filter by case status.
    """
    items, total = case_store.list_paginated(page=page, page_size=page_size, status=status)
    return PaginatedCasesResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{case_id}/document-url",
    summary="Get a presigned URL to view the uploaded document",
)
async def get_document_url(
    case_id: UUID,
    case_store: Annotated[CaseStore, Depends(get_case_store)],
    minio: Annotated[Minio, Depends(get_minio_client)],
) -> dict:
    """Return a 1-hour presigned MinIO URL for the raw document file."""
    record = case_store.get(case_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")
    s = get_settings()
    url = minio.presigned_get_object(
        bucket_name=s.minio_bucket,
        object_name=record.file_key,
        expires=timedelta(hours=1),
    )
    return {"url": url, "mime_type": record.mime_type}


@router.patch(
    "/{case_id}/decision",
    response_model=CaseRecord,
    summary="Manually override the case decision (review queue)",
)
async def override_decision(
    case_id: UUID,
    body: DecisionOverrideRequest,
    case_store: Annotated[CaseStore, Depends(get_case_store)],
) -> CaseRecord:
    """Override the pipeline's decision for an escalated case.

    Sets the case status to **APPROVED** or **DENIED** and appends a
    manual-override entry to the audit log.
    """
    record = case_store.get(case_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")
    updated = case_store.override_decision(
        case_id=case_id,
        decision=body.decision,
        reason=body.reason,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")
    return updated


@router.get(
    "/{case_id}",
    response_model=CaseRecord,
    summary="Get case status and metadata",
)
async def get_case(
    case_id: UUID,
    case_store: Annotated[CaseStore, Depends(get_case_store)],
) -> CaseRecord:
    """Retrieve the current status and metadata for a specific case.

    Returns `404` if the `case_id` does not exist.
    """
    record = case_store.get(case_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")
    return record
