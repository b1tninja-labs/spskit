from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from spskit.cli import run
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
        assert body is None
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
