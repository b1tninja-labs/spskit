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
"correlationId":"corr-kmsi","sessionId":"sess-kmsi","pgid":"KmsiInterrupt","urlPost":"/kmsi","sErrorCode":"50140"};</script></html>
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
        if "token.gen.acdelcotds.com" in url:
            return 200, b"header.payload.signature"
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
            return 200, json.dumps(
                {"token_type": "Bearer", "access_token": TOKEN, "refresh_token": "refresh-token-value-0001"}
            ).encode()
        assert headers["Authorization"] == "Bearer header.payload.signature"
        assert headers["X-EEID-Access-Token"] == TOKEN
        return 200, b"{}"

    def reader(prompt: str) -> str:
        assert "email code" in prompt
        return next(codes)

    assert run(["--env", str(env), "login"], exchange, reader) == 0
    assert begins == 1
    assert posts == 0
    assert run(["--env", str(env), "code"], exchange, reader) == 0
    assert begins == 1
    assert posts == 2
    assert "That code was rejected." in capsys.readouterr().err
    saved = json.loads((tmp_path / "out" / "session.json").read_text(encoding="utf-8"))
    assert saved["access_token"] == TOKEN


def test_a_confirmation_page_is_posted_before_stay_signed_in():
    settings = Settings(
        "person@example.com",
        "current-secret",
        "https://gateway.example",
        "https://ciam.example",
        "",
        Path("D:/data/spskit"),
    )
    requested = EmailRequest(
        MfaChallenge(8, "flow-after-begin", "ctx-after-begin", "form-canary", "corr-begin", "person@example.com"),
        "b" * 43,
    )
    cmsi = """<html><title>Sign in to your account</title><script>$Config={"sFT":"flow-cmsi",
"sCtx":"ctx-cmsi","canary":"canary-cmsi","sessionId":"sess-cmsi","correlationId":"corr-cmsi",
"pgid":"CmsiInterrupt","stsErrorCode":399218,"urlPost":"/appverify"};</script></html>"""

    def exchange(_method, url, body, _headers):
        if url.endswith("/ProcessAuth"):
            return 200, cmsi.encode()
        if url.endswith("/appverify"):
            form = parse_qs(body.decode())
            assert form["ContinueAuth"] == ["true"]
            assert form["hpgrequestid"] == ["sess-cmsi"]
            assert form["flowToken"] == ["flow-cmsi"]
            assert "otc" not in form
            return 200, KMSI.encode()
        assert url.endswith("/kmsi")
        assert "otc" not in parse_qs(body.decode())
        return 302, REDIRECT.encode()

    assert submit_email_code(settings, requested, "abcd1234", exchange) == REDIRECT


def test_the_stay_signed_in_redirect_page_is_posted_back():
    settings = Settings(
        "person@example.com",
        "current-secret",
        "https://gateway.example",
        "https://ciam.example",
        "",
        Path("D:/data/spskit"),
    )
    requested = EmailRequest(
        MfaChallenge(8, "flow-after-begin", "ctx-after-begin", "form-canary", "corr-begin", "person@example.com"),
        "b" * 43,
    )
    redirecting = """<html><title>Redirecting</title><script>$Config={"stsErrorCode":50168,
"urlPost":"/kmsi","oPostParams":{"LoginOptions":"1","type":"28","ctx":"ctx-kmsi",
"hpgrequestid":"sess-kmsi","flowToken":"flow-kmsi","canary":"canary-kmsi","i19":"0"},
"bsso":{"cookieNames":{"ssoPulled":"SSOCOOKIEPULLED"}}};</script></html>"""

    def exchange(_method, url, body, headers):
        if url.endswith("/ProcessAuth"):
            return 200, KMSI.encode()
        if "sso_reload=true" not in url:
            assert url.endswith("/kmsi")
            return 200, redirecting.encode()
        assert headers["cookie"] == "SSOCOOKIEPULLED=1"
        form = parse_qs(body.decode())
        assert form["flowToken"] == ["flow-kmsi"]
        assert "otc" not in form
        return 302, REDIRECT.encode()

    assert submit_email_code(settings, requested, "abcd1234", exchange) == REDIRECT


