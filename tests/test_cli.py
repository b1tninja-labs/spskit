from __future__ import annotations

import http.client
import json
import pathlib
import subprocess
import sys
import urllib.error

import pytest

from spskit.cli import _TryingHTTPSConnection, run, urllib_exchange
from spskit.login_start import LoginError
from spskit.verify import parse_challenge

VERIFIER = "b" * 43
REDIRECT = "https://www.acdelcotds.com/#code=example-authorization-code"

CHALLENGE = {
    "state": "verificationRequired",
    "codeLength": 8,
    "continuationToken": "continue-1",
    "_links": {"verify": {"href": "/tenant/verify"}},
}


def test_verify_prompts_and_reports_continue(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(
        "TDS_USERNAME=person\nTDS_PASSWORD=secret\nSPS_DOWNLOAD_DIR=" + str(tmp_path / "out") + "\n",
        encoding="utf-8",
    )
    prompts: list[str] = []

    def exchange(method, url, body, headers):
        assert method == "POST"
        assert headers["accept"] == "application/json"
        assert url == "https://gmb2bciamprod.ciamlogin.com/tenant/verify"
        assert json.loads(body)["otp"] == "abcd1234"
        return 200, json.dumps({"state": "continue"}).encode()

    def reader(prompt: str) -> str:
        prompts.append(prompt)
        return "abcd1234"

    code = run(["--env", str(env), "verify"], exchange, reader, json.dumps(CHALLENGE))
    assert code == 0
    assert prompts
    assert "8" in prompts[0]
    assert "continue" in capsys.readouterr().out
    parse_challenge(CHALLENGE)


def test_an_expired_session_is_reported_without_prompting(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("SPS_DOWNLOAD_DIR=" + str(tmp_path / "out") + "\n", encoding="utf-8")

    def exchange(method, url, body, headers):
        assert method == "GET"
        assert body is None
        assert "accept" in headers
        assert url.endswith("/permissions")
        return 401, b""

    code = run(["--env", str(env), "modules", "--id", "25"], exchange, lambda _prompt: "nope")
    assert code == 2
    assert "expired" in capsys.readouterr().err


def test_token_command_writes_the_token_and_does_not_print_it(tmp_path, capsys):
    token_file = tmp_path / "token.txt"
    env = tmp_path / ".env"
    env.write_text(
        "SPS_DOWNLOAD_DIR="
        + str(tmp_path / "out")
        + "\nTDS_CODE_VERIFIER="
        + VERIFIER
        + "\nTDS_TOKEN_FILE="
        + str(token_file)
        + "\nTDS_PASSWORD=stored-password\n",
        encoding="utf-8",
    )

    def exchange(method, url, body, headers):
        assert method == "POST"
        if url.endswith("/token"):
            assert b"stored-password" not in body
            return 200, json.dumps({"token_type": "Bearer", "access_token": "access-token-value-0001"}).encode()
        assert body == b""
        assert headers["Origin"] == "https://www.acdelcotds.com"
        assert headers["X-EEID-Access-Token"] == "access-token-value-0001"
        return 200, b"{}"

    code = run(["--env", str(env), "token", "--redirect", REDIRECT], exchange)
    assert code == 0
    assert "access-token-value-0001" not in capsys.readouterr().out
    assert json.loads(token_file.read_text(encoding="utf-8"))["access_token"] == "access-token-value-0001"


def test_session_prompts_for_the_emailed_token_and_later_commands_send_it(tmp_path, capsys):
    env = tmp_path / ".env"
    download = tmp_path / "out"
    env.write_text("SPS_DOWNLOAD_DIR=" + str(download) + "\n", encoding="utf-8")
    emailed = "access-token-from-email"

    def reader(prompt: str) -> str:
        assert "access token" in prompt
        return emailed

    code = run(["--env", str(env), "session"], lambda *_args: (0, b""), reader)
    assert code == 0
    assert emailed not in capsys.readouterr().out
    saved = json.loads((download / "session.json").read_text(encoding="utf-8"))
    assert saved == {"access_token": emailed}

    def exchange(method, url, body, headers):
        assert method == "GET"
        assert url.endswith("/permissions")
        assert body is None
        assert headers["authorization"] == "Bearer " + emailed
        return 200, json.dumps(
            {
                "resourceVersions": [
                    {
                        "cdlResourceId": "25",
                        "cdlResourceName": "Example",
                        "cdlResourceDescription": "A module",
                        "cdlResourceTypeCode": "SOFTWARE",
                        "versionNumber": "1",
                    }
                ]
            }
        ).encode()

    code = run(["--env", str(env), "modules", "--id", "25"], exchange, lambda _prompt: "not-asked")
    assert code == 0
    assert emailed not in capsys.readouterr().out


def test_python_m_spskit_reaches_the_cli():
    completed = subprocess.run(
        [sys.executable, "-m", "spskit", "--help"],
        cwd=pathlib.Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "session" in completed.stdout
    assert "code" in completed.stdout


def test_a_closed_connection_is_retried(monkeypatch):
    calls = 0

    class Response:
        status = 200

        def read(self) -> bytes:
            return b"ok"

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def open_request(_request: object, timeout: int = 60) -> Response:
        nonlocal calls
        del timeout
        calls += 1
        if calls < 3:
            raise urllib.error.URLError(ConnectionResetError(10054, "reset"))
        return Response()

    monkeypatch.setattr("spskit.cli._OPENER.open", open_request)
    delays: list[float] = []
    status, body = urllib_exchange("GET", "https://ciam.example/login", None, {}, sleeper=delays.append)
    assert status == 200
    assert body == b"ok"
    assert delays == [1.0, 2.0]
    assert calls == 3


def test_a_closed_connection_stops_after_the_backoff(monkeypatch):
    def open_request(_request: object, timeout: int = 60) -> object:
        del timeout
        raise urllib.error.URLError(ConnectionResetError(10054, "reset"))

    monkeypatch.setattr("spskit.cli._OPENER.open", open_request)
    delays: list[float] = []
    with pytest.raises(LoginError, match="closed the connection"):
        urllib_exchange("GET", "https://ciam.example/login", None, {}, sleeper=delays.append)
    assert delays == [1.0, 2.0, 4.0]


def test_the_access_token_header_keeps_its_spelling(monkeypatch):
    seen: list[object] = []

    def capture(_self: object, header: object, *_values: object) -> None:
        seen.append(header)

    monkeypatch.setattr(http.client.HTTPSConnection, "putheader", capture)
    _TryingHTTPSConnection("backend.example").putheader("X-Eeid-Access-Token", "value")
    assert seen == ["X-EEID-Access-Token"]


def test_a_saved_token_retries_the_backend_without_a_new_code(tmp_path, capsys):
    token_file = tmp_path / "session.json"
    env = tmp_path / ".env"
    env.write_text(
        "SPS_DOWNLOAD_DIR=" + str(tmp_path / "out") + "\nTDS_TOKEN_FILE=" + str(token_file) + "\n",
        encoding="utf-8",
    )
    token_file.write_text(
        json.dumps(
            {
                "access_token": "access-token-value-0001",
                "backend_pending": True,
                "stay": {"url": "https://ciam.example/kmsi"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def exchange(method, url, body, headers):
        assert method == "POST"
        assert "/api/v1/login" in url
        assert body == b""
        assert headers["X-EEID-Access-Token"] == "access-token-value-0001"
        return 200, b"{}"

    code = run(["--env", str(env), "code"], exchange, lambda _prompt: "nope")
    assert code == 0
    saved = json.loads(token_file.read_text(encoding="utf-8"))
    assert saved["access_token"] == "access-token-value-0001"
    assert "backend_pending" not in saved
    assert "stay" not in saved
    assert "access-token-value-0001" not in capsys.readouterr().out
