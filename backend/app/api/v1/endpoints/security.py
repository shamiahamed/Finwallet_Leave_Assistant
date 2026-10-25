"""Read-only security review endpoint.

Runs deterministic, in-process checks over configuration and runtime state and
returns advisory findings. It never modifies application data, never auto-fixes,
and never calls the LLM, so it is safe and always available.
"""

import logging

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.schemas.security import SecurityReviewResponse
from app.services.security_review_service import run_security_review

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Security"])


@router.get(
    "/security/review",
    response_model=SecurityReviewResponse,
    summary="Read-only security review of configuration and runtime state",
)
def security_review(request: Request) -> SecurityReviewResponse:
    settings = get_settings()
    document_registry = getattr(request.app.state, "document_registry", None)
    review = run_security_review(settings, document_registry=document_registry)
    return SecurityReviewResponse(**review.model_dump())



@router.get(
    "/security/monitoring",
    summary="Get automatic monitoring status and current findings",
)
def get_monitoring_status(request: Request) -> dict:
    monitoring = getattr(request.app.state, "monitoring", None)

    if monitoring is None:
        return {
            "monitoring_enabled": False,
            "last_scan_status": "not_started",
            "message": "Background monitoring has not started.",
        }

    return monitoring.snapshot()


@router.get(
    "/security/history",
    summary="Get recent security scan history",
)
def get_monitoring_history(request: Request) -> dict:
    monitoring = getattr(request.app.state, "monitoring", None)

    if monitoring is None:
        return {"history": []}

    state = monitoring.snapshot()
    return {"history": state["history"]}


@router.get(
    "/security/events",
    summary="Get recent security and health events",
)
def get_monitoring_events(request: Request) -> dict:
    monitoring = getattr(request.app.state, "monitoring", None)

    if monitoring is None:
        return {"events": [], "event_counts": {}}

    state = monitoring.snapshot()
    return {
        "events": state["events"],
        "event_counts": state["event_counts"],
    }
