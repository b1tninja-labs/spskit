from __future__ import annotations

import json
from pathlib import Path

import pytest

from spskit.cli import run
from spskit.client import (
    child_token,
    launcher_browser_bearer,
    parse_child_token,
    request_vin_access_form,
)
from spskit.config import Settings
from spskit.spsinfo import SpsInfoError

ACCESS = "eeid-access-token-value-0001"
APIM = "header.payload.signature"
SLOT = "7"
BEARER = "browser-access-token-value-0001"
TECHPD_FORM = """<!DOCTYPE html><html><head><title>SPOREF Redirection</title></head><body>
<form method="POST" action="https://gateway.example/authorization/oauth/user/sporef/ui">
<input type="hidden" name="appParm" value="techpd">
<input type="hidden" name="ticket" value="sample-ticket">
</form></body></html>
"""


def _settings(directory: Path) -> Settings:
    return Settings(
        username="",
        password="",
        gateway="https://gateway.example",
        ciam="https://ciam.example",
        access_token=ACCESS,
        download_dir=directory,
        backend="https://backend.example",
    )


def test_the_child_token_call_keeps_only_the_token_values(tmp_path: Path):
    settings = _settings(tmp_path)
    calls: list[tuple[str, str, dict[str, str]]] = []

    def exchange(method: str, url: str, body: bytes | None, headers: dict[str, str]) -> tuple[int, bytes]:
        calls.append((method, url, dict(headers)))
        assert method == "GET"
        assert url == "https://gateway.example/oauth/user/token/child?tokenType=tum2"
        assert body is None
        assert headers["accept"] == "application/json"
        assert headers["authorization"] == f"Bearer {BEARER}"
        return 200, json.dumps(
            {
                "accessToken": {"tokenValue": "access-token-value-0001", "expiresAt": "2099-01-01T00:00:00"},
                "refreshToken": {"tokenValue": "refresh-token-value-0001", "expiresAt": "2099-01-01T00:00:00"},
                "extra": "dropped",
            }
        ).encode()

    pair = child_token(settings, BEARER, exchange, "tum2")
    assert pair.access_token == "access-token-value-0001"
    assert pair.refresh_token == "refresh-token-value-0001"
    assert pair == parse_child_token(
        {
            "accessToken": {"tokenValue": "access-token-value-0001", "expiresAt": "ignored"},
            "refreshToken": {"tokenValue": "refresh-token-value-0001", "expiresAt": "ignored"},
            "extra": "dropped",
        }
    )
    assert len(calls) == 1


def test_the_vin_access_form_uses_the_same_eeid_headers_as_sps(tmp_path: Path):
    settings = _settings(tmp_path)
    calls: list[tuple[str, str, dict[str, str]]] = []

    def exchange(method: str, url: str, body: bytes | None, headers: dict[str, str]) -> tuple[int, bytes]:
        calls.append((method, url, dict(headers)))
        if url.endswith("/api/tds-backend"):
            assert method == "GET"
            return 200, APIM.encode()
        assert method == "GET"
        assert url == f"https://backend.example/api/v1/subscriptions/vin/access/{SLOT}"
        assert headers["Authorization"] == f"Bearer {APIM}"
        assert headers["X-EEID-Access-Token"] == ACCESS
        assert body is None
        return 200, TECHPD_FORM.encode()

    form = request_vin_access_form(settings, SLOT, exchange)
    assert form.fields[0] == ("appParm", "techpd")
    assert len(calls) == 2


def test_the_launcher_handoff_posts_the_vin_form(tmp_path: Path):
    settings = _settings(tmp_path)
    seen: list[tuple[str, str]] = []

    def exchange(method: str, url: str, body: bytes | None, _headers: dict[str, str]) -> tuple[int, bytes]:
        if url.endswith("/api/tds-backend"):
            return 200, APIM.encode()
        if url.endswith(f"/vin/access/{SLOT}"):
            seen.append((method, url))
            return 200, TECHPD_FORM.encode()
        if url.endswith("/sporef/ui"):
            seen.append((method, url))
            assert body is not None
            assert b"appParm=techpd" in body
            return 200, b"<html></html>"
        raise AssertionError(url)

    bearer = launcher_browser_bearer(settings, SLOT, exchange, browser_access_token=BEARER)
    assert bearer == BEARER
    assert seen == [
        ("GET", f"https://backend.example/api/v1/subscriptions/vin/access/{SLOT}"),
        ("POST", "https://gateway.example/authorization/oauth/user/sporef/ui"),
    ]


def test_launch_writes_the_child_token_and_does_not_print_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    download = tmp_path / "out"
    download.mkdir()
    session = download / "session.json"
    session.write_text(json.dumps({"access_token": ACCESS}) + "\n", encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text(
        "SPS_DOWNLOAD_DIR="
        + str(download)
        + "\nTDS_GATEWAY=https://gateway.example\nTDS_BACKEND=https://backend.example\n",
        encoding="utf-8",
    )
    child_access = "access-token-value-0001"
    child_refresh = "refresh-token-value-0001"

    def exchange(method: str, url: str, body: bytes | None, headers: dict[str, str]) -> tuple[int, bytes]:
        if url.endswith("/api/tds-backend"):
            return 200, APIM.encode()
        if url.endswith(f"/vin/access/{SLOT}"):
            assert headers["X-EEID-Access-Token"] == ACCESS
            return 200, TECHPD_FORM.encode()
        if url.endswith("/sporef/ui"):
            assert body is not None
            assert b"appParm=techpd" in body
            return 200, b"<html></html>"
        if url.endswith("/oauth/user/token/child?tokenType=tum2"):
            assert headers["authorization"] == "Bearer " + BEARER
            assert method == "GET"
            return 200, json.dumps(
                {
                    "accessToken": {"tokenValue": child_access},
                    "refreshToken": {"tokenValue": child_refresh},
                }
            ).encode()
        raise AssertionError(url)

    def browser_bearer(_exchange: object, access_token: str = "") -> str:
        return access_token or BEARER

    monkeypatch.setattr("spskit.client.browser_access_bearer", browser_bearer)
    code = run(["--env", str(env), "launch", "--slot", SLOT], exchange)
    assert code == 0
    saved = json.loads(session.read_text(encoding="utf-8"))
    assert saved["access_token"] == ACCESS
    assert saved["launcher_access_token"] == child_access
    assert saved["launcher_refresh_token"] == child_refresh
    printed = capsys.readouterr().out
    assert str(session) in printed
    assert child_access not in printed
    assert child_refresh not in printed
    assert BEARER not in printed


def test_child_token_refuses_an_empty_bearer(tmp_path: Path):
    settings = _settings(tmp_path)

    def exchange(_method: str, _url: str, _body: bytes | None, _headers: dict[str, str]) -> tuple[int, bytes]:
        raise AssertionError("no call")

    with pytest.raises(SpsInfoError, match="did not return a session"):
        child_token(settings, "", exchange, "tum2")
