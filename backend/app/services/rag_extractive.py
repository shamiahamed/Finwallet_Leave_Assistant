"""Extractive fallback answers for RAG when the LLM is unavailable.

These functions produce deterministic answers from retrieved passages
without calling the LLM, so the feature keeps working without Groq.
"""

import re

from app.services.document_service import tokenize

_INSUFFICIENT_NOTICE = (
    "The available documents do not contain information that answers this "
    "question. Upload a relevant policy document, or rephrase the question."
)


def _is_summary_request(question: str) -> bool:
    """Identify requests asking for a document summary or overview."""
    return bool(
        re.search(
            r"\b("
            r"summar(?:y|ies|ize|ise|ized|ised|izing|ising)"
            r"|overview"
            r"|key\s+points"
            r"|main\s+points"
            r"|highlights?"
            r"|outline"
            r"|summariz(?:e|ation)"
            r")\b",
            question.lower(),
        )
    )


def _build_context_block(chunks) -> str:
    """Build a delimited context block with source locations."""
    lines = ["<passages>"]

    for index, (chunk, _score) in enumerate(chunks, start=1):
        location = f"page {chunk.page}" if chunk.page else "text"
        lines.append(
            f"[{index}] ({chunk.document_name}, {location}) {chunk.text}"
        )

    lines.append("</passages>")
    return "\n".join(lines)


def _focused_extract(question: str, chunk) -> str | None:
    """Return the most relevant sentence(s) from a chunk for a factual question."""
    text = chunk.text.strip()
    if not text:
        return None

    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return None

    question_tokens = set(tokenize(question))
    if not question_tokens:
        return None

    best_score = 0.0
    best_sentences: list[str] = []

    for sentence in sentences:
        sentence_tokens = set(tokenize(sentence))
        if not sentence_tokens:
            continue
        overlap = len(question_tokens & sentence_tokens) / len(question_tokens)
        if overlap > best_score:
            best_score = overlap
            best_sentences = [sentence]
        elif overlap == best_score and best_score > 0:
            best_sentences.append(sentence)

    if best_score < 0.25 or not best_sentences:
        return None

    return " ".join(best_sentences[:2])


def _extractive_answer(question: str, chunks) -> str:
    """Provide a deterministic fallback using retrieved passages."""
    if not chunks:
        return _INSUFFICIENT_NOTICE

    if _is_summary_request(question):
        snippets = []

        for chunk, _score in chunks:
            location = f"page {chunk.page}" if chunk.page else "the document"
            snippet = chunk.text.strip()

            if snippet:
                snippets.append(
                    f"- {chunk.document_name} ({location}): {snippet}"
                )

        if not snippets:
            return _INSUFFICIENT_NOTICE

        return (
            "Relevant passages from the uploaded documents "
            "(AI summarization unavailable \u2014 extractive summary):\n"
            + "\n".join(snippets)
        )

    top = chunks[0][0]
    location = f"page {top.page}" if top.page else "the document"
    label = f"{top.document_name} ({location})"

    focused = _focused_extract(question, top)
    if focused:
        return (
            f"Based on {label} "
            f"(AI summarization unavailable \u2014 matched extract):\n"
            f"{focused}"
        )

    return (
        f"Based on {label} "
        f"(AI summarization unavailable \u2014 relevant extract):\n"
        f"{top.text.strip()}"
    )


def _extractive_comparison_answer(chunks) -> str:
    """Provide labelled passages from each document when the LLM is down."""
    by_document: dict[str, list] = {}
    name_for: dict[str, str] = {}

    for chunk, _score in chunks:
        doc_id = getattr(chunk, "document_id", None)
        if not doc_id:
            continue
        text = chunk.text.strip()
        if not text:
            continue
        if doc_id not in by_document:
            by_document[doc_id] = []
            name_for[doc_id] = getattr(chunk, "document_name", "document")
        by_document[doc_id].append(chunk)

    if len(by_document) < 2:
        return _INSUFFICIENT_NOTICE

    sections: list[str] = []
    for doc_id, doc_chunks in by_document.items():
        doc_name = name_for[doc_id]
        passage_lines: list[str] = []
        for chunk in doc_chunks:
            location = f"page {chunk.page}" if chunk.page else "the document"
            passage_lines.append(f"  [{location}] {chunk.text.strip()}")
        sections.append(f"{doc_name}:\n" + "\n".join(passage_lines))

    return (
        "Comparison extracts (AI summarization unavailable \u2014 "
        "showing retrieved passages only; the comparison may not cover "
        "all differences between the documents):\n\n"
        + "\n\n".join(sections)
    )