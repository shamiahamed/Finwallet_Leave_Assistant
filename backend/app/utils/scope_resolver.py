
import re
from collections.abc import Iterable

from app.utils.document_names import extract_document_mentions


ALL_EMPLOYEES_PATTERNS = (
    r"\beveryone\b",
    r"\ball\s+employees\b",
    r"\ball\s+staff\b",
    r"\ball\s+workers\b",
    r"\bcompany[- ]wide\b",
    r"\bwhole\s+(?:company|organization|organisation)\b",
    r"\bentire\s+(?:company|organization|organisation)\b",
)

BALANCE_PATTERNS = (
    r"\bleave\s+balances?\b",
    r"\bbalances?\b",
    r"\bdays?\s+left\b",
    r"\bremaining\s+leave\b",
    r"\bleave\s+remaining\b",
    r"\bavailable\s+leave\b",
    r"\bleave\s+entitlement\b",
)

HEADCOUNT_PATTERNS = (
    r"\bhow\s+many\s+employees\b",
    r"\bhow\s+many\s+staff\b",
    r"\bemployee\s+count\b",
    r"\bheadcount\b",
    r"\bcount\s+employees\b",
    r"\bnumber\s+of\s+employees\b",
)

DEPARTMENT_SUMMARY_PATTERNS = (
    r"\bleave\s+activity\b",
    r"\bdepartment\s+summary\b",
    r"\bleave\s+summary\b",
    r"\bsummarize\s+.*\bleave\b",
    r"\bsummarise\s+.*\bleave\b",
    r"\bwhich\s+department\b.*\b(?:most|highest|max|largest)\b.*\bleave\b",
    r"\bwhich\s+department\b.*\b(?:least|lowest|min|smallest)\b.*\bleave\b",
    r"\bdepartment\b.*\b(?:most|highest|max)\b.*\bapproved\s+leave\b",
    r"\bdepartment\b.*\b(?:least|lowest|min)\b.*\bapproved\s+leave\b",
)

# Explicit references to an uploaded document. These take priority over a
# conflicting structured intent so "according to the PDF" answers from the
# document rather than the Excel worksheet.
DOCUMENT_REFERENCE_PATTERNS = (
    r"\buploaded\s+(?:pdf|document|file|doc|attachment|policy)\b",
    r"\b(?:pdf|document|doc|file|attachment)\s+(?:i\s+)?uploaded\b",
    r"\baccording\s+to\s+(?:the\s+)?(?:uploaded\s+)?(?:pdf|document|file|doc)\b",
    r"\b(?:in|from|per|within|based\s+on)\s+the\s+(?:uploaded\s+)?(?:pdf|document|file|doc)\b",
    r"\bthe\s+(?:uploaded\s+)?(?:pdf|document|file)\b",
    r"\bthis\s+(?:pdf|document|file)\b",
    r"\bthe\s+uploaded\s+document\b",
    r"\bsample[_\s-]*leave[_\s-]*policy\b",
    r"\b\.pdf\b",
    r"\b\.docx?\b",
    r"\b\.txt\b",
)

# An explicit request to compare document content, as opposed to a question
# that merely mentions several files.
COMPARISON_PATTERNS = (
    r"\bcompar(?:e|es|ed|ing|ison|isons)\b",
    r"\bdifference(?:s)?\b",
    r"\bversus\b",
    r"\bvs\.?\b",
    r"\bcontrast\b",
    r"\bhow\s+do(?:es)?\b.*\bdiffer\b",
)

