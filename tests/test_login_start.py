from __future__ import annotations

import json
from urllib.parse import parse_qs

import pytest

from spskit.cli import run
from spskit.config import Settings
from spskit.login_start import LoginError, parse_page_config, redirect_location, request_email_code, submit_email_code

PAGE = """
<html><script>$Config={"sFT":"flow-token-value-0001","sCtx":"original-request-value",
"country":"US","apiCanary":"canary-value","canary":"form-canary","correlationId":"corr-id",
"hpgact":2000,"hpgid":11406,"sessionId":"sess-id"};</script></html>
"""

MFA = """
<html><script>$Config={"sFT":"flow-after-password","sCtx":"ctx-after-password",
"canary":"form-canary","apiCanary":"canary-value","correlationId":"corr-id",
"sErrorCode":"50074","pgid":"FabricTFA","iEmailOtcLength":8,
"urlBeginAuth":"https://ciam.example/common/SAS/BeginAuth"};</script></html>
"""

KMSI = """
<html><script>$Config={"sFT":"flow-kmsi","sCtx":"ctx-kmsi","canary":"canary-kmsi",
"correlationId":"corr-kmsi","pgid":"KmsiInterrupt","urlPost":"/kmsi","sErrorCode":"50140"};</script></html>
"""

REDIRECT = "https://www.acdelcotds.com/#code=example-authorization-code"
TOKEN = "access-token-value-0001"


def _page(html: str) -> dict[str, object]:
    config = parse_page_config(html)
    assert config is not None
    return config


def test_a_page_without_a_flow_token_is_skipped():
    assert parse_page_config("<html>$Config={};</html>") is None
    assert _page(PAGE)["sFT"] == "flow-token-value-0001"


def test_a_code_fragment_is_the_redirect_and_a_plain_url_is_not():
    assert redirect_location(REDIRECT) == REDIRECT
    assert redirect_location("https://www.acdelcotds.com/") is None


def test_a_rejected_password_does_not_ask_for_a_code(tmp_path):
    settings = Settings(
        "person@example.com",
        "old-secret",
        "https://gateway.example",
        "https://ciam.example",
        "",
        tmp_path,
        new_password="current-secret",
    )
    seen: list[str] = []

    def exchange(method, url, _body, _headers):
        seen.append(url)
        if method == "GET":
            return 200, PAGE.encode()
        if url.endswith("/GetCredentialType"):
            return 200, json.dumps({"IfExistsResult": 0, "FlowToken": "flow-2"}).encode()
        assert url.endswith("/login")
        return 200, _html(',"sErrorCode":"50126","pgid":"FabricLogin"', "flow-after-password")

    with pytest.raises(LoginError, match="password"):
        request_email_code(settings, exchange)
    assert not any("BeginAuth" in url for url in seen)


