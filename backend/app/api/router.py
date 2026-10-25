from fastapi import APIRouter

from app.api.v1.endpoints import (
    chat,
    datasets,
    departments,
    documents,
    employees,
    health,
    leave,
    security,
)
from app.schemas.common import ErrorResponse

ERRORS = {
    404: {"model": ErrorResponse, "description": "Record not found"},
    409: {"model": ErrorResponse, "description": "Ambiguous request (candidates listed)"},
    422: {"model": ErrorResponse, "description": "Invalid parameter"},
    500: {"model": ErrorResponse, "description": "Unexpected server error"},
    502: {"model": ErrorResponse, "description": "LLM provider error"},
    503: {"model": ErrorResponse, "description": "LLM provider temporarily unavailable"},
}

api_router = APIRouter(prefix="/api/v1", responses=ERRORS)
for module in (health, employees, leave, departments, chat, datasets, documents, security):
    api_router.include_router(module.router)