# Wording that points at a specific pair of uploaded documents. Used on its
# own, this is not a comparison; it only identifies reliable candidates.
DOCUMENT_PAIR_REFERENCE_PATTERNS = (
    r"\bboth\s+(?:the\s+)?(?:uploaded\s+)?(?:documents?|pdfs?|files?|attachments?|(?:leave\s+)?policies?)\b",
    r"\bthe\s+both\s+(?:uploaded\s+)?(?:documents?|pdfs?|files?|attachments?|(?:leave\s+)?policies?)\b",
    r"\b(?:these|those|the)\s+(?:two|both)\s+(?:uploaded\s+)?"
    r"(?:documents?|pdfs?|files?|attachments?|(?:leave\s+)?policies?)\b",
    r"\b(?:both|either)\s+of\s+(?:the\s+)?(?:uploaded\s+)?"
    r"(?:documents?|pdfs?|files?|attachments?|(?:leave\s+)?policies?)\b",
    r"\b(?:two|both)\s+(?:uploaded\s+)?(?:documents?|pdfs?|files?|attachments?|(?:leave\s+)?policies?)\b",
)

# Contexts that mention a department and a "balance"-like word but are not
# leave-balance queries. They must fall through to the normal parser.
NON_BALANCE_PATTERNS = (
    r"\bpolicy\b",
    r"\bpolicies\b",
    r"\bentitlement\s+rules?\b",
    r"\baccrual\b",
    r"\bapproval\b",
    r"\bapproved\b",
    r"\bpending\b",
    r"\brejected\b",
    r"\brequest(?:s|ed)?\b",
    r"\bapply\b",
    r"\bapplied\b",
    r"\bhistory\b",
    r"\bhow\s+many\s+days\b.*\b(?:off|taken)\b",
)

# A follow-up must look like a continuation, not merely contain "and" or
# "also" somewhere in a standalone question. A bare summary/overview of the
# active document also counts, because it has no structured-data anchor and
# only makes sense against the document the user just received.
DOCUMENT_FOLLOWUP_CUE_PATTERNS = (
    r"^\s*(?:and|also|then|so)\b",
    r"\b(?:what|how)\s+(?:about|of)\b",
    r"\bsummar(?:y|ies|ize|ise|ized|ised|izing|ising)\b",
    r"\boverview\b",
    r"\bkey\s+points\b",
    r"\bhighlights?\b",
    r"\boutline\b",
    r"\bcheck\s+(?:out|over|review)\b",
    r"\blook\s+(?:at|over|review)\b",
    r"\breview\b",
)

# Content that belongs to policy documents rather than the structured policy
# worksheet. Used together with a continuation cue, never on its own.
DOCUMENT_TOPIC_PATTERNS = (
    r"\bpolic(?:y|ies)\b",
    r"\brule(?:s)?\b",
    r"\baccrual\b",
    r"\bprobation(?:ary)?\b",
    r"\bcarry[-\s]?(?:forward|over)\b",
    r"\bcarried\s+forward\b",
    r"\bencash\w*\b",
    r"\bnotice(?:\s+period)?\b",
    r"\beligib\w*\b",
    r"\bentitlement\b",
    r"\b(?:minimum|maximum|min|max)\s+age\b",
    r"\bage\s+(?:limit|limits|requirement|requirements|criteria)\b",
    r"\bmedical\s+certificate\b",
    r"\bapproval\s+(?:process|workflow|procedure|chain)\b",
    r"\bwho\s+approves\b",
)

# Any of these means the question is clearly about structured records.
STRUCTURED_DATA_ANCHOR_PATTERNS = (
    r"\bEMP\d+\b",
    r"\bmy\b",
    r"\bbalances?\b",
    r"\bremaining\b",
    r"\bavailable\b",
    r"\bdays?\s+left\b",
    r"\bdo\s+i\s+have\b",
    r"\bhow\s+many\b[^?]{0,40}\b(?:days?|leave)\b",
    r"\b(?:last|this|next)\s+(?:week|month|year)\b",
    r"\brequest(?:s|ed)?\b",
    r"\bapproved?\b",
    r"\bpending\b",
    r"\brejected\b",
    r"\bhistory\b",
    r"\btaken\b",
    r"\btook\b",
    r"\bappl(?:y|ies|ied)\b",
    r"\bhow\s+many\s+(?:employees|staff)\b",
    r"\bheadcount\b",
    r"\bemployee\s+count\b",
    r"\bcount\s+employees\b",
    r"\bnumber\s+of\s+employees\b",
    r"\bdepartment\s+(?:summary|activity)\b",
    r"\bleave\s+(?:summary|activity)\b",
    r"\b(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\b",
    r"\b20\d{2}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d+\s+days?\b",
)

