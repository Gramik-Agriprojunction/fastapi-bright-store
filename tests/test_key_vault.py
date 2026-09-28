import base64

from app.core.key_vault import (
    ciphertext_from_html,
    load_webtech_keys,
    open_sealed,
    render_keys_html,
    seal,
)

_KEY_NAMES = {
    "CURSOR_API_KEY",
    "WEBTECH_BRIDGE_TOKEN",
    "WEBTECH_MODEL",
    "AWS_ENDPOINT_URL_S3",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "AWS_BUCKET",
}


def test_seal_round_trip() -> None:
    key = base64.b64decode("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    payload = {"CURSOR_API_KEY": "cursor_example", "WEBTECH_BRIDGE_TOKEN": "bridge-token"}
    html = render_keys_html(seal(payload, key))

    opened = open_sealed(ciphertext_from_html(html), key)

    assert opened == payload
    assert "cursor_example" not in html
    assert "bridge-token" not in html


def test_committed_html_holds_encrypted_bridge_keys() -> None:
    keys = load_webtech_keys()

    assert set(keys) == _KEY_NAMES
    assert all(value.strip() for value in keys.values())
