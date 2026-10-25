"""Dataset upload, listing, preview, and deletion.

All endpoints operate on the in-memory registry. Uploads are validated and
stored under a server-generated name; the client filename is never trusted.
This feature is intended for the trusted local/development environment and does
not guarantee isolation between different users.
"""

import logging

from fastapi import APIRouter, File, Request, UploadFile

from app.core.config import get_settings
from app.exceptions.errors import DatasetNotFoundError, InvalidUploadError
from app.repositories.workbook_repository import WorkbookRepository
from app.schemas.dataset import DatasetListResponse, DatasetPreview, UploadResponse
from app.services.dataset_registry import DatasetRegistry
from app.services.upload_service import build_preview, validate_and_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Datasets"])


def _registry(request: Request) -> DatasetRegistry:
    return request.app.state.dataset_registry


@router.post(
    "/datasets/upload",
    response_model=UploadResponse,
    summary="Upload an Excel/CSV dataset",
)
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
) -> UploadResponse:
    settings = get_settings()
    data = await file.read()

    stored, kind, raw, preview = validate_and_store(file.filename or "", data, settings)

    # Only known-schema uploads become queryable; unknown ones are registered
    # as invalid so they are visible but cannot serve queries.
    repository: WorkbookRepository | None = None
    if kind == "known":
        repository = WorkbookRepository.from_raw_sheets(raw)

    warnings = preview.warnings
    registry = _registry(request)
    dataset = registry.register(
        dataset_id=preview.dataset_id,
        name=(file.filename or "uploaded dataset"),
        schema_kind=kind,
        repository=repository,
        storage_path=stored,
        size_bytes=len(data),
        warnings=warnings,
        preview=preview,
    )
    return UploadResponse(dataset=dataset.summary(), preview=preview)


@router.get(
    "/datasets",
    response_model=DatasetListResponse,
    summary="List available datasets",
)
def list_datasets(request: Request) -> DatasetListResponse:
    registry = _registry(request)
    return DatasetListResponse(
        datasets=[d.summary() for d in registry.list_all()],
        default_dataset_id=registry.default_dataset_id,
    )


@router.get(
    "/datasets/{dataset_id}/preview",
    response_model=DatasetPreview,
    summary="Preview a dataset",
)
def preview_dataset(request: Request, dataset_id: str) -> DatasetPreview:
    dataset = _registry(request).get(dataset_id)
    if dataset.preview is not None:
        return dataset.preview
    # Default dataset preview is built from its repository on demand.
    if dataset.repository is None:
        raise DatasetNotFoundError(f"No dataset found with ID '{dataset_id}'.")

    raw = {
        "Employees": dataset.repository.employees,
        "Leave Requests": dataset.repository.leave_requests,
        "Leave Balances": dataset.repository.leave_balances,
        "Leave Policy": dataset.repository.leave_policy,
    }
    return build_preview(raw, dataset.dataset_id)


@router.delete(
    "/datasets/{dataset_id}",
    summary="Remove an uploaded dataset",
)
def delete_dataset(request: Request, dataset_id: str) -> dict:
    _registry(request).remove(dataset_id)
    return {"status": "ok", "removed": dataset_id}