# Policy attributes the structured worksheet does not model. The worksheet
# stores only annual days, accrual, and payment.
UNSTRUCTURED_POLICY_DETAIL_PATTERNS = (
    r"\bage\b",
    r"\bretirement\b",
    r"\bprobation(?:ary)?\b",
    r"\bcarry[-\s]?(?:forward|over)\b",
    r"\bcarried\s+forward\b",
    r"\bencash\w*\b",
    r"\bnotice(?:\s+period)?\b",
    r"\beligib\w*\b",
    r"\bgender\b",
    r"\bnationality\b",
    r"\bmarital\s+status\b",
    r"\bmedical\s+certificate\b",
    r"\bdoctor'?s?\s+note\b",
    r"\bapproval\s+(?:process|workflow|procedure|chain)\b",
    r"\bwho\s+approves\b",
)


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    return any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in patterns
    )


def detect_department_name(
    question: str,
    department_names: Iterable[str],
) -> str | None:
    """Find a department mentioned in a question."""
    matches: list[str] = []

    for department in department_names:
        name = str(department).strip()

        if not name:
            continue

        pattern = rf"(?<!\w){re.escape(name)}(?!\w)"

        if re.search(pattern, question, re.IGNORECASE):
            matches.append(name)

    if not matches:
        return None

    # Prefer the longest match when names overlap.
    return max(matches, key=len)


