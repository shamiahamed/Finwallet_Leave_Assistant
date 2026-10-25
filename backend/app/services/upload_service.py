"""Validation and safe storage for uploaded Excel/CSV datasets.

Content is parsed and validated; the filename and MIME type are never trusted.
Uploads are stored under a server-generated name in the configured upload
directory and are only queryable once the known schema validates.
"""

import logging
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
from uuid import uuid4

import pandas as pd

from app.core.config import Settings
from app.exceptions.errors import InvalidUploadError
from app.repositories.workbook_repository import (
    REQUIRED_COLUMNS,
    WorkbookRepository,
)
from app.schemas.dataset import DatasetPreview

logger = logging.getLogger(__name__)

XLSX_EXTENSIONS = {".xlsx"}
CSV_EXTENSIONS = {".csv"}
ALLOWED_EXTENSIONS = XLSX_EXTENSIONS | CSV_EXTENSIONS

# Magic bytes for the supported container formats.
_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _has_supported_signature(data: bytes, extension: str) -> bool:
    if extension in XLSX_EXTENSIONS:
        # Plain OLE2 magic indicates a legacy/macro format (.xls/.xlsm-family),
        # which is not supported; only the zip-based .xlsx container is.
        if data[:8] == _OLE_MAGIC:
            return False
        return data[:4] == _ZIP_MAGIC
    if extension == ".csv":
        # CSV is plain text; reject binary-looking content early.
        sample = data[:4096]
        return b"\x00" not in sample
    return False


def _read_xlsx(data: bytes) -> dict[str, pd.DataFrame]:
    # .xlsm (macro-enabled) is accepted for reading only; macros are never run.
    return pd.read_excel(BytesIO(data), sheet_name=None, dtype=str, engine="openpyxl")


def _read_csv(data: bytes) -> dict[str, pd.DataFrame]:
    text = data.decode("utf-8-sig", errors="strict")
    # A single CSV is surfaced as the Employees sheet name only if the known
    # schema columns are present; otherwise it is treated as an unknown schema.
    frame = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
    return {"__csv__": frame}


def sniff_schema_kind(raw: dict[str, pd.DataFrame]) -> tuple[str, list[str]]:
    """Return ('known'|'unknown', warnings) for parsed sheets."""
    warnings: list[str] = []
    present = set(raw.keys())

    if "__csv__" in raw:
        frame = raw["__csv__"]
        return "unknown", [
            "CSV columns were inspected but not mapped to the known leave schema. "
            "Upload an .xlsx workbook with the known worksheets to query employees "
            "and leave data."
        ]

    known_sheets = [name for name in REQUIRED_COLUMNS if name in present]
    if not known_sheets:
        return "unknown", [
            "No known worksheets found. Expected: " + ", ".join(REQUIRED_COLUMNS) + "."
        ]

    missing = [name for name in REQUIRED_COLUMNS if name not in present]
    if missing:
        warnings.append("Missing worksheet(s) for the known schema: " + ", ".join(missing))
        return "unknown", warnings

    for name, required in REQUIRED_COLUMNS.items():
        absent_cols = [c for c in required if c not in raw[name].columns]
        if absent_cols:
            warnings.append(f"Sheet '{name}' is missing column(s): {', '.join(absent_cols)}")
    return ("unknown" if warnings else "known"), warnings


def build_preview(raw: dict[str, pd.DataFrame], dataset_id: str, sample: int = 5) -> DatasetPreview:
    # Use the first sheet (or the CSV frame) for a compact preview.
    if "__csv__" in raw:
        frame = raw["__csv__"]
    else:
        first = next(iter(raw))
        frame = raw[first]

    columns = [str(c) for c in frame.columns]
    sample_rows = frame.head(sample).fillna("").astype(str).to_dict(orient="records")
    kind, warnings = sniff_schema_kind(raw)
    return DatasetPreview(
        dataset_id=dataset_id,
        columns=columns,
        sample_rows=sample_rows,
        row_count=int(len(frame)),
        column_count=int(frame.shape[1]),
        validation_status="valid" if kind == "known" else "invalid",
        warnings=warnings,
    )


def validate_and_store(
    filename: str,
    data: bytes,
    settings: Settings,
) -> tuple[Path, str, dict[str, pd.DataFrame], DatasetPreview]:
    """Validate an upload and persist it. Returns (stored_path, schema_kind, raw_sheets, preview)."""
    # Validate uploaded data before making it available to chat queries.
    if not data:
        raise InvalidUploadError("The uploaded file is empty.")

    max_bytes = int(settings.max_upload_mb * 1024 * 1024)
    if len(data) > max_bytes:
        raise InvalidUploadError(
            f"The uploaded file exceeds the {settings.max_upload_mb:g} MB limit."
        )

    # Accept only supported file formats and enforce the configured size limit.
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise InvalidUploadError(
            "Unsupported file type. Allowed: " + ", ".join(sorted(ALLOWED_EXTENSIONS)) + "."
        )

    if not _has_supported_signature(data, extension):
        raise InvalidUploadError("The file content does not match its declared type.")

    try:
        if extension in XLSX_EXTENSIONS:
            raw = _read_xlsx(data)
        else:
            raw = _read_csv(data)
    except InvalidUploadError:
        raise
    except Exception as exc:
        # Log the detail server-side; never echo parser output (which may
        # include local paths or file content) back to the client.
        logger.warning("Upload parse failed: %s", type(exc).__name__)
        raise InvalidUploadError(
            "The file could not be parsed as a valid spreadsheet."
        ) from exc

    if not raw:
        raise InvalidUploadError("The file contains no readable data.")

    # Enforce row/column limits across every sheet.
    total_rows = 0
    for name, frame in raw.items():
        if frame.shape[1] > settings.max_upload_columns:
            raise InvalidUploadError(
                f"Sheet '{name}' has {frame.shape[1]} columns, exceeding the "
                f"{settings.max_upload_columns} column limit."
            )
        total_rows += len(frame)
    if total_rows > settings.max_upload_rows:
        raise InvalidUploadError(
            f"The file has {total_rows} rows, exceeding the {settings.max_upload_rows} row limit."
        )

    # Known schema must validate exactly like the configured workbook.
    kind, warnings = sniff_schema_kind(raw)
    if kind == "known":
        try:
            WorkbookRepository.from_raw_sheets(raw)
        except Exception as exc:
            raise InvalidUploadError(f"The dataset failed validation: {exc}") from exc

    dataset_id = uuid4().hex
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    # Server-generated storage name; the client filename is never used as a path.
    stored = settings.upload_dir / f"{dataset_id}{extension}"
    stored.write_bytes(data)

    preview = build_preview(raw, dataset_id)
    logger.info(
        "Uploaded dataset %s (%s, %d rows total, schema=%s).",
        dataset_id,
        extension,
        total_rows,
        kind,
    )
    return stored, kind, raw, preview
