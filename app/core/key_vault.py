"""Unwrap WebTech Mac-bridge keys stored in app/html/webtech-keys.html.

The HTML file holds ciphertext only. This module is what the API process uses
to read those keys. Nothing here is returned on an HTTP route.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from functools import lru_cache
from pathlib import Path

_VAULT_KEY = base64.b64decode("0BPo/V5GhtE8Nj5vCOG7dqyOSJxO0R1fpaAtMbDmuB8=")
_HTML_PATH = Path(__file__).resolve().parents[1] / "html" / "webtech-keys.html"
_NONCE_LEN = 16
_MAC_LEN = 32


class KeyVaultError(RuntimeError):
    pass


def _keystream(key: bytes, nonce: bytes, size: int) -> bytes:
    chunks: list[bytes] = []
    counter = 0
    produced = 0
    while produced < size:
        block = hmac.new(
            key,
            nonce + counter.to_bytes(4, "big"),
            hashlib.sha256,
        ).digest()
        chunks.append(block)
        produced += len(block)
        counter += 1
    return b"".join(chunks)[:size]


def seal(payload: dict[str, str], key: bytes | None = None) -> str:
    """Encrypt a string map. Returns URL-safe base64 ciphertext."""
    secret = key if key is not None else _VAULT_KEY
    if len(secret) < 32:
        raise KeyVaultError("Vault key must be at least 32 bytes")
    raw = json.dumps(payload, separators=(",", ":")).encode()
    nonce = os.urandom(_NONCE_LEN)
    stream = _keystream(secret, nonce, len(raw))
    cipher = bytes(left ^ right for left, right in zip(raw, stream, strict=True))
    mac = hmac.new(secret, nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + mac + cipher).decode()


def open_sealed(ciphertext: str, key: bytes | None = None) -> dict[str, str]:
    secret = key if key is not None else _VAULT_KEY
    try:
        blob = base64.urlsafe_b64decode(ciphertext.encode())
    except (ValueError, TypeError) as exc:
        raise KeyVaultError("Key file is not valid ciphertext") from exc
    if len(blob) < _NONCE_LEN + _MAC_LEN:
        raise KeyVaultError("Key file is too short")
    nonce = blob[:_NONCE_LEN]
    mac = blob[_NONCE_LEN : _NONCE_LEN + _MAC_LEN]
    cipher = blob[_NONCE_LEN + _MAC_LEN :]
    expected = hmac.new(secret, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise KeyVaultError("Key file failed integrity check")
    stream = _keystream(secret, nonce, len(cipher))
    raw = bytes(left ^ right for left, right in zip(cipher, stream, strict=True))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise KeyVaultError("Key file did not decrypt") from exc
    if not isinstance(data, dict):
        raise KeyVaultError("Key file payload is invalid")
    for name, value in data.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise KeyVaultError("Key file payload is invalid")
    return data


def render_keys_html(ciphertext: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        "  <title>webtech keys</title>\n"
        "</head>\n"
        "<body>\n"
        f'  <pre id="webtech-keys">{ciphertext}</pre>\n'
        "</body>\n"
        "</html>\n"
    )


def ciphertext_from_html(html: str) -> str:
    marker = '<pre id="webtech-keys">'
    start = html.find(marker)
    if start < 0:
        raise KeyVaultError("HTML key file is missing its payload")
    start += len(marker)
    end = html.find("</pre>", start)
    if end < 0:
        raise KeyVaultError("HTML key file is missing its payload")
    token = html[start:end].strip()
    if not token:
        raise KeyVaultError("HTML key file is empty")
    return token


@lru_cache
def load_webtech_keys() -> dict[str, str]:
    if not _HTML_PATH.is_file():
        raise KeyVaultError(f"Missing {_HTML_PATH.name}")
    html = _HTML_PATH.read_text(encoding="utf-8")
    return open_sealed(ciphertext_from_html(html))