def detect_leave_type(
    question: str,
    leave_types: Iterable[str],
) -> str | None:
    """Find a leave type mentioned in a question.

    Matches the workbook's canonical names ("Sick Leave") and their short
    forms ("sick"). When more than one type is mentioned, the first one in
    the question wins so the wording order is respected.
    """
    text = question
    best: str | None = None
    best_pos = len(text) + 1

    for leave_type in leave_types:
        name = str(leave_type).strip()

        if not name:
            continue

        stem = name
        for suffix in (" Leave", " leave"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break

        alternation = r"(?:\s+leave)?" if stem != name else ""
        pattern = rf"(?<!\w){re.escape(stem)}{alternation}(?!\w)"

        match = re.search(pattern, text, re.IGNORECASE)

        if match and match.start() < best_pos:
            best = name
            best_pos = match.start()

    return best


def detect_document_reference(question: str) -> bool:
    """Return True when the question explicitly refers to an uploaded document.

    This is a deterministic signal: "according to the PDF", "the uploaded
    document", a filename ending in .pdf/.txt, etc. It lets an explicit
    document request win over a conflicting structured intent such as
    leave_policy, which otherwise answers from the Excel worksheet.
    """
    text = (question or "").strip()

    if not text:
        return False

    return _matches_any(text, DOCUMENT_REFERENCE_PATTERNS)


def detect_document_name(question: str) -> str | None:
    """Return the file name mentioned in a question, if there is exactly one.

    Only a token carrying a document extension counts as a mention, so
    "What is the leave policy?" never resolves to a document named
    "Policy.pdf". When a question names more than one document no name is
    returned, because picking one of them would be a guess; the retrieval
    layer reports that ambiguity instead.
    """
    mentions = extract_document_mentions(question)

    if len(mentions) != 1:
        return None

    return mentions[0]


def is_document_comparison_request(
    question: str,
    mentions: list[str] | None = None,
) -> bool:
    """Return True when the user explicitly asks to compare documents.

    A comparison cue alone is not enough: the question must either name two
    files or point at an explicit document pair (for example "both documents").
    This keeps ordinary multi-filename questions on the ambiguity path.
    """
    text = (question or "").strip()

    if not text:
        return False

    if not _matches_any(text, COMPARISON_PATTERNS):
        return False

    if mentions is None:
        mentions = extract_document_mentions(text)

    if len(mentions) >= 2:
        return True

    return _matches_any(text, DOCUMENT_PAIR_REFERENCE_PATTERNS)


def is_headcount_question(question: str) -> bool:
    """Identify explicit employee-count questions."""
    text = question.strip()

    if _matches_any(text, DEPARTMENT_SUMMARY_PATTERNS):
        return False

    return _matches_any(text, HEADCOUNT_PATTERNS)


def detect_balance_scope(
    question: str,
    department_names: Iterable[str] = (),
    leave_types: Iterable[str] = (),
) -> dict | None:
    """
    Detect clear leave-balance scope without relying on the LLM.

    Returns None when the question is not clearly a balance query.
    """
    text = question.strip()

    if not text:
        return None

    # Do not misclassify headcount or activity summaries.
    if is_headcount_question(text):
        return None

    if _matches_any(text, DEPARTMENT_SUMMARY_PATTERNS):
        return None

    # A department plus a request/policy word is not a balance query.
    if _matches_any(text, NON_BALANCE_PATTERNS):
        return None

    if not _matches_any(text, BALANCE_PATTERNS):
        return None

    leave_type = detect_leave_type(text, leave_types)

    if _matches_any(text, ALL_EMPLOYEES_PATTERNS):
        return {
            "scope": "all",
            "department": None,
            "employee_id": None,
            "leave_type": leave_type,
        }

    department = detect_department_name(text, department_names)

    if department:
        return {
            "scope": "department",
            "department": department,
            "employee_id": None,
            "leave_type": leave_type,
        }

    employee_match = re.search(
        r"\bEMP\d+\b",
        text,
        re.IGNORECASE,
    )

    if employee_match:
        return {
            "scope": "single",
            "department": None,
            "employee_id": employee_match.group(0).upper(),
            "leave_type": leave_type,
        }

    # Employee names and contextual follow-ups are handled
    # by the intent parser and conversation logic.
    return None


# Cues that alone identify a document follow-up because they have no meaning
# outside a document context. They need no additional topic pattern.
DOCUMENT_FOLLOWUP_SOLO_CUES = (
    r"\bsummar(?:y|ies|ize|ise|ized|ised|izing|ising)\b",
    r"\boverview\b",
    r"\bkey\s+points\b",
    r"\bhighlights?\b",
    r"\boutline\b",
    r"\bcheck\s+(?:out|over|review)\b",
    r"\blook\s+(?:at|over|review)\b",
    r"\breview\b",
    r"\bthe\s+(?:most\s+)?recent\s+(?:uploaded\s+)?document\b",
    r"\bthis\s+(?:uploaded\s+)?document\b",
    r"\bthe\s+(?:uploaded\s+)?document\b",
)


def is_document_follow_up(
    question: str,
    leave_types: Iterable[str] = (),
    department_names: Iterable[str] = (),
) -> bool:
    """Detect a terse follow-up that should continue the active document.

    Returns True only when the question is a continuation cue plus a document
    topic or workbook leave type, and carries no structured-data anchor. A
    known department also counts as a structured anchor. This is deliberately
    conservative so structured lookups are never redirected to documents.
    """
    text = (question or "").strip()

    if not text:
        return False

    if _matches_any(text, STRUCTURED_DATA_ANCHOR_PATTERNS):
        return False

    if detect_department_name(text, department_names):
        return False

    # A bare summary/overview/review of the active document has no other
    # interpretation, so it counts as a follow-up on its own.
    if _matches_any(text, DOCUMENT_FOLLOWUP_SOLO_CUES):
        return True

    if not _matches_any(text, DOCUMENT_FOLLOWUP_CUE_PATTERNS):
        return False

    return bool(detect_leave_type(text, leave_types)) or _matches_any(
        text,
        DOCUMENT_TOPIC_PATTERNS,
    )


def asks_unstructured_policy_detail(question: str) -> bool:
    """Detect policy questions about fields absent from the worksheet schema."""
    text = (question or "").strip()

    if not text:
        return False

    return _matches_any(text, UNSTRUCTURED_POLICY_DETAIL_PATTERNS)


_THRESHOLD_CONTEXT_RE = re.compile(
    r"\b(?:remaining|left|balance|available)\b",
    re.IGNORECASE,
)
_ZERO_THRESHOLD_RE = re.compile(
    r"\b(?:zero|none|no\s+(?:remaining|leave|days?|balance))\b|"
    r"\b0\s*(?:days?\s+)?(?:remaining|left)\b|"
    r"\b(?:remaining|left|balance)\b[^?\n]{0,12}\b0\b",
    re.IGNORECASE,
)
_THRESHOLD_RES = (
    re.compile(r"(?:<=|≤)\s*(\d+)"),
    re.compile(
        r"\b(?:less\s+than\s+or\s+equal\s+to|at\s+most|no\s+more\s+than|"
        r"not\s+more\s+than|up\s+to|maximum\s+of|max(?:imum)?)\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(\d+)\s*(?:days?\s+)?(?:or\s+(?:fewer|less)|and\s+(?:below|under))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:less\s+than|fewer\s+than|below|under)\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:exactly|equal\s+to)\s*(\d+)",
        re.IGNORECASE,
    ),
)
_COUNT_RE = re.compile(
    r"\b(?:how\s+many|how\s+much|count|number\s+of)\b",
    re.IGNORECASE,
)
_DEPARTMENT_BREAKDOWN_RE = re.compile(
    r"\b(?:each|every|per|by|across|all)\s+departments?\b|"
    r"\bdepartment[- ]?(?:level|wise)\b",
    re.IGNORECASE,
)
_LEAVE_HISTORY_PATTERNS = (
    r"\bhow\s+much\s+leave\b[^?]{0,30}\b(?:taken|used|took)\b",
    r"\bhow\s+many\b[^?]{0,40}\b(?:days?|leave)\b[^?]{0,30}\b(?:taken|used|took)\b",
    r"\b(?:leave|days?)\s+(?:was|were|has|have|had)\s+(?:been\s+)?(?:taken|used)\b",
    r"\b(?:leave\s+(?:history|taken|used)|used\s+leave|taken\s+leave)\b",
    r"\bhow\s+much\s+leave\s+(?:did|has|have)\b",
)
_GROUP_LEAVE_HISTORY_PATTERNS = (
    r"\b(?:which|what)\s+(?:employees|staff|people)\b[^?]{0,50}"
    r"\b(?:taken|used|took)\b",
    r"\bwho\b[^?]{0,50}\b(?:taken|used|took)\b[^?]{0,20}\bleave\b",
    r"\b(?:employees|staff|people)\b[^?]{0,40}\b(?:have|has|had)\b"
    r"[^?]{0,30}\b(?:taken|used)\b[^?]{0,20}\bleave\b",
    r"\bwho\b[^?]{0,40}\b(?:is|are|currently)\b[^?]{0,20}\b(?:on|taking)\b[^?]{0,20}\bleave\b",
    r"\bwhich\b[^?]{0,40}\b(?:employees|staff|people)\b[^?]{0,30}\b(?:on|taking)\b[^?]{0,20}\bleave\b",
    r"\b(?:which|show|list|get)\b[^?]{0,60}\b(?:employees|staff|people)\b[^?]{0,120}\b(?:have|has|had)\b[^?]{0,60}\b(?:taken|used|took)\b[^?]{0,40}\bleave\b",
    r"\b(?:which|show|list|get)\b[^?]{0,60}\b(?:employees|staff|people)\b[^?]{0,120}\b(?:with|having)\b[^?]{0,80}\b(?:leave|leave\s+history|history)\b",
    r"\b(?:employees|staff|people)\b[^?]{0,120}\b(?:with|having)\b[^?]{0,80}\b(?:leave\s+history|history)\b",
)
_UNKNOWN_EMPLOYEE_PATTERNS = (
    r"\b(?:for|about|of|by|named)\s+(?:an?\s+)?"
    r"(?:unknown|nonexistent|non-existent|invalid)\s+employee\b",
)
_EMPLOYEE_CANDIDATE_RE = re.compile(
    r"\b(?:for|about|of|by|named)\s+(?:employee\s+)?"
    r"([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,2})\b"
)
_EMPLOYEE_CANDIDATE_IGNORES = {
    "the", "this", "that", "these", "those", "all", "any", "each", "every",
    "approved", "pending", "rejected", "cancelled", "canceled", "active",
    "inactive", "leave", "leaves", "employee", "employees", "staff", "team",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
    "oct", "nov", "dec", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
}
_VALID_LEAVE_PREFIX_IGNORES = {
    "the", "a", "an", "my", "his", "her", "their", "our", "your",
    "this", "that", "these", "those", "all", "any", "each", "every",
    "some", "no", "one", "two", "three", "approved", "pending",
    "rejected", "cancelled", "canceled", "paid", "for", "of", "on",
    "in", "to", "with", "without", "about", "by", "from", "as", "at",
    "during", "after", "before", "request", "requests", "days", "day",
    "much", "many", "more", "most", "less", "least", "fewer", "enough",
    "remaining", "available", "taken", "used", "total", "what", "which",
    "whose", "how", "when", "where", "who", "is", "was", "were", "show",
    "list", "find", "get", "tell", "display", "see", "view", "give",
    "check", "retrieve", "pull", "print", "provide", "compare", "summarize",
    "summarise", "describe", "explain", "calculate", "count", "please",
    "need", "want", "like", "take", "takes", "taking", "took", "book",
    "booking", "apply", "applies", "applying", "plan", "planned", "planning",
    "use", "using", "spend", "spent", "grant", "granted", "requesting",
    "requested", "eligible", "eligibility", "entitled", "upcoming",
}


def _leave_type_stems(leave_types: Iterable[str]) -> set[str]:
    stems = set()
    for leave_type in leave_types:
        name = str(leave_type).strip().lower()
        if not name:
            continue
        for suffix in (" leave",):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        stems.add(name)
    return stems


def detect_balance_threshold(question: str) -> dict | None:
    """Return a remaining-balance threshold spec when the question sets one.

    Returns a dict with 'value' (int) and 'operator' (str) keys, or None.
    Operators: 'exactly', 'at_most', 'less_than', 'zero'.
    """
    text = question or ""
    if not _THRESHOLD_CONTEXT_RE.search(text):
        return None

    # Check "exactly N" / "equal to N" first (higher priority)
    match = _THRESHOLD_RES[4].search(text)
    if match:
        return {"value": int(match.group(1)), "operator": "exactly"}

    for pattern in _THRESHOLD_RES[:3]:
        match = pattern.search(text)
        if match:
            return {"value": int(match.group(1)), "operator": "at_most"}

    match = _THRESHOLD_RES[3].search(text)
    if match:
        value = int(match.group(1))
        return {"value": value, "operator": "less_than"}

    # Zero threshold: only match when no comparison operator was found.
    if _ZERO_THRESHOLD_RE.search(text):
        return {"value": 0, "operator": "zero"}

    return None


def is_balance_count_question(question: str) -> bool:
    return bool(_COUNT_RE.search(question or ""))


def is_department_breakdown_question(question: str) -> bool:
    return bool(_DEPARTMENT_BREAKDOWN_RE.search(question or ""))


def is_leave_history_question(question: str) -> bool:
    return _matches_any(question or "", _LEAVE_HISTORY_PATTERNS)


def is_group_leave_history_question(question: str) -> bool:
    """Detect leave-history questions about a group, not one employee."""
    return _matches_any(question or "", _GROUP_LEAVE_HISTORY_PATTERNS)


def asks_currently_on_leave(question: str) -> bool:
    """Detect questions asking who is on leave right now (current/active leave)."""
    return bool(
        re.search(
            r"\b(?:currently|right\s+now|active(?:ly)?)\s+(?:on|taking)\s+leave\b",
            question or "",
            re.IGNORECASE,
        )
        or re.search(
            r"\bwho\b[^?]{0,40}\b(?:is|are)\b[^?]{0,20}\b(?:on|taking)\b[^?]{0,20}\bleave\b",
            question or "",
            re.IGNORECASE,
        )
        or re.search(
            r"\bshow\s+(?:employees|staff|people)\s+(?:currently|right\s+now|active(?:ly)?)\b",
            question or "",
            re.IGNORECASE,
        )
        or re.search(
            r"\bemployees?\s+(?:currently|right\s+now|active(?:ly)?)\s+(?:on|taking)\s+leave\b",
            question or "",
            re.IGNORECASE,
        )
    )


_LR_ID_RE = re.compile(r"\b(LR\d+)\b", re.IGNORECASE)


def detect_leave_request_id(question: str) -> str | None:
    """Return a leave-request ID (e.g. LR0025) from the question, or None."""
    match = _LR_ID_RE.search(question or "")
    if not match:
        return None
    return match.group(1).upper()


def asks_about_leave_request_id(question: str) -> bool:
    """True when the question is specifically about a leave-request ID."""
    text = question or ""
    if not _LR_ID_RE.search(text):
        return False
    lowered = text.lower()
    return bool(
        re.search(
            r"\b(approved|rejected|cancelled|pending|status|details?|"
            r"submitted|type\s+of\s+leave|who\s+submitted|manager|"
            r"approved\s+by|rejected\s+by|who\s+is|what\s+is|"
            r"how\s+many|when\s+was|when\s+did|days?|start|end|"
            r"leave\s+type|employee|requester)\b",
            lowered,
        )
    )


def detect_unsupported_leave_type(
    question: str,
    leave_types: Iterable[str],
) -> str | None:
    """Return a mentioned leave type that is absent from the workbook."""
    valid = _leave_type_stems(leave_types)

    for match in re.finditer(
        r"\b([A-Za-z][A-Za-z-]{2,})\s+leaves?\b",
        question or "",
        re.IGNORECASE,
    ):
        prefix = match.group(1).lower()
        if prefix in valid or prefix in _VALID_LEAVE_PREFIX_IGNORES:
            continue
        return f"{match.group(1)} leave"

    return None


def detect_known_employee_name(
    question: str,
    employee_names: Iterable[str],
) -> str | None:
    matches = []
    for name in employee_names:
        cleaned = str(name).strip()
        if not cleaned:
            continue
        pattern = rf"(?<!\w){re.escape(cleaned)}(?!\w)"
        if re.search(pattern, question or "", re.IGNORECASE):
            matches.append(cleaned)
    if not matches:
        return None
    return max(matches, key=len)


def detect_unresolved_employee_reference(
    question: str,
    *,
    employee_names: Iterable[str] = (),
    department_names: Iterable[str] = (),
    leave_types: Iterable[str] = (),
    approval_statuses: Iterable[str] = (),
) -> str | None:
    """Return an employee reference that cannot be resolved to one employee."""
    text = question or ""

    for pattern in _UNKNOWN_EMPLOYEE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "unknown employee"

    known_names = {str(name).strip().lower() for name in employee_names}
    departments = {str(name).strip().lower() for name in department_names}
    types = _leave_type_stems(leave_types)
    statuses = {str(name).strip().lower() for name in approval_statuses}

    for match in _EMPLOYEE_CANDIDATE_RE.finditer(text):
        candidate = match.group(1).strip()
        normalized = candidate.lower().removesuffix("'s")
        if normalized in _EMPLOYEE_CANDIDATE_IGNORES:
            continue
        if normalized in departments or normalized in types or normalized in statuses:
            continue
        if normalized in known_names:
            continue
        if detect_leave_type(candidate, leave_types):
            continue
        return candidate

    return None
