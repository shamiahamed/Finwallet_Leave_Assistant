import re
from calendar import monthrange
from datetime import date

import pandas as pd

from app.exceptions.errors import InvalidFilterError

_MONTH_NAMES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_MONTH_FIRST_RE = re.compile(
    rf"\b({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{{4}}))?\b",
    re.IGNORECASE,
)
_DAY_FIRST_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH})(?:\s*,?\s*(\d{{4}}))?\b",
    re.IGNORECASE,
)
_MONTH_YEAR_RE = re.compile(rf"\b({_MONTH})\s+(\d{{4}})\b", re.IGNORECASE)
_MONTH_ONLY_RE = re.compile(rf"\b({_MONTH})\b", re.IGNORECASE)
_BEFORE_RE = re.compile(r"\b(?:before|until|by|up\s+to)\b", re.IGNORECASE)
_AFTER_RE = re.compile(r"\b(?:after|since|from|starting)\b", re.IGNORECASE)
_SUBMISSION_RE = re.compile(
    r"\b(?:submitted|submission(?:\s+date)?|date\s+submitted|"
    r"application\s+date|applied\s+on|requested\s+on)\b",
    re.IGNORECASE,
)


def validate_date_range(start: date | None, end: date | None) -> None:
    if start and end and start > end:
        raise InvalidFilterError("start_date must not be later than end_date.")


def overlap_mask(
    starts: pd.Series, ends: pd.Series, range_start: date | None, range_end: date | None
) -> pd.Series:
    mask = pd.Series(True, index=starts.index)
    if range_start:
        mask &= ends >= pd.Timestamp(range_start)
    if range_end:
        mask &= starts <= pd.Timestamp(range_end)
    return mask


def asks_submission_date(question: str) -> bool:
    return bool(_SUBMISSION_RE.search(question or ""))


def _month_period(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _month_number(value: str) -> int:
    return _MONTH_NAMES[value.lower()]


def _is_modal_may(text: str, match: re.Match) -> bool:
    before = text[max(0, match.start() - 20):match.start()]
    after = text[match.end():match.end() + 20]
    if re.search(
        r"\b(?:in|during|for|of|by|before|after|since|from|until|to|through|"
        r"early|late|mid)\s*$",
        before,
        re.IGNORECASE,
    ):
        return False
    if re.search(
        r"\b(?:who|that|which|they|we|you|i|he|she|it|employees?|staff|"
        r"could|might|should|can|would|will)\s*$",
        before,
        re.IGNORECASE,
    ):
        return True
    return bool(
        re.match(
            r"\s+(?:be|have|has|had|need|want|take|apply|get|not)\b",
            after,
            re.IGNORECASE,
        )
    )


def _month_tokens(
    text: str,
    today: date,
) -> list[tuple[int, int, date, date, bool]]:
    tokens: list[tuple[int, int, date, date, bool]] = []

    for match in _ISO_RE.finditer(text):
        try:
            value = date.fromisoformat(match.group(0))
        except ValueError as exc:
            raise InvalidFilterError(
                f"Invalid date '{match.group(0)}'. Use YYYY-MM-DD."
            ) from exc
        tokens.append((match.start(), match.end(), value, value, False))

    for match in _MONTH_FIRST_RE.finditer(text):
        year = int(match.group(3) or today.year)
        month = _month_number(match.group(1))
        day = int(match.group(2))
        try:
            value = date(year, month, day)
        except ValueError as exc:
            raise InvalidFilterError(
                f"Invalid date '{match.group(0)}'."
            ) from exc
        tokens.append((match.start(), match.end(), value, value, False))

    for match in _DAY_FIRST_RE.finditer(text):
        year = int(match.group(3) or today.year)
        month = _month_number(match.group(2))
        day = int(match.group(1))
        try:
            value = date(year, month, day)
        except ValueError as exc:
            raise InvalidFilterError(
                f"Invalid date '{match.group(0)}'."
            ) from exc
        tokens.append((match.start(), match.end(), value, value, False))

    for match in _MONTH_YEAR_RE.finditer(text):
        month = _month_number(match.group(1))
        start, end = _month_period(int(match.group(2)), month)
        tokens.append((match.start(), match.end(), start, end, True))

    for match in _MONTH_ONLY_RE.finditer(text):
        if match.group(1).lower() == "may" and _is_modal_may(text, match):
            continue
        month = _month_number(match.group(1))
        start, end = _month_period(today.year, month)
        tokens.append((match.start(), match.end(), start, end, True))

    selected: list[tuple[int, int, date, date, bool]] = []
    for token in sorted(tokens, key=lambda item: (item[0], -(item[1] - item[0]))):
        start, end = token[0], token[1]
        if any(start < kept[1] and end > kept[0] for kept in selected):
            continue
        selected.append(token)

    return sorted(selected, key=lambda item: item[0])


def detect_leave_date_range(
    question: str,
    today: date | None = None,
) -> tuple[date | None, date | None] | None:
    text = (question or "").strip()
    if not text:
        return None

    current = today or date.today()
    lowered = text.lower()

    if re.search(r"\b(?:this|current)\s+month\b", lowered):
        return _month_period(current.year, current.month)

    if re.search(r"\blast\s+month\b", lowered):
        month = current.month - 1 or 12
        year = current.year if current.month > 1 else current.year - 1
        return _month_period(year, month)

    tokens = _month_tokens(text, current)
    if not tokens:
        return None

    if len(tokens) >= 2:
        start = tokens[0][2]
        end = tokens[1][3]
        validate_date_range(start, end)
        return start, end

    start, end, is_period = tokens[0][2], tokens[0][3], tokens[0][4]
    if is_period:
        return start, end
    if _BEFORE_RE.search(text):
        return None, end
    if _AFTER_RE.search(text):
        return start, None
    return start, end
