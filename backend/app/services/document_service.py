"""Document ingestion and deterministic lexical retrieval for RAG.

PDF/text documents are extracted, split into page-aware chunks, and scored with
a pure-Python lexical method (tokenization, stopword removal, term frequency,
with an inverse-document-frequency weight). No embedding models, vector stores,
or heavy ML dependencies are used, so ranking is deterministic and testable.

This module is deliberately separate from the structured Excel/CSV services:
document retrieval never performs employee/leave calculations.
"""

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.exceptions.errors import InvalidUploadError

logger = logging.getLogger(__name__)

ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".txt", ".md"}
_PDF_MAGIC = b"%PDF"

# Chunking: group whole sentences/words into readable, page-tagged chunks.
_CHUNK_CHARS = 800
_CHUNK_OVERLAP_CHARS = 120

# Small, common English stopword set. Kept inline to avoid a new dependency.
_STOPWORDS = frozenset(
    "a an the and or but if then else of to in on at by for with from as is are was "
    "were be been being it its this that these those he she they them his her their "
    "we you your i me my our do does did done can could should would may might will "
    "what when where who whom which how why not no nor so than too very s t just".split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# A few domain synonyms so a paraphrase still overlaps the source wording.
_SYNONYMS = {
    "leave": {"leave", "leaves"},
    "leaves": {"leave", "leaves"},
    "carry": {"carry", "carried", "carryover", "carryforward"},
    "forward": {"forward", "carryforward", "carryover"},
    "carryforward": {"carryforward", "carry", "forward"},
    "carryover": {"carryover", "carry"},
    "allow": {"allow", "allowed", "allowance", "allows"},
    "allowed": {"allow", "allowed", "allowance"},
    "allowance": {"allowance", "allow", "allowed"},
    "entitle": {"entitle", "entitled", "entitlement", "entitlements"},
    "entitlement": {"entitlement", "entitlements", "entitle", "entitled"},
    "sick": {"sick"},
    "casual": {"casual"},
    "earned": {"earned"},
    "notice": {"notice", "notify", "notification"},
    "approve": {"approve", "approved", "approval", "approvals"},
    "approval": {"approval", "approvals", "approve", "approved"},
    "policy": {"policy", "policies"},
    "accrual": {"accrual", "accrue", "accrued", "accruals"},
    "eligib": {"eligib", "eligible", "eligibility"},
    "encash": {"encash", "encashed", "encashment", "encashments"},
    "encashment": {"encashment", "encashments", "encash", "encashed"},
    "probation": {"probation", "probationary"},
    "probationary": {"probationary", "probation"},
}


def _stem(token: str) -> str:
    # Very light suffix stripping so inflected forms share one token.
    for suffix in ("ization", "ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return _normalize(token[: -len(suffix)])
    return _normalize(token)


def _normalize(stem: str) -> str:
    # Collapse a trailing silent "e" so "leave" and "leaves" share one stem.
    if len(stem) > 3 and stem.endswith("e"):
        return stem[:-1]
    return stem


def _expand(token: str) -> set[str]:
    # Return the token plus its stem variants and any domain synonyms.
    forms = {token, _stem(token)}
    for key, synonyms in _SYNONYMS.items():
        if token in synonyms or _stem(token) == _stem(key):
            forms.update(synonyms)
    return {_stem(f) for f in forms if f}


def tokenize(text: str) -> list[str]:
    # Lowercase word tokens with stopwords and single characters removed.
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS and len(t) > 1]


def _expand_query(tokens: list[str]) -> set[str]:
    # Expand query tokens to their stems/synonyms for matching.
    expanded: set[str] = set()
    for token in tokens:
        expanded.update(_expand(token))
    return expanded


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    document_name: str
    page: int | None
    text: str
    tokens: list[str] = field(default_factory=list)


@dataclass
class Document:
    document_id: str
    name: str
    source: str  # "pdf" | "text"
    page_count: int
    chunks: list[Chunk]
    created_at: str
    size_bytes: int | None = None
    storage_path: Path | None = None


def _extract_pdf_pages(data: bytes) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


def _extract_text_pages(data: bytes) -> list[str]:
    text = data.decode("utf-8-sig", errors="strict")
    return [text]


def _split_page_into_chunks(text: str) -> list[str]:
    # Split on sentence-ish boundaries, then pack into size-bounded chunks with
    # a small overlap so context around a heading is not lost.
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", clean)
    chunks: list[str] = []
    buffer = ""
    for sentence in sentences:
        if buffer and len(buffer) + len(sentence) + 1 > _CHUNK_CHARS:
            chunks.append(buffer.strip())
            # overlap: keep the tail of the previous chunk as context.
            buffer = buffer[-_CHUNK_OVERLAP_CHARS:] + " " + sentence
        else:
            buffer = f"{buffer} {sentence}".strip()
    if buffer.strip():
        chunks.append(buffer.strip())
    return chunks


def ingest_document(
    filename: str,
    data: bytes,
    settings: Settings,
    *,
    store: bool = True,
) -> Document:
    """Validate, extract, chunk, and (optionally) persist a document."""
    if not data:
        raise InvalidUploadError("The uploaded document is empty.")

    max_bytes = int(settings.max_upload_mb * 1024 * 1024)
    if len(data) > max_bytes:
        raise InvalidUploadError(
            f"The uploaded document exceeds the {settings.max_upload_mb:g} MB limit."
        )

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise InvalidUploadError(
            "Unsupported document type. Allowed: "
            + ", ".join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))
            + "."
        )

    if extension == ".pdf":
        if data[:4] != _PDF_MAGIC:
            raise InvalidUploadError("The file content does not match its declared type.")
        try:
            pages = _extract_pdf_pages(data)
        except Exception as exc:
            logger.warning("PDF parse failed: %s", type(exc).__name__)
            raise InvalidUploadError("The PDF could not be parsed.") from exc
        source = "pdf"
    else:
        try:
            pages = _extract_text_pages(data)
        except Exception as exc:
            logger.warning("Text decode failed: %s", type(exc).__name__)
            raise InvalidUploadError("The text document could not be read.") from exc
        source = "text"

    document_id = uuid4().hex
    document_name = filename or "document"
    # Preserve source and page details so retrieved policy text can be traced back.
    chunks: list[Chunk] = []
    for page_index, page_text in enumerate(pages, start=1):
        for piece in _split_page_into_chunks(page_text):
            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}-{len(chunks)}",
                    document_id=document_id,
                    document_name=document_name,
                    page=page_index if source == "pdf" else None,
                    text=piece,
                    tokens=tokenize(piece),
                )
            )

    if not chunks:
        raise InvalidUploadError("The document contains no extractable text.")

    storage_path: Path | None = None
    if store:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        storage_path = settings.upload_dir / f"{document_id}{extension}"
        storage_path.write_bytes(data)

    logger.info(
        "Ingested document %s (%s, %d pages, %d chunks).",
        document_id,
        source,
        len(pages),
        len(chunks),
    )
    return Document(
        document_id=document_id,
        name=document_name,
        source=source,
        page_count=len(pages),
        chunks=chunks,
        created_at=datetime.now(timezone.utc).isoformat(),
        size_bytes=len(data),
        storage_path=storage_path,
    )



