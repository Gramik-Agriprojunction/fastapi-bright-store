from fastapi.testclient import TestClient

from app.main import app
from app.modules.webtech.catalog import GitProject

client = TestClient(app)
TOKEN = "bridge-token"
KEYS = {
    "WEBTECH_BRIDGE_TOKEN": TOKEN,
    "CURSOR_API_KEY": "cursor_test_value",
    "WEBTECH_MODEL": "composer-2.5",
}


def _patch_keys(monkeypatch) -> None:
    monkeypatch.setattr("app.modules.webtech.auth.load_webtech_keys", lambda: KEYS)


def test_chat_rejects_missing_token(monkeypatch) -> None:
    _patch_keys(monkeypatch)

    response = client.post("/api/v1/webtech/chat", json={"prompt": "hi", "project": "Gramik-CRM"})

    assert response.status_code == 401
    assert "cursor_test_value" not in response.text
    assert TOKEN not in response.text


def test_chat_rejects_unknown_project(monkeypatch) -> None:
    _patch_keys(monkeypatch)

    response = client.post(
        "/api/v1/webtech/chat",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"prompt": "hi", "project": "webtech_editor"},
    )

    assert response.status_code == 403


def test_chat_starts_cloud_agent_for_allowed_repo(monkeypatch) -> None:
    _patch_keys(monkeypatch)
    seen: dict[str, object] = {}

    async def fake_run(**kwargs):
        seen.update(kwargs)
        return {
            "status": "finished",
            "response": "opened a pull request",
            "project": kwargs["project"].name,
            "run_id": "run-1",
            "agent_id": "bc-1",
        }

    monkeypatch.setattr("app.modules.webtech.router.run_cloud_chat", fake_run)

    response = client.post(
        "/api/v1/webtech/chat",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"prompt": "rename the title", "project": "Gramik-CRM"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "opened a pull request"
    assert body["project"] == "Gramik-CRM"
    assert "cursor_test_value" not in response.text
    project = seen["project"]
    assert isinstance(project, GitProject)
    assert project.url == "https://github.com/18pixels/Gramik-CRM"
    assert project.starting_ref == "main"
    assert seen["api_key"] == "cursor_test_value"


def test_projects_lists_three_repos(monkeypatch) -> None:
    _patch_keys(monkeypatch)

    response = client.get(
        "/api/v1/webtech/projects",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["projects"]]
    assert names == ["Gramik-CRM", "Gramik-CRM-Backend", "fastapi-bright-store"]
