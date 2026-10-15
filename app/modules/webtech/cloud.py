"""Start a Cursor cloud agent on a GitHub repo. The repo is not copied here."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.modules.webtech.catalog import GitProject
from app.modules.webtech.errors import WebtechError

_WORKSPACE = Path(__file__).resolve().parents[3]
_client: Any = None
_client_lock = asyncio.Lock()
_agents: dict[str, str] = {}


def _safe_error(exc: Exception) -> str:
    text = str(getattr(exc, "message", "") or exc)
    lowered = text.lower()
    if any(marker in lowered for marker in ("crsr_", "cursor_", "akia", "bearer ")):
        return "Cursor agent failed to start"
    return text[:300] or "Cursor agent failed to start"


async def cursor_client() -> Any:
    global _client
    async with _client_lock:
        if _client is None:
            from cursor_sdk import AsyncClient

            _client = await AsyncClient.launch_bridge(
                workspace=_WORKSPACE,
                allow_api_key_env_fallback=False,
            )
        return _client


async def close_cursor_client() -> None:
    global _client
    async with _client_lock:
        client = _client
        _client = None
    if client is not None:
        await client.aclose()


def _task(project: GitProject, prompt: str) -> str:
    return (
        f"Work only in the {project.label} repository ({project.url}), "
        f"starting from {project.starting_ref}. "
        "Put the change on a new branch and open a pull request. "
        "Do not push main, go_live, or live directly. "
        "Do not print secrets, tokens, or environment values.\n\n"
        f"{prompt}"
    )


def _pr_url(result: Any) -> str:
    git = getattr(result, "git", None)
    branches = getattr(git, "branches", ()) or ()
    for branch in branches:
        url = getattr(branch, "pr_url", "") or ""
        if url:
            return url
    return ""


async def _send(agent: Any, project: GitProject, prompt: str, image: dict[str, str] | None) -> Any:
    from cursor_sdk import SDKImage, UserMessage

    task = _task(project, prompt)
    if image:
        message = UserMessage(
            text=task,
            images=[SDKImage.data_image(image["data"], image["mimeType"])],
        )
        run = await agent.send(message)
    else:
        run = await agent.send(task)
    return await run.wait()


async def run_cloud_chat(
    *,
    project: GitProject,
    prompt: str,
    api_key: str,
    model: str,
    image: dict[str, str] | None = None,
) -> dict[str, str | None]:
    from cursor_sdk import (
        AgentOptions,
        CloudAgentOptions,
        CloudRepository,
        CursorAgentError,
        IntegrationNotConnectedError,
    )

    client = await cursor_client()
    cloud = CloudAgentOptions(
        repos=[CloudRepository(url=project.url, starting_ref=project.starting_ref)],
        auto_create_pr=True,
        skip_reviewer_request=True,
        work_on_current_branch=False,
    )
    agent_id = _agents.get(project.name)
    try:
        if agent_id:
            try:
                agent = await client.agents.resume(agent_id, AgentOptions(api_key=api_key))
            except CursorAgentError:
                agent_id = None
                _agents.pop(project.name, None)
                agent = await client.agents.create(
                    model=model,
                    api_key=api_key,
                    name=f"webtech-{project.label}",
                    cloud=cloud,
                )
        else:
            agent = await client.agents.create(
                model=model,
                api_key=api_key,
                name=f"webtech-{project.label}",
                cloud=cloud,
            )
        _agents[project.name] = agent.agent_id
        try:
            result = await _send(agent, project, prompt, image)
        finally:
            await agent.close()
    except IntegrationNotConnectedError as exc:
        help_url = getattr(exc, "help_url", "") or ""
        detail = "Cursor is not connected to GitHub for this repository"
        if help_url.startswith("https://cursor.com"):
            detail = f"{detail}. Connect it at {help_url}"
        raise WebtechError(502, detail) from exc
    except CursorAgentError as exc:
        raise WebtechError(502, _safe_error(exc)) from exc
    except WebtechError:
        raise
    except Exception as exc:
        raise WebtechError(502, _safe_error(exc)) from exc

    text = str(getattr(result, "result", "") or "")
    pr_url = _pr_url(result)
    if pr_url:
        text = f"{text}\n\nPull request: {pr_url}".strip()
    status = str(getattr(result, "status", "") or "finished")
    return {
        "status": status,
        "response": text,
        "project": project.name,
        "run_id": getattr(result, "id", None),
        "agent_id": agent.agent_id,
    }
