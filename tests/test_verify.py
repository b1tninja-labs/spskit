from __future__ import annotations

import json

import pytest

from spskit.client import submit_code
from spskit.config import Settings
from spskit.verify import VerificationError, otp_message, parse_challenge, prompt_code

CHALLENGE = {
    "state": "verificationRequired",
    "codeLength": 8,
    "continuationToken": "continue-1",
    "_links": {"verify": {"href": "/tenant/api/v1.0/auth/methods/email/method/verify"}},
}


def test_a_challenge_keeps_the_path_the_host_named():
    parsed = parse_challenge(CHALLENGE)
    assert parsed.code_length == 8
    assert parsed.verify_path.endswith("/verify")
    assert otp_message(parsed, "abcd1234") == {"continuationToken": "continue-1", "otp": "abcd1234"}


def test_a_code_of_the_wrong_length_is_refused():
    parsed = parse_challenge(CHALLENGE)
    with pytest.raises(VerificationError):
        prompt_code(parsed, lambda _prompt: "short")


def test_an_off_host_verify_link_is_refused():
    bad = dict(CHALLENGE)
    bad["_links"] = {"verify": {"href": "https://evil.example/verify"}}
    with pytest.raises(VerificationError):
        parse_challenge(bad)


def test_the_code_is_posted_once_and_not_kept_on_settings(tmp_path):
    settings = Settings(
        username="person",
        password="not-sent",
        gateway="https://gateway.example",
        ciam="https://ciam.example",
        access_token="",
        download_dir=tmp_path,
    )
    seen: list[tuple[str, bytes | None]] = []

    def exchange(method: str, url: str, body: bytes | None, headers):
        seen.append((url, body))
        assert method == "POST"
        assert headers["content-type"] == "application/json"
        return 200, json.dumps({"state": "continue"}).encode()

    result = submit_code(settings, parse_challenge(CHALLENGE), lambda _prompt: "abcd1234", exchange)
    assert result["state"] == "continue"
    assert seen[0][0] == "https://ciam.example/tenant/api/v1.0/auth/methods/email/method/verify"
    posted = json.loads(seen[0][1] or b"")
    assert posted["otp"] == "abcd1234"
    assert "not-sent" not in (seen[0][1] or b"").decode()
    assert "otp" not in settings.__dict__.values()
