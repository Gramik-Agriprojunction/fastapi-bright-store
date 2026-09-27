from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import check_database_connection

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


@router.get("/ready")
async def readiness() -> JSONResponse:
    try:
        await check_database_connection()
    except SQLAlchemyError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "database": "unavailable"},
        )
    return JSONResponse(content={"status": "ready", "database": "available"})