def score_chunks(
    query: str,
    chunks: list[Chunk],
    top_k: int,
    min_score: float = 0.0,
    min_matches: int | None = None,
) -> list[tuple[Chunk, float]]:
    """Rank document chunks using conservative lexical relevance scoring."""

    query_tokens = tokenize(query)
    if not query_tokens or not chunks or top_k <= 0:
        return []

    # Keep unique original query terms for coverage calculations.
    query_terms = list(dict.fromkeys(_stem(token) for token in query_tokens))
    query_terms = [term for term in query_terms if term]

    if not query_terms:
        return []

    if min_matches is None:
        # Short questions require at least one match; longer questions
        # require partial rather than 50% keyword coverage.
        min_matches = max(1, math.ceil(len(query_terms) * 0.30))

    min_matches = max(1, min(min_matches, len(query_terms)))

    # Expand query terms to include known synonyms.
    expanded_by_term = {
        term: _expand(token)
        for token, term in zip(query_tokens, (_stem(t) for t in query_tokens))
    }

    # Deduplicate expanded variants for each normalized query term.
    normalized_expansions: dict[str, set[str]] = {}
    for token in query_tokens:
        term = _stem(token)
        normalized_expansions.setdefault(term, set()).update(_expand(token))

    chunk_terms: list[set[str]] = []
    document_frequency: dict[str, int] = {}

    for chunk in chunks:
        terms = {_stem(token) for token in (chunk.tokens or tokenize(chunk.text))}
        chunk_terms.append(terms)
        for term in terms:
            document_frequency[term] = document_frequency.get(term, 0) + 1

    total_chunks = len(chunks)
    query_phrase = " ".join(query_tokens)
    scored: list[tuple[Chunk, float]] = []

    for chunk, terms in zip(chunks, chunk_terms):
        if not terms:
            continue

        matched = 0
        score = 0.0

        for query_term in query_terms:
            variants = normalized_expansions.get(query_term, {query_term})
            matching_variants = variants.intersection(terms)

            if not matching_variants:
                continue

            matched += 1
            # Rare matching terms contribute more than common terms.
            best_idf = max(
                math.log(
                    (total_chunks + 1)
                    / (document_frequency.get(variant, 0) + 1)
                ) + 1.0
                for variant in matching_variants
            )
            score += best_idf

        coverage = matched / len(query_terms)

        # Exact topic phrases are strong evidence even if the question
        # contains extra wording such as "how many" or "per year".
        normalized_text = " ".join(tokenize(chunk.text))
        phrase_bonus = 0.0

        for phrase in ("casual leave", "sick leave", "earned leave",
                       "leave policy", "annual entitlement"):
            if phrase in normalized_text and phrase in query_phrase:
                phrase_bonus = max(phrase_bonus, 2.0)

        # Normalize the lexical score so longer chunks do not automatically
        # receive higher scores.
        final_score = (score / len(query_terms)) * coverage + phrase_bonus

        # A strong explicit phrase match can qualify with fewer term matches.
        strong_phrase_match = phrase_bonus > 0 and matched >= 1

        if matched >= min_matches and final_score > min_score:
            scored.append((chunk, final_score))
        elif strong_phrase_match and final_score > min_score:
            scored.append((chunk, final_score))

    # Stable ordering: highest score first, then stable chunk ID.
    scored.sort(key=lambda item: (-item[1], item[0].chunk_id))
    return scored[:top_k]
