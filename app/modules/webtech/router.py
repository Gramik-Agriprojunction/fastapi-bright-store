from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.modules.webtech.auth import cursor_credentials, require_bridge_token
from app.modules.webtech.catalog import PROJECTS, get_project
from app.modules.webtech.cloud import run_cloud_chat
from app.modules.webtech.errors import WebtechError

router = APIRouter(prefix="/webtech", tags=["webtech"])


class ChatImage(BaseModel):
    data: str = Field(min_length=1, max_length=8_000_000)
    mimeType: str = Field(pattern=r"(?i)^image/(png|jpeg|jpg|webp)$")


class ChatIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    project: str = Field(min_length=1, max_length=120)
    image: ChatImage | None = None


@router.get("/projects")
async def projects(_: Annotated[None, Depends(require_bridge_token)]) -> dict[str, object]:
    return {
        "projects": [
            {"name": item.name, "label": item.label} for item in PROJECTS.values()
        ]
    }


@router.post("/chat")
async def chat(
    body: ChatIn,
    _: Annotated[None, Depends(require_bridge_token)],
) -> dict[str, str | None]:
    project = get_project(body.project.strip())
    if project is None:
        raise WebtechError(403, "Only Lens, CRM, and FastAPI can be opened")
    api_key, model = cursor_credentials()
    image = body.image.model_dump() if body.image else None
    return await run_cloud_chat(
        project=project,
        prompt=body.prompt.strip(),
        api_key=api_key,
        model=model,
        image=image,
    )
