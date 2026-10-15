"""The only repositories the phone is allowed to send to Cursor."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GitProject:
    name: str
    label: str
    url: str
    starting_ref: str


PROJECTS: dict[str, GitProject] = {
    "Gramik-CRM": GitProject(
        name="Gramik-CRM",
        label="Lens",
        url="https://github.com/18pixels/Gramik-CRM",
        starting_ref="main",
    ),
    "Gramik-CRM-Backend": GitProject(
        name="Gramik-CRM-Backend",
        label="CRM",
        url="https://github.com/18pixels/Gramik-CRM-Backend",
        starting_ref="go_live",
    ),
    "fastapi-bright-store": GitProject(
        name="fastapi-bright-store",
        label="FastAPI",
        url="https://github.com/Gramik-Agriprojunction/fastapi-bright-store",
        starting_ref="uat",
    ),
}


def get_project(name: str) -> GitProject | None:
    return PROJECTS.get(name)
