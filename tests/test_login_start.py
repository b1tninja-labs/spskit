from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from spskit.cli import run
from spskit.config import Settings
from spskit.login_start import (
    CodeRejectedError,
    EmailRequest,
    LoginError,
    MfaChallenge,
    _load_config,
    parse_page_config,
    redirect_location,
    request_email_code,
    submit_email_code,
)

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


def test_a_redirecting_page_is_loaded_again_with_sso_reload():
    settings = Settings(
        "person@example.com",
        "current-secret",
        "https://gateway.example",
        "https://ciam.example",
        "",
        Path("D:/data/spskit"),
    )
    first = "https://ciam.example/tenant/oauth2/v2.0/authorize?client_id=abc"
    seen: list[str] = []

    def exchange(method, url, _body, headers):
        assert method == "GET"
        seen.append(url)
        if "sso_reload=true" not in url:
            return 200, b'<html><title>Redirecting</title><script>$Config={"sFTName":"flowToken"};</script></html>'
        assert headers["referer"] == first
        return 200, PAGE.encode()

    config, loaded = _load_config(settings, exchange, first)
    assert config["sFT"] == "flow-token-value-0001"
    assert loaded.startswith(first)
    assert "sso_reload=true" in loaded
    assert seen[0] == first


def test_a_password_redirect_is_posted_back_with_sso_reload(tmp_path):
    settings = Settings(
        "person@example.com",
        "current-secret",
        "https://gateway.example",
        "https://ciam.example",
        "",
        tmp_path,
    )
    interrupt = """
<html><title>Redirecting</title><script>$Config={"sFTName":"flowToken","stsErrorCode":"50168",
"urlPost":"/tenant/login","oPostParams":{"flowToken":"flow-after-interrupt","ctx":"ctx-i",
"canary":"canary-i","login":"person@example.com","passwd":"a&amp;b","type":"11"},
"bsso":{"cookieNames":{"ssoPulled":"SSOCOOKIEPULLED"}}};</script></html>
"""
    seen: list[tuple[str, str]] = []

    def exchange(method, url, body, headers):
        seen.append((method, url))
        if method == "GET":
            return 200, PAGE.encode()
        if url.endswith("/GetCredentialType"):
            return 200, json.dumps({"IfExistsResult": 0, "FlowToken": "flow-2"}).encode()
        if url.endswith("/login") and "sso_reload=true" not in url:
            posted = parse_qs(body.decode())
            assert posted["passwd"] == ["current-secret"]
            return 200, interrupt.encode()
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
        assert "sso_reload=true" in url
        assert "/login?" in url
        assert headers["cookie"] == "SSOCOOKIEPULLED=1"
        posted = parse_qs(body.decode())
        assert posted["passwd"] == ["a&b"]
        assert posted["flowToken"] == ["flow-after-interrupt"]
        assert "current-secret" not in body.decode()
        return 200, MFA.encode()

    requested = request_email_code(settings, exchange)
    assert requested.challenge.code_length == 8
    assert any("sso_reload=true" in url for _method, url in seen)


def test_the_code_post_follows_the_redirect_before_it_is_judged(tmp_path):
    settings = Settings(
        "person@example.com",
        "current-secret",
        "https://gateway.example",
        "https://ciam.example",
        "",
        tmp_path,
    )
    requested = EmailRequest(
        MfaChallenge(8, "flow-after-begin", "ctx-after-begin", "form-canary", "corr-begin", "person@example.com"),
        "b" * 43,
    )
    interrupt = """
<html><title>Redirecting</title><script>$Config={"stsErrorCode":"50168",
"urlPost":"/common/SAS/ProcessAuth","oPostParams":{"otc":"abcd1234","canary":"form-canary",
"flowToken":"flow-after-begin","request":"ctx-after-begin","login":"person@example.com",
"hpgrequestid":"corr-begin","mfaAuthMethod":"Email"},
"bsso":{"cookieNames":{"ssoPulled":"SSOCOOKIEPULLED"}}};</script></html>
"""

    def exchange(method, url, body, headers):
        assert method == "POST"
        if url.endswith("/ProcessAuth") and "sso_reload" not in url:
            assert parse_qs(body.decode())["otc"] == ["abcd1234"]
            assert parse_qs(body.decode())["mfaAuthMethod"] == ["Email"]
            return 200, interrupt.encode()
        if "sso_reload=true" in url:
            assert headers["cookie"] == "SSOCOOKIEPULLED=1"
            assert parse_qs(body.decode())["otc"] == ["abcd1234"]
            return 200, KMSI.encode()
        assert url.endswith("/kmsi")
        return 302, REDIRECT.encode()

    assert submit_email_code(settings, requested, "abcd1234", exchange) == REDIRECT

    def rejected(_method, url, _body, _headers):
        if "sso_reload=true" in url:
            return 200, MFA.replace('"sErrorCode":"50074"', '"sErrorCode":"InvalidOneTimePasscode"').encode()
        return 200, interrupt.encode()

    with pytest.raises(CodeRejectedError, match="rejected") as caught:
        submit_email_code(settings, requested, "abcd1234", rejected)
    assert caught.value.challenge.flow_token == "flow-after-password"


