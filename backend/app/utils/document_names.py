"""Shared normalisation and matching rules for uploaded document names.

A document name reaches the backend in several shapes: the name stored at
upload time, the name a user types in a question, and the same name after the
operating system has appended a copy suffix such as " (1)". Every name
comparison goes through this module so the query side and the retrieval side
can never disagree about what counts as the same document.

The module is deliberately dependency-free: it works on plain strings and
name lists, so it can be imported from the query helpers, the retrieval
service, and the tests without creating an import cycle.
"""

import re

# Extensions that mark a token in a question as a file name mention.
DOCUMENT_EXTENSIONS = (".pdf", ".txt", ".md", ".docx", ".doc")

_EXTENSION_PATTERN = re.compile(r"\.(pdf|txt|md|docx?)$", re.IGNORECASE)
_COPY_SUFFIX_PATTERN = re.compile(r"\s*\(\d+\)$")
_SEPARATOR_PATTERN = re.compile(r"[\s_\-]+")

# A file name mention: a word, optionally followed by a copy suffix, followed
# by a known document extension. Spaces are allowed only inside the copy
# suffix, so "Policy.pdf" is captured as a whole instead of as a bare word.
_MENTION_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_\-]*(?:\s*\(\d+\))?\.(?:pdf|txt|md|docx?)\b",
    re.IGNORECASE,
)


def normalize_document_key(name: str) -> str:
    
    
    text = (name or "").strip().lower()

    if not text:
        return ""

    text = _EXTENSION_PATTERN.sub("", text)
    text = _SEPARATOR_PATTERN.sub(" ", text)

    return text.strip()


def extract_document_mentions(question: str) -> list[str]:
    """Return the file names mentioned in a question, in order of appearance.

    Only a token that carries a document extension counts as a mention, so
    "What is the leave policy?" never resolves to a document named
    "Policy.pdf". Repeated mentions of the same name are collapsed.
    """
    if not question:
        return []

    mentions: list[str] = []
    seen: set[str] = set()

    for match in _MENTION_PATTERN.finditer(question):
        name = match.group(0).strip(" .,;:")

        if not name:
            continue

        key = name.lower()

        if key in seen:
            continue

        seen.add(key)
        mentions.append(name)

    return mentions


def rank_name_matches(
    mentioned_name: str,
    candidate_names,
) -> tuple[list[str], list[str], list[str]]:
    """Split candidate names into the tiers that can match a mention.

    The tiers are ordered by how specific the match is:

    1. ``exact`` - the full name matches case-insensitively.
    2. ``normalized`` - the normalised keys are equal, which covers extension
       differences and separator differences.
    3. ``suffix`` - two sub-cases:
       a. The candidate key ends with the mention key on a word boundary,
          which covers "Policy.pdf" matching "Sample Leave Policy.pdf".
       b. The candidate key starts with the mention key followed by a copy
          suffix " (N)", which covers "Sample_Leave_Policy.pdf" matching
          "Sample_Leave_Policy (1).pdf".

    Each tier is returned as its own list so the caller can prefer the most
    specific tier and can report an ambiguity when a tier holds more than
    one candidate.
    """
    wanted = (mentioned_name or "").strip().lower()
    key = normalize_document_key(mentioned_name)

    exact: list[str] = []
    normalized: list[str] = []
    suffix: list[str] = []

    for candidate in candidate_names:
        name = str(candidate).strip()

        if not name:
            continue

        if name.lower() == wanted:
            exact.append(name)
            continue

        candidate_key = normalize_document_key(name)

        if not candidate_key or not key:
            continue

        if candidate_key == key:
            normalized.append(name)
        elif candidate_key.endswith(" " + key):
            # Short typed name matches a longer stored name (suffix prefix).
            suffix.append(name)
        elif re.match(
            r"\(\d+\)$",
            candidate_key[len(key):].strip(),
        ) and candidate_key.startswith(key):
            # Typed base name matches a copy-suffix variant stored in the
            # registry (e.g. "Sample_Leave_Policy.pdf" → "Sample_Leave_Policy (1).pdf").
            suffix.append(name)

    return exact, normalized, suffix
