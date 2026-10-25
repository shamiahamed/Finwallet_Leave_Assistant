"""Lazy, safe refresh of the configured workbook.

Keeps the last valid snapshot available at all times. A changed workbook is
loaded and validated into a candidate repository first, and only published
atomically once every check passes. Refreshes are serialized so concurrent
queries can never observe a half-built snapshot.
"""

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.exceptions.errors import WorkbookError
from app.repositories.workbook_repository import WorkbookRepository, file_fingerprint

logger = logging.getLogger(__name__)


class WorkbookRefreshService:
    """Owns the current workbook snapshot and refreshes it when the file changes."""

    def __init__(self, path: Path, repository: WorkbookRepository, enabled: bool = True) -> None:
        self._path = path
        self._repository = repository
        self._enabled = enabled
        self._lock = threading.Lock()
        self._last_result = "startup"
        self._last_error: str | None = None
        self._last_refresh_at = datetime.now(timezone.utc)

    @property
    def current(self) -> WorkbookRepository:
        return self._repository

    def maybe_refresh(self) -> WorkbookRepository:
        """Reload the workbook if the file changed; otherwise return the current one.

        Never raises: a failed refresh keeps the last valid snapshot and records
        the failure category for /health and logs.
        """
        if not self._enabled:
            return self._repository
        # Reload the workbook only when its file fingerprint changes.
        if file_fingerprint(self._path) == self._repository.fingerprint:
            return self._repository

        with self._lock:
            # Another request may have refreshed while we waited for the lock.
            if file_fingerprint(self._path) == self._repository.fingerprint:
                return self._repository
            return self._reload_locked()

    def _reload_locked(self) -> WorkbookRepository:
        try:
            candidate = WorkbookRepository.load(self._path)
        except WorkbookError as exc:
            # Keep the last valid dataset available if the new workbook fails validation.
            self._record("failed", "validation", str(exc))
            logger.warning("Workbook refresh rejected; keeping last valid snapshot: %s", exc)
            return self._repository
        except Exception as exc:  # unexpected: still keep the last valid snapshot
            self._record("failed", "unexpected", str(exc))
            logger.exception("Workbook refresh failed unexpectedly; keeping last valid snapshot.")
            return self._repository

        # Atomic publish: a single attribute assignment. In-flight requests keep
        # the old repository object; new requests see the new one.
        self._repository = candidate
        self._record("reloaded", None, None)
        logger.info("Workbook refreshed from disk: %s", candidate.row_counts)
        return candidate

    def _record(self, result: str, error_category: str | None, message: str | None) -> None:
        self._last_result = result
        self._last_error = None if error_category is None else f"{error_category}: {message}"
        self._last_refresh_at = datetime.now(timezone.utc)

    @property
    def status(self) -> dict:
        # Report the latest refresh result without exposing internal file details.
        return {
            "last_result": self._last_result,
            "last_refresh_at": self._last_refresh_at.isoformat(),
            "last_error": self._last_error,
        }
