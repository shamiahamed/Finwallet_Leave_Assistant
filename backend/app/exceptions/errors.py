# Application exceptions. Each API-facing error carries an HTTP status and a stable code.

from typing import Any


class AppError(Exception):
    # Base class for errors that are safe to show to API clients.

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class InvalidEmployeeIdError(AppError):
    status_code = 422
    code = "invalid_employee_id"


class EmployeeNotFoundError(AppError):
    status_code = 404
    code = "employee_not_found"


class AmbiguousEmployeeError(AppError):
    # Several employees match; the caller must pick one candidate.
    status_code = 409
    code = "ambiguous_employee"


class InvalidFilterError(AppError):
    status_code = 422
    code = "invalid_filter"


class DatasetNotFoundError(AppError):
    # Unknown or removed dataset selected for a query.
    status_code = 404
    code = "dataset_not_found"


class InvalidUploadError(AppError):
    # Uploaded file is unsupported, too large, malformed, or fails validation.
    status_code = 422
    code = "invalid_upload"


class DocumentNotFoundError(AppError):
    # Unknown or removed document selected for a retrieval question.
    status_code = 404
    code = "document_not_found"


class WorkbookError(Exception):
    pass
    # Workbook missing/unreadable/invalid. Raised at application startup; never sent to clients.
