from typing import Any

from pydantic import BaseModel, Field


class Evidence(BaseModel):

    worksheets: list[str] = Field(description="Worksheets the answer was computed from.")
    employee_ids: list[str] = Field(default_factory=list)
    request_ids: list[str] = Field(default_factory=list)


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable explanation.")
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error: ErrorBody
