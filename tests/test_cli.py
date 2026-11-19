from __future__ import annotations

import json

from spskit.cli import run
from spskit.verify import parse_challenge

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
