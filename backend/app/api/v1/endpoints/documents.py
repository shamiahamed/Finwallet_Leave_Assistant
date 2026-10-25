
"""Document upload, listing, and deletion for RAG answers.

Documents are kept separate from structured employee and leave datasets.
Monitoring events contain metadata only, never document contents.
"""

import logging

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.core.config import get_settings
from app.schemas.document import (
    DocumentListResponse,
    DocumentSummary,
    DocumentUploadResponse,
)
from app.services.document_registry import DocumentRegistry
from app.services.document_service import ingest_document

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Documents"])


def _registry(request: Request) -> DocumentRegistry:
    return request.app.state.document_registry


def _record_monitoring_event(
    request: Request,
    event_type: str,
    severity: str,
    message: str,
) -> None:
    """Record an event without allowing monitoring failures to break an API."""
    monitoring = getattr(request.app.state, "monitoring", None)

    if monitoring is None:
        return

    try:
        monitoring.record_event(
            event_type=event_type,
            severity=severity,
            message=message,
        )
    except Exception:
        logger.exception("Could not record document monitoring event.")


def _summary(document) -> DocumentSummary:
    return DocumentSummary(
        document_id=document.document_id,
        name=document.name,
        source=document.source,
        page_count=document.page_count,
        chunk_count=len(document.chunks),
        size_bytes=document.size_bytes,
        created_at=document.created_at,
    )


@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    summary="Upload a PDF or text document for retrieval",
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    settings = get_settings()

    try:
        data = await file.read()

        document = ingest_document(
            file.filename or "",
            data,
            settings,
        )

        _registry(request).add(document)

    except HTTPException:
        _record_monitoring_event(
            request,
            "document.upload.failed",
            "medium",
            "Document upload was rejected.",
        )
        raise

    except Exception:
        logger.exception("Document upload or ingestion failed.")

        _record_monitoring_event(
            request,
            "document.upload.failed",
            "medium",
            "Document ingestion failed. Check backend logs.",
        )

        raise

    finally:
        await file.close()

    _record_monitoring_event(
        request,
        "document.upload.succeeded",
        "info",
        "A document was ingested successfully.",
    )

    logger.info("Document ingested successfully.")

    return DocumentUploadResponse(document=_summary(document))


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List uploaded documents",
)
def list_documents(request: Request) -> DocumentListResponse:
    registry = _registry(request)

    return DocumentListResponse(
        documents=[_summary(document) for document in registry.list_all()]
    )


@router.delete(
    "/documents/{document_id}",
    summary="Remove an uploaded document",
)
def delete_document(
    request: Request,
    document_id: str,
) -> dict:
    try:
        _registry(request).remove(document_id)

    except Exception as exc:
        from app.exceptions.errors import DocumentNotFoundError

        if isinstance(exc, DocumentNotFoundError):
            raise HTTPException(
                status_code=404,
                detail="Document not found.",
            ) from exc

        raise

    _record_monitoring_event(
        request,
        "document.deleted",
        "info",
        "An uploaded document was removed.",
    )

    logger.info("Uploaded document removed.")

    return {"status": "ok", "removed": document_id}
