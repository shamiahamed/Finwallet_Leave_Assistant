"""In-memory registry of queryable datasets.

Always contains the configured workbook as the 'default' dataset. Uploaded
datasets are registered only after validation. Selection is per-request via an
optional dataset id, so there is no shared 'active dataset' state that could
leak between clients.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.exceptions.errors import DatasetNotFoundError, InvalidUploadError
from app.repositories.workbook_repository import WorkbookRepository
from app.schemas.dataset import DatasetPreview, DatasetSummary

logger = logging.getLogger(__name__)

DEFAULT_DATASET_ID = "default"

# Dataset ids are server-generated hex or the literal "default". This format
# check is defense-in-depth: a crafted id (path-like, traversal, or odd chars)
# can never be treated as a key or a filesystem path.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass
class Dataset:
    dataset_id: str
    name: str
    source: str  # "default" | "upload"
    schema_kind: str  # "known" | "unknown"
    repository: WorkbookRepository | None
    created_at: str
    storage_path: Path | None = None
    size_bytes: int | None = None
    warnings: list[str] = field(default_factory=list)
    preview: DatasetPreview | None = None

    @property
    def validation_status(self) -> str:
        return "valid" if self.repository is not None else "invalid"

    def summary(self) -> DatasetSummary:
        row_counts = self.repository.row_counts if self.repository else {}
        return DatasetSummary(
            dataset_id=self.dataset_id,
            name=self.name,
            source=self.source,
            schema_kind=self.schema_kind,
            row_counts=row_counts,
            size_bytes=self.size_bytes,
            created_at=self.created_at,
            validation_status=self.validation_status,
            warnings=self.warnings,
        )


class DatasetRegistry:
    def __init__(self, default_repository: WorkbookRepository, default_name: str = "Configured workbook") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._datasets: dict[str, Dataset] = {
            DEFAULT_DATASET_ID: Dataset(
                dataset_id=DEFAULT_DATASET_ID,
                name=default_name,
                source="default",
                schema_kind="known",
                repository=default_repository,
                created_at=now,
            )
        }
        self._default_id = DEFAULT_DATASET_ID

    @property
    def default_dataset_id(self) -> str:
        return self._default_id

    def list_all(self) -> list[Dataset]:
        return list(self._datasets.values())

    def get(self, dataset_id: str | None) -> Dataset:
        key = dataset_id or self._default_id
        # Reject malformed dataset IDs before looking up a dataset.
        if not _ID_PATTERN.fullmatch(key):
            raise DatasetNotFoundError(f"No dataset found with ID '{key}'.")
        dataset = self._datasets.get(key)
        if dataset is None:
            raise DatasetNotFoundError(f"No dataset found with ID '{key}'.")
        return dataset

    def resolve_repository(self, dataset_id: str | None) -> WorkbookRepository:
        """Return the queryable repository for a dataset id (None -> default)."""
        dataset = self.get(dataset_id)
        if dataset.repository is None:
            raise InvalidUploadError(
                f"Dataset '{dataset.dataset_id}' is not queryable "
                "(its schema was not recognized)."
            )
        return dataset.repository

    def register(
        self,
        dataset_id: str,
        name: str,
        schema_kind: str,
        repository: WorkbookRepository | None,
        storage_path: Path | None,
        size_bytes: int | None,
        warnings: list[str],
        preview: DatasetPreview | None,
    ) -> Dataset:
        dataset = Dataset(
            dataset_id=dataset_id,
            name=name,
            source="upload",
            schema_kind=schema_kind,
            repository=repository,
            created_at=datetime.now(timezone.utc).isoformat(),
            storage_path=storage_path,
            size_bytes=size_bytes,
            warnings=warnings,
            preview=preview,
        )
        self._datasets[dataset_id] = dataset
        return dataset

    def remove(self, dataset_id: str) -> None:
        dataset = self.get(dataset_id)
        if dataset.dataset_id == self._default_id:
            raise InvalidUploadError("The default dataset cannot be removed.")
        storage_path = dataset.storage_path
        del self._datasets[dataset_id]
        if storage_path is not None:
            try:
                storage_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not delete stored file for dataset %s.", dataset_id)
        logger.info("Removed dataset %s.", dataset_id)