def test_login_posts_the_password_then_waits_for_the_email_code(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "TDS_USERNAME=person@example.com",
                "TDS_PASSWORD=old-secret",
                "TDS_NEW_PASSWORD=current-secret",
                "TDS_CIAM=https://ciam.example",
                "TDS_BACKEND=https://backend.example",
                "TDS_GATEWAY=https://gateway.example",
                "SPS_DOWNLOAD_DIR=" + str(tmp_path / "out"),
            ]
        ),
        encoding="utf-8",
    )
    order: list[str] = []

    def exchange(method, url, body, headers):
        order.append("PROMPT" if False else url)
        posted = body.decode() if body else ""
        assert "old-secret" not in posted
        if method == "GET":
            return 200, PAGE.encode()
        if url.endswith("/GetCredentialType"):
            message = json.loads(posted)
            assert message["username"] == "person@example.com"
            assert message["flowToken"] == "flow-token-value-0001"
            assert "current-secret" not in posted
            assert headers["canary"] == "canary-value"
            return 200, json.dumps({"IfExistsResult": 0, "FlowToken": "flow-2", "apiCanary": "canary-2"}).encode()
        if url.endswith("/login"):
            form = parse_qs(posted)
            assert form["passwd"] == ["current-secret"]
            assert form["flowToken"] == ["flow-2"]
            assert form["type"] == ["11"]
            assert form["LoginOptions"] == ["3"]
            assert "BeginAuth" not in posted
            return 200, MFA.encode()
        if url.endswith("/BeginAuth"):
            message = json.loads(posted)
            assert message == {
                "AuthMethodId": "Email",
                "Method": "BeginAuth",
                "ctx": "ctx-after-password",
                "flowToken": "flow-after-password",
            }
            assert "current-secret" not in posted
            return 200, json.dumps(
                {
                    "Success": True,
                    "ErrCode": 0,
                    "ResultValue": "Success",
                    "AuthMethodId": "Email",
                    "FlowToken": "flow-after-begin",
                    "Ctx": "ctx-after-begin",
                    "CorrelationId": "corr-begin",
                }
            ).encode()
        if url.endswith("/ProcessAuth"):
            form = parse_qs(posted)
            assert form["otc"] == ["abcd1234"]
            assert form["mfaAuthMethod"] == ["Email"]
            assert form["flowToken"] == ["flow-after-begin"]
            assert form["request"] == ["ctx-after-begin"]
            assert form["canary"] == ["form-canary"]
            assert "current-secret" not in posted
            return 200, KMSI.encode()
        if url.endswith("/kmsi"):
            form = parse_qs(posted)
            assert form["LoginOptions"] == ["1"]
            assert form["type"] == ["28"]
            assert form["flowToken"] == ["flow-kmsi"]
            assert "otc" not in form
            assert "current-secret" not in posted
            return 302, REDIRECT.encode()
        if url.endswith("/token"):
            assert b"current-secret" not in body
            assert b"abcd1234" not in body
            return 200, json.dumps({"token_type": "Bearer", "access_token": TOKEN}).encode()
        assert url.startswith("https://backend.example/api/v1/login")
        assert body is None
        assert headers["X-EEID-Access-Token"] == TOKEN
        return 200, b"{}"

    def reader(prompt: str) -> str:
        order.append("PROMPT")
        assert "email code" in prompt
        assert "8" in prompt
        return "abcd1234"

    code = run(["--env", str(env), "login"], exchange, reader)
    assert code == 0
    assert order.index("PROMPT") > next(i for i, url in enumerate(order) if url.endswith("/BeginAuth"))
    assert order.index("PROMPT") < next(i for i, url in enumerate(order) if str(url).endswith("/ProcessAuth"))
    captured = capsys.readouterr()
    assert "abcd1234" not in captured.out
    assert TOKEN not in captured.out
    assert "current-secret" not in captured.out
    saved = json.loads((tmp_path / "out" / "session.json").read_text(encoding="utf-8"))
    assert saved["access_token"] == TOKEN
    assert "abcd1234" not in json.dumps(saved)


def test_a_short_code_is_refused_before_it_is_sent(tmp_path):
    settings = Settings(
        "person@example.com", "current-secret", "https://gateway.example", "https://ciam.example", "", tmp_path
    )
    requested = request_email_code(settings, _accepting_exchange())

    def exchange(_method, url, _body, _headers):
        raise AssertionError(url)

    with pytest.raises(LoginError, match="8"):
        submit_email_code(settings, requested, "nope", exchange)


def _html(extra: str = "", flow: str = "flow-token-value-0001") -> bytes:
    body = (
        '{"sFT":"' + flow + '","sCtx":"original-request-value","country":"US",'
        '"apiCanary":"canary-value","canary":"form-canary","correlationId":"corr-id"' + extra + "}"
    )
    return f"<html><script>$Config={body};</script></html>".encode()


def _accepting_exchange():
    def exchange(method, url, _body, _headers):
        if method == "GET":
            return 200, PAGE.encode()
        if url.endswith("/GetCredentialType"):
            return 200, json.dumps({"IfExistsResult": 0, "FlowToken": "flow-2"}).encode()
        if url.endswith("/login"):
            return 200, MFA.encode()
        if url.endswith("/BeginAuth"):
            return 200, json.dumps(
                {
                    "Success": True,
                    "ErrCode": 0,
                    "ResultValue": "Success",
                    "FlowToken": "flow-after-begin",
                    "Ctx": "ctx-after-begin",
                    "CorrelationId": "corr-begin",
                }
            ).encode()
        raise AssertionError(url)

    return exchange
