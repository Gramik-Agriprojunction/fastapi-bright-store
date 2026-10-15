import hmac

from fastapi import Header

from app.core.key_vault import KeyVaultError, load_webtech_keys
from app.modules.webtech.errors import WebtechError


def _tokens_match(provided: str, expected: str) -> bool:
    left = provided.encode()
    right = expected.encode()
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def require_bridge_token(authorization: str | None = Header(default=None)) -> None:
    try:
        keys = load_webtech_keys()
    except KeyVaultError as exc:
        raise WebtechError(503, "WebTech keys are not configured") from exc
    expected = keys.get("WEBTECH_BRIDGE_TOKEN", "").strip()
    if not expected:
        raise WebtechError(503, "Bridge token is not configured")
    provided = ""
    if authorization and authorization.startswith("Bearer "):
        provided = authorization[7:].strip()
    if not provided or not _tokens_match(provided, expected):
        raise WebtechError(401, "Invalid bridge token")


def cursor_credentials() -> tuple[str, str]:
    try:
        keys = load_webtech_keys()
    except KeyVaultError as exc:
        raise WebtechError(503, "WebTech keys are not configured") from exc
    api_key = keys.get("CURSOR_API_KEY", "").strip()
    model = keys.get("WEBTECH_MODEL", "").strip() or "composer-2.5"
    if not api_key:
        raise WebtechError(503, "Cursor key is not configured")
    return api_key, model
