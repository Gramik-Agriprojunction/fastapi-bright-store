import asyncio
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.modules.webtechAIAgent.service import ask_webtech_agent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webtech-ai-agent", tags=["webtech-ai-agent"])


class AskIn(BaseModel):
    message: str = ""
    context: dict[str, Any] | None = None


def _envelope(ok: bool, status_code: int, msg: str, data: object) -> dict[str, object]:
    return {"status": ok, "statusCode": status_code, "msg": msg, "data": data}


@router.post("")
async def ask(body: AskIn) -> JSONResponse:
    message = body.message.strip()
    if not message:
        return JSONResponse(
            status_code=400,
            content=_envelope(False, 400, "Message likho", None),
        )
    try:
        data = await asyncio.to_thread(ask_webtech_agent, message, body.context or {})
    except Exception:
        logger.exception("WebtechAgent analysis failed")
        return JSONResponse(
            status_code=500,
            content=_envelope(False, 500, "WebtechAgent analysis nahi kar paya", None),
        )
    return JSONResponse(status_code=200, content=_envelope(True, 200, "OK", data))