def test_a_rejected_code_is_asked_again_without_a_new_email(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "TDS_USERNAME=person@example.com",
                "TDS_PASSWORD=current-secret",
                "TDS_CIAM=https://ciam.example",
                "TDS_BACKEND=https://backend.example",
                "TDS_GATEWAY=https://gateway.example",
                "SPS_DOWNLOAD_DIR=" + str(tmp_path / "out"),
            ]
        ),
        encoding="utf-8",
    )
    codes = iter(["00000000", "abcd1234"])
    begins = 0
    posts = 0
    first_try = """
<html><title>Redirecting</title><script>$Config={"stsErrorCode":"50168",
"urlPost":"/common/SAS/ProcessAuth","oPostParams":{"otc":"00000000","canary":"form-canary",
"flowToken":"flow-after-begin","request":"ctx-after-begin","login":"person@example.com",
"hpgrequestid":"corr-begin","mfaAuthMethod":"Email"},
"bsso":{"cookieNames":{"ssoPulled":"SSOCOOKIEPULLED"}}};</script></html>
"""
    second_try = first_try.replace("00000000", "abcd1234")
    rejected_page = (
        MFA.replace('"sErrorCode":"50074"', '"sErrorCode":"InvalidOneTimePasscode"')
        .replace("flow-after-password", "flow-retry")
        .replace("ctx-after-password", "ctx-retry")
    )

    def exchange(method, url, body, headers):
        nonlocal begins, posts
        if method == "GET":
            return 200, PAGE.encode()
        if url.endswith("/GetCredentialType"):
            return 200, json.dumps({"IfExistsResult": 0, "FlowToken": "flow-2"}).encode()
        if url.endswith("/login") and "sso_reload" not in url:
            return 200, MFA.encode()
        if url.endswith("/BeginAuth"):
            begins += 1
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
        if url.endswith("/ProcessAuth") and "sso_reload" not in url:
            posts += 1
            posted = parse_qs(body.decode())
            if posts == 1:
                assert posted["flowToken"] == ["flow-after-begin"]
                assert posted["otc"] == ["00000000"]
                return 200, first_try.encode()
            assert posted["flowToken"] == ["flow-retry"]
            assert posted["request"] == ["ctx-retry"]
            assert posted["otc"] == ["abcd1234"]
            return 200, second_try.encode()
        if "sso_reload=true" in url:
            posted = parse_qs(body.decode())
            if posted["otc"] == ["00000000"]:
                return 200, rejected_page.encode()
            return 200, KMSI.encode()
        if url.endswith("/kmsi"):
            return 302, REDIRECT.encode()
        if url.endswith("/token"):
            return 200, json.dumps({"token_type": "Bearer", "access_token": TOKEN}).encode()
        assert headers["X-EEID-Access-Token"] == TOKEN
        return 200, b"{}"

    def reader(prompt: str) -> str:
        assert "email code" in prompt
        return next(codes)

    assert run(["--env", str(env), "login"], exchange, reader) == 0
    assert begins == 1
    assert posts == 2
    assert "That code was rejected." in capsys.readouterr().err
    saved = json.loads((tmp_path / "out" / "session.json").read_text(encoding="utf-8"))
    assert saved["access_token"] == TOKEN


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
