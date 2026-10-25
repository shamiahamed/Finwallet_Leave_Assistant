import re

from app.exceptions.errors import InvalidEmployeeIdError

EMPLOYEE_ID_PATTERN = re.compile(r"EMP\d+")


def normalize_employee_id(raw: str) -> str:
    # Trim/upper-case an ID

    value = (raw or "").strip().upper()
    if not EMPLOYEE_ID_PATTERN.fullmatch(value):
        raise InvalidEmployeeIdError(
            "Employee IDs look like 'EMP025' (the letters EMP followed by digits)."
        )
    return value
