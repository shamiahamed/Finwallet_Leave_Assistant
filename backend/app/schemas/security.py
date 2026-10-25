# Security review response schemas (read-only findings, no mutations).
from pydantic import BaseModel, Field


class SecurityFinding(BaseModel):
    id: str = Field(description="Stable machine-readable finding identifier.")
    title: str
    severity: str = Field(description="high | medium | low | info")
    category: str = Field(description="configuration | secrets | input_validation | exposure | cors")
    evidence: str
    recommendation: str


class SecurityReviewResponse(BaseModel):
    status: str = "ok"
    environment: str
    checks_run: int = Field(description="Number of independent checks executed.")
    summary: dict[str, int] = Field(
        default_factory=dict, description="Finding counts keyed by severity."
    )
    findings: list[SecurityFinding] = Field(default_factory=list)
