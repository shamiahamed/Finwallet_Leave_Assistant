"""In-memory registry of uploaded documents for retrieval-augmented answers.

Documents are separate from datasets: this registry only holds text passages for
the RAG capability and never participates in structured leave/employee queries.
"""

import logging
import re
import threading
from datetime import datetime, timezone

from app.exceptions.errors import DocumentNotFoundError
from app.services.document_service import Document

logger = logging.getLogger(__name__)

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _parse_created_at(value: object) -> datetime | None:
    """Parse a document's ``created_at`` timestamp, or return None."""
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


class DocumentRegistry:
    """Thread-safe in-memory store of ingested documents."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._documents: dict[str, Document] = {}

    def add(self, document: Document) -> Document:
        """Store a document, replacing any existing one with the same name.

        Re-uploading a file with the same filename replaces the previous
        version so answers reflect the latest content. Documents with
        different names coexist.
        """
        replaced: list[Document] = []

        with self._lock:
            new_name = str(getattr(document, "name", "")).strip().lower()

            if new_name:
                for doc_id, existing in list(self._documents.items()):
                    existing_name = str(getattr(existing, "name", "")).strip().lower()

                    if existing_name == new_name:
                        replaced.append(self._documents.pop(doc_id))

            self._documents[document.document_id] = document

        for old in replaced:
            if old.storage_path is not None:
                try:
                    old.storage_path.unlink(missing_ok=True)
                except OSError as exc:  # pragma: no cover - disk errors are rare
                    logger.warning(
                        "Could not delete replaced document file: %s",
                        type(exc).__name__,
                    )

        if replaced:
            logger.info("Replaced %d previous document(s) with same name.", len(replaced))

        return document

    def get(self, document_id: str) -> Document:
        if not document_id or not _ID_PATTERN.match(document_id):
            raise DocumentNotFoundError(document_id)
        with self._lock:
            document = self._documents.get(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    def remove(self, document_id: str) -> None:
        document = self.get(document_id)
        with self._lock:
            self._documents.pop(document_id, None)
        if document.storage_path is not None:
            try:
                document.storage_path.unlink(missing_ok=True)
            except OSError as exc:  # pragma: no cover - disk errors are rare
                logger.warning("Could not delete document file: %s", type(exc).__name__)

    def list_all(self) -> list[Document]:
        with self._lock:
            return sorted(self._documents.values(), key=lambda d: d.document_id)

    def latest(self) -> Document | None:
        """Return the most recently uploaded document.

        ``ingest_document`` stores ``created_at`` as a UTC ISO timestamp, so it
        is the primary ordering key. When a timestamp is missing or malformed,
        registry insertion order is used instead: ``add`` re-inserts replaced
        documents, so the last entry is the newest upload. UUID ordering is
        never used for recency.
        """
        with self._lock:
            documents = list(self._documents.values())

        best: Document | None = None
        best_key: tuple[bool, datetime, int] | None = None

        for index, document in enumerate(documents):
            created = _parse_created_at(getattr(document, "created_at", None))
            key = (
                created is not None,
                created or datetime.min.replace(tzinfo=timezone.utc),
                index,
            )

            if best_key is None or key > best_key:
                best = document
                best_key = key

        return best

    def all_chunks(self):
        with self._lock:
            documents = list(self._documents.values())
        chunks = []
        for document in documents:
            chunks.extend(document.chunks)
        return chunks

    def is_empty(self) -> bool:
        with self._lock:
            return not self._documents
