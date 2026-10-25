"""Deterministic tests for Phase 6 document-Q&A reliability (A-G).

These exercise routing, document-targeted retrieval, the re-upload lifecycle,
and evidence reporting without calling the LLM.
"""

import sys

from app.core.config import get_settings
from app.services.document_registry import DocumentRegistry
from app.services.document_service import Chunk, Document, tokenize
from app.services.rag_service import answer_document_question
from app.utils.document_names import normalize_document_key
from app.utils.scope_resolver import (
    detect_document_name,
    detect_document_reference,
)

PASS = 0
FAIL = 0


def check(label, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  OK   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


def make_document(doc_id, name, chunks):
    built = []
    for index, (page, text) in enumerate(chunks):
        built.append(
            Chunk(
                chunk_id=f"{doc_id}-{index}",
                document_id=doc_id,
                document_name=name,
                page=page,
                text=text,
                tokens=tokenize(text),
            )
        )
    return Document(
        document_id=doc_id,
        name=name,
        source="pdf",
        page_count=len(chunks),
        chunks=built,
        created_at="now",
    )


def main():
    print("=== A: explicit document-reference detection ===")
    explicit = [
        "According to the uploaded PDF, how many Casual Leave days are allowed per year?",
        "Show the Casual Leave details mentioned in the uploaded document.",
        "What is the maximum age for Casual Leave eligibility according to this PDF?",
        "What is the yearly Casual Leave entitlement stated in the uploaded PDF?",
        "Summarize the uploaded file.",
    ]
    for question in explicit:
        check(f"document reference: {question[:45]!r}", detect_document_reference(question))

    structured = [
        "How many Casual Leave days are allowed per year?",
        "What is the Sick Leave policy?",
        "Show all leave policies.",
        "How many employees are in Engineering?",
        "Show everyone's leave balances",
    ]
    for question in structured:
        check(f"no document reference: {question[:45]!r}", not detect_document_reference(question))

    print("=== A: named document extraction ===")
    check(
        "filename matched",
        detect_document_name("per Sample_Leave_Policy.pdf") == "Sample_Leave_Policy.pdf",
    )
    check(
        "unrelated name not matched",
        detect_document_name("per the handbook") is None,
    )
    check(
        "bare policy word is not a filename",
        detect_document_name("What is the leave policy?") is None,
    )
    check(
        "two filenames are not silently reduced to one",
        detect_document_name("compare Alpha.pdf and Beta.pdf") is None,
    )

    settings = get_settings()

    print("=== D: document-targeted retrieval ===")
    registry = DocumentRegistry()
    registry.add(
        make_document(
            "d1",
            "Sample_Leave_Policy.pdf",
            [(2, "Casual Leave: 12 days per calendar year. Accrual: Annual. Paid.")],
        )
    )
    registry.add(
        make_document(
            "d2",
            "Other_Handbook.pdf",
            [(1, "Casual Leave entitlement is 20 days annually in the other handbook.")],
        )
    )
    targeted = answer_document_question(
        "How many casual leave days per year?",
        registry,
        settings,
        document_name="Sample_Leave_Policy.pdf",
    )
    check("targeted answer matched", targeted["matched"])
    check(
        "targeted sources only the named document",
        {src["document_name"] for src in targeted["sources"]} == {"Sample_Leave_Policy.pdf"},
    )

    untargeted = answer_document_question(
        "How many casual leave days per year?", registry, settings
    )
    check(
        "untargeted search spans documents",
        len({src["document_name"] for src in untargeted["sources"]}) >= 2,
    )

    print("=== D: a name supplied only by the intent is not trusted ===")
    # A name that appears in the question is checked strictly and reported as
    # unavailable when it matches nothing. A name that arrives only through
    # the intent is ignored when it cannot be resolved, so the fallback for
    # unsupported questions keeps working.
    ignored = answer_document_question(
        "how many days?", registry, settings, document_name="Nope.pdf"
    )
    check(
        "unresolved intent name does not block the answer",
        ignored["matched"] is True,
    )
    check(
        "unresolved intent name still cites real documents",
        len(ignored["sources"]) > 0,
    )

    print("=== E: evidence reported only when supported ===")
    unsupported = answer_document_question(
        "What is the capital of France?", registry, settings
    )
    check("unsupported answer not matched", unsupported["matched"] is False)
    check("unsupported answer has no sources", unsupported["sources"] == [])

    print("=== C: same-filename re-upload replaces ===")
    lifecycle = DocumentRegistry()
    lifecycle.add(make_document("a", "Same.pdf", [(1, "old alpha")]))
    lifecycle.add(make_document("b", "Same.pdf", [(1, "new beta")]))
    docs = lifecycle.list_all()
    check("same-name upload keeps one document", len(docs) == 1)
    check("same-name upload keeps latest", docs[0].document_id == "b")
    lifecycle.add(make_document("c", "Other.pdf", [(1, "distinct")]))
    check("different-name upload coexists", len(lifecycle.list_all()) == 2)

    print("=== F: extractive fallback is labelled ===")
    fallback = answer_document_question(
        "How many casual leave days per year?", registry, settings,
        document_name="Sample_Leave_Policy.pdf",
    )
    check(
        "fallback never presents an empty answer",
        bool(fallback["answer"].strip()),
    )

    print("=== Normaliser: shared key rules ===")
    check(
        "separators and case collapse to one key",
        normalize_document_key("Sample_Leave_Policy.pdf")
        == normalize_document_key("sample leave policy.pdf")
        == normalize_document_key("SAMPLE-LEAVE-POLICY.PDF"),
    )
    check(
        "copy suffix is preserved — variant and base produce different keys",
        normalize_document_key("Sample_Leave_Policy (1).pdf")
        != normalize_document_key("Sample_Leave_Policy.pdf"),
    )
    check(
        "extension differences collapse to one key",
        normalize_document_key("Policy.pdf") == normalize_document_key("policy.txt"),
    )
    check(
        "different names keep different keys",
        normalize_document_key("Alpha.pdf") != normalize_document_key("Beta.pdf"),
    )

    print("=== Copy suffix: typed name matches the stored copy ===")
    copy_registry = DocumentRegistry()
    copy_registry.add(
        make_document(
            "c1",
            "Sample_Leave_Policy (1).pdf",
            [(2, "Casual Leave: 15 days per calendar year. Accrual: Annual.")],
        )
    )
    copy_result = answer_document_question(
        "According to Sample_Leave_Policy.pdf, how many casual leave days per year?",
        copy_registry,
        settings,
    )
    check("copy suffix still resolves", copy_result["matched"] is True)
    check(
        "copy suffix resolves to the stored document",
        {src["document_name"] for src in copy_result["sources"]}
        == {"Sample_Leave_Policy (1).pdf"},
    )

    print("=== Two documents: retrieval and citation stay isolated ===")
    two_registry = DocumentRegistry()
    two_registry.add(
        make_document(
            "a1",
            "Alpha (1).pdf",
            [(2, "Casual Leave: 15 days per calendar year.")],
        )
    )
    two_registry.add(
        make_document(
            "b1",
            "Beta.pdf",
            [(1, "Casual Leave entitlement is 30 days annually.")],
        )
    )
    isolated = answer_document_question(
        "According to Alpha.pdf, how many casual leave days per year?",
        two_registry,
        settings,
    )
    check("isolated answer matched", isolated["matched"] is True)
    check(
        "only the named document is cited",
        {src["document_name"] for src in isolated["sources"]} == {"Alpha (1).pdf"},
    )
    check(
        "the other document's content is not cited",
        all("30 days" not in src["text"] for src in isolated["sources"]),
    )
    check(
        "the named document's content is cited",
        any("15 days" in src["text"] for src in isolated["sources"]),
    )

    print("=== Ambiguity: several documents share a name ===")
    ambiguous_registry = DocumentRegistry()
    ambiguous_registry.add(make_document("p1", "Policy (1).pdf", [(1, "alpha text")]))
    ambiguous_registry.add(make_document("p2", "Policy (2).pdf", [(1, "beta text")]))
    ambiguous = answer_document_question(
        "According to Policy.pdf, what is the leave policy?",
        ambiguous_registry,
        settings,
    )
    check("ambiguity is not answered", ambiguous["matched"] is False)
    check("ambiguity cites nothing", ambiguous["sources"] == [])
    check(
        "ambiguity lists both candidates",
        "Policy (1).pdf" in ambiguous["answer"]
        and "Policy (2).pdf" in ambiguous["answer"],
    )

    print("=== Missing document: named but never uploaded ===")
    missing_result = answer_document_question(
        "According to Missing_Policy.pdf, what is the leave policy?",
        copy_registry,
        settings,
    )
    check("missing document is not answered", missing_result["matched"] is False)
    check("missing document cites nothing", missing_result["sources"] == [])
    check(
        "missing document is named in the message",
        "Missing_Policy.pdf" in missing_result["answer"],
    )

    print(f"\nPASS={PASS} FAIL={FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
