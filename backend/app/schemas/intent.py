from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class QueryIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal[
        "employee_lookup",
        "employee_list",
        "employee_headcount",
        "leave_requests",
        "leave_balance",
        "department_balance_summary",
        "leave_policy",
        "department_summary",
        "document_question",
        "unsupported",
        "clarify",
        "greeting",
        "help",
    ]

    # Defines whose data the user wants.
    scope: Literal["single", "all", "department"] = "single"

    employee_id: str | None = None
    employee_name: str | None = None
    approval_status: str | None = None
    leave_type: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    department: str | None = None
    employment_status: str | None = None
    document_name: str | None = None
    date_mode: Literal["overlap", "start_date", "end_date"] = "overlap"
    currently_on_leave: bool = False

    @field_validator(
        "employee_id",
        "employee_name",
        "approval_status",
        "leave_type",
        "department",
        "employment_status",
        "document_name",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None

    @field_validator("employee_id")
    @classmethod
    def normalize_employee_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.upper()

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, value: date | None, info):
        start_date = info.data.get("start_date")

        if value and start_date and value < start_date:
            raise ValueError("end_date cannot be before start_date")

        return value