def test_confirmation_followed_by_a_redirect_form_is_posted_back():
    settings = Settings(
        "person@example.com",
        "current-secret",
        "https://gateway.example",
        "https://ciam.example",
        "",
        Path("D:/data/spskit"),
    )
    requested = EmailRequest(
        MfaChallenge(8, "flow-after-begin", "ctx-after-begin", "form-canary", "corr-begin", "person@example.com"),
        "b" * 43,
    )
    cmsi = """<html><title>Sign in to your account</title><script>$Config={"sFT":"flow-cmsi",
"sCtx":"ctx-cmsi","canary":"canary-cmsi","sessionId":"sess-cmsi","correlationId":"corr-cmsi",
"pgid":"CmsiInterrupt","stsErrorCode":399218,"urlPost":"/appverify"};</script></html>"""
    redirecting = """<html><title>Redirecting</title><script>$Config={"sFT":"flow-on-redirect",
"stsErrorCode":50168,"urlPost":"/kmsi","oPostParams":{"LoginOptions":"1","type":"28","ctx":"ctx-kmsi",
"hpgrequestid":"sess-kmsi","flowToken":"flow-kmsi","canary":"canary-kmsi","i19":"0"},
"bsso":{"cookieNames":{"ssoPulled":"SSOCOOKIEPULLED"}}};</script></html>"""

    def exchange(_method, url, body, headers):
        if url.endswith("/ProcessAuth"):
            return 200, cmsi.encode()
        if url.endswith("/appverify"):
            assert "otc" not in parse_qs(body.decode())
            return 200, redirecting.encode()
        assert "sso_reload=true" in url
        assert headers["cookie"] == "SSOCOOKIEPULLED=1"
        assert parse_qs(body.decode())["flowToken"] == ["flow-kmsi"]
        return 302, REDIRECT.encode()

    assert submit_email_code(settings, requested, "abcd1234", exchange) == REDIRECT


def test_a_redirect_page_with_a_flow_token_is_posted_back():
    settings = Settings(
        "person@example.com",
        "current-secret",
        "https://gateway.example",
        "https://ciam.example",
        "",
        Path("D:/data/spskit"),
    )
    requested = EmailRequest(
        MfaChallenge(8, "flow-after-begin", "ctx-after-begin", "form-canary", "corr-begin", "person@example.com"),
        "b" * 43,
    )
    redirecting = """<html><title>Redirecting</title><script>$Config={"sFT":"flow-on-redirect",
"stsErrorCode":50168,"urlPost":"/kmsi","oPostParams":{"LoginOptions":"1","type":"28","ctx":"ctx-kmsi",
"hpgrequestid":"sess-kmsi","flowToken":"flow-kmsi","canary":"canary-kmsi","i19":"0"},
"bsso":{"cookieNames":{"ssoPulled":"SSOCOOKIEPULLED"}}};</script></html>"""
    stayed = """<html><title>Sign in to your account</title><script>$Config={"sFT":"flow-after-reload",
"sCtx":"ctx-after-reload","canary":"canary-after","sessionId":"sess-after","correlationId":"corr-after",
"pgid":"KmsiInterrupt","urlPost":"/kmsi","sErrorCode":"50140"};</script></html>"""
    posts = {"kmsi": 0}

    def exchange(_method, url, body, headers):
        if url.endswith("/ProcessAuth"):
            return 200, KMSI.encode()
        if "sso_reload=true" in url:
            assert headers["cookie"] == "SSOCOOKIEPULLED=1"
            form = parse_qs(body.decode())
            assert form["flowToken"] == ["flow-kmsi"]
            assert "otc" not in form
            return 200, stayed.encode()
        assert url.endswith("/kmsi")
        posts["kmsi"] += 1
        if posts["kmsi"] == 1:
            return 200, redirecting.encode()
        form = parse_qs(body.decode())
        assert form["flowToken"] == ["flow-after-reload"]
        assert form["hpgrequestid"] == ["sess-after"]
        assert "otc" not in form
        return 302, REDIRECT.encode()

    assert submit_email_code(settings, requested, "abcd1234", exchange) == REDIRECT
    assert posts["kmsi"] == 2


def test_an_expired_challenge_is_named():
    settings = Settings(
        "person@example.com",
        "current-secret",
        "https://gateway.example",
        "https://ciam.example",
        "",
        Path("D:/data/spskit"),
    )
    requested = EmailRequest(
        MfaChallenge(8, "flow-after-begin", "ctx-after-begin", "form-canary", "corr-begin", "person@example.com"),
        "b" * 43,
    )
    expired = """<html><title>Sign in to your account</title><script>$Config={"pgid":"ConvergedError",
"stsErrorCode":50089,"sessionId":"sess","correlationId":"corr","canary":"canary","apiCanary":"api",
"strMainMessage":"flow-secret-value"};</script></html>"""

    def exchange(_method, url, _body, _headers):
        assert url.endswith("/ProcessAuth")
        return 200, expired.encode()

    with pytest.raises(LoginError, match="challenge expired") as caught:
        submit_email_code(settings, requested, "abcd1234", exchange)
    assert "flow-secret-value" not in str(caught.value)
    assert "50089" in str(caught.value)


