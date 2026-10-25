from collections.abc import Iterable

from app.exceptions.errors import InvalidFilterError


def resolve_choice(value: str, valid_values: Iterable[str], label: str) -> str:

    # A bare leave-type word is accepted too: 'sick' -> 'Sick Leave'.
    valid = sorted(set(valid_values))
    wanted = value.strip().lower()
    for candidate in valid:
        if candidate.lower() in (wanted, f"{wanted} leave"):
            return candidate
    raise InvalidFilterError(
        f"Unknown {label} '{value.strip()[:40]}'.", details={"valid_values": valid}
    )
