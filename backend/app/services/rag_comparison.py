"""Comparison notices and helpers for RAG document comparison."""

import re

from app.services.document_service import tokenize

_COMPARISON_TARGET_NOTICE = (
    "I need the names of two uploaded documents to compare. Name both "
    "documents, or retrieve both first and then ask again."
)

_COMPARISON_SAME_NOTICE = (
    "Both names refer to the same uploaded document, so there is nothing to "
    "compare. Name two different documents."
)

_COMPARISON_INSUFFICIENT_NOTICE = (
    "Both documents were found, but their retrieved passages do not support "
    "the requested comparison."
)

_COMPARISON_FILLER_TERMS = frozenset(
    {
        "between", "both", "compare", "comparing", "comparison",
        "content", "contents", "contrast", "detail", "details",
        "differ", "difference", "differences", "doc", "docs",
        "document", "documents", "file", "files", "leave", "leaves",
        "overview", "pdf", "pdfs", "policies", "policy",
        "similarities", "similarity", "them", "two", "uploaded",
        "versus", "vs",
    }
)


def _comparison_retrieval_query(question: str, names: list[str]) -> str:
    """Remove file names and comparison wording from a retrieval query."""
    text = question

    for name in names:
        text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)

    text = re.sub(
        r"\b(?:compar(?:e|es|ed|ing|ison|isons)|differences?|versus|vs\.?"
        r"|contrast|differ)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    return " ".join(text.split())


def _has_comparison_topic(query: str) -> bool:
    """True when a comparison query still asks about specific content."""
    return any(
        token not in _COMPARISON_FILLER_TERMS
        for token in tokenize(query)
    )