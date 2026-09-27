from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.session import check_database_connection

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", debug=settings.debug)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


@app.get("/ready", tags=["system"])
async def readiness() -> JSONResponse:
    try:
        await check_database_connection()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "database": "unavailable"},
        )
    return JSONResponse(content={"status": "ready", "database": "available"})
