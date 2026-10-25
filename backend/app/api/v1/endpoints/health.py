from fastapi import APIRouter, Depends, Request

from app.api.deps import get_repository
from app.core.config import get_settings
from app.repositories.workbook_repository import WorkbookRepository
from app.schemas.leave import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Service and workbook status")
def health(
    request: Request,
    repo: WorkbookRepository = Depends(get_repository),
) -> HealthResponse:
    refresher = getattr(request.app.state, "workbook_refresh", None)
    return HealthResponse(
        status="ok",
        environment=get_settings().app_env,
        workbook_loaded=True,
        row_counts=repo.row_counts,
        workbook_refresh=refresher.status if refresher is not None else None,
    )