def test_a_page_that_is_not_stay_signed_in_names_itself(tmp_path):
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
    body = """<html><title>Sign in to your account</title><script>$Config={"sFT":"flow-secret-value",
"sCtx":"ctx-secret","canary":"canary-secret","sessionId":"sess-1","correlationId":"corr-1",
"pgid":"OtherPage","sErrorCode":"50011","urlPost":"/common/SAS/ProcessAuth",
"sErrTxt":"person@example.com abcd1234"};</script><!-- abcd1234 flow-secret-value --></html>"""

    def exchange(_method, url, _body, _headers):
        assert url.endswith("/ProcessAuth")
        return 200, body.encode()

    with pytest.raises(LoginError, match="pgid OtherPage") as caught:
        submit_email_code(settings, requested, "abcd1234", exchange)
    message = str(caught.value)
    assert "sErrorCode 50011" in message
    assert "urlPost /common/SAS/ProcessAuth" in message
    assert "title Sign in to your account" in message
    for secret in (
        "abcd1234",
        "flow-secret-value",
        "ctx-secret",
        "canary-secret",
        "person@example.com",
        "current-secret",
    ):
        assert secret not in message


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
        if "token.gen.acdelcotds.com" in url:
            return 200, b"header.payload.signature"
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
            assert form["hpgrequestid"] == ["sess-kmsi"]
            assert form["flowToken"] == ["flow-kmsi"]
            assert "otc" not in form
            assert "current-secret" not in posted
            return 302, REDIRECT.encode()
        if url.endswith("/token"):
            assert b"current-secret" not in body
            assert b"abcd1234" not in body
            return 200, json.dumps(
                {"token_type": "Bearer", "access_token": TOKEN, "refresh_token": "refresh-token-value-0001"}
            ).encode()
        assert url.startswith("https://backend.example/api/v1/login")
        assert body == b""
        assert headers["Origin"] == "https://www.acdelcotds.com"
        assert headers["Authorization"] == "Bearer header.payload.signature"
        assert headers["X-EEID-Access-Token"] == TOKEN
        return 200, b"{}"

    def reader(prompt: str) -> str:
        order.append("PROMPT")
        assert "email code" in prompt
        assert "8" in prompt
        return "abcd1234"

    code = run(["--env", str(env), "login"], exchange, reader)
    assert code == 0
    assert "PROMPT" not in order
    pending_text = (tmp_path / "out" / "session.json").read_text(encoding="utf-8")
    assert "signin" in pending_text
    assert "abcd1234" not in pending_text
    assert "current-secret" not in pending_text
    code = run(["--env", str(env), "code"], exchange, reader)
    assert code == 0
    assert order.index("PROMPT") > next(i for i, url in enumerate(order) if url.endswith("/BeginAuth"))
    assert order.index("PROMPT") < next(i for i, url in enumerate(order) if str(url).endswith("/ProcessAuth"))
    captured = capsys.readouterr()
    assert "abcd1234" not in captured.out
    assert TOKEN not in captured.out
    assert "current-secret" not in captured.out
    saved = json.loads((tmp_path / "out" / "session.json").read_text(encoding="utf-8"))
    assert saved["access_token"] == TOKEN
    assert "signin" not in saved
    assert "stay" not in saved
    assert "abcd1234" not in json.dumps(saved)


def test_a_saved_stay_signed_in_finishes_without_a_new_email(tmp_path, capsys):
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
    calls: list[str] = []
    kmsi_posts = 0

    def exchange(method, url, body, headers):
        nonlocal kmsi_posts
        calls.append(url)
        if "token.gen.acdelcotds.com" in url:
            return 200, b"header.payload.signature"
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
        if url.endswith("/ProcessAuth"):
            assert parse_qs(body.decode())["otc"] == ["abcd1234"]
            return 200, KMSI.encode()
        if url.endswith("/kmsi"):
            kmsi_posts += 1
            if kmsi_posts == 1:
                raise LoginError("the sign-in host closed the connection")
            assert parse_qs(body.decode())["hpgrequestid"] == ["sess-kmsi"]
            assert "otc" not in parse_qs(body.decode())
            return 302, REDIRECT.encode()
        if url.endswith("/token"):
            assert b"abcd1234" not in body
            return 200, json.dumps(
                {"token_type": "Bearer", "access_token": TOKEN, "refresh_token": "refresh-token-value-0001"}
            ).encode()
        assert headers["Authorization"] == "Bearer header.payload.signature"
        assert headers["X-EEID-Access-Token"] == TOKEN
        return 200, b"{}"

    prompts: list[str] = []

    def reader(prompt: str) -> str:
        prompts.append(prompt)
        return "abcd1234"

    assert run(["--env", str(env), "login"], exchange, reader) == 0
    assert prompts == []
    assert run(["--env", str(env), "code"], exchange, reader) == 2
    saved = (tmp_path / "out" / "session.json").read_text(encoding="utf-8")
    assert "abcd1234" not in saved
    assert "/kmsi" in saved
    assert run(["--env", str(env), "code"], exchange, reader) == 0
    assert prompts == ["Enter the email code (8 characters): "]
    assert kmsi_posts == 2
    assert sum(1 for url in calls if url.endswith("/BeginAuth")) == 1
    assert sum(1 for url in calls if url.endswith("/ProcessAuth")) == 1
    assert "already accepted" in capsys.readouterr().err
    finished = json.loads((tmp_path / "out" / "session.json").read_text(encoding="utf-8"))
    assert finished["access_token"] == TOKEN
    assert "stay" not in finished


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
