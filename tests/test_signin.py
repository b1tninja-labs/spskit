from __future__ import annotations

import json
import urllib.parse

import pytest

from spskit.client import exchange_authorization_code, open_backend_session, submit_code
from spskit.config import Settings
from spskit.signin import (
    PasswordUpdateRequiredError,
    TokenError,
    authorization_code,
    parse_access_token,
    password_update_body,
    token_form,
)
from spskit.verify import SessionExpiredError, parse_challenge

VERIFIER = "a" * 43
REDIRECT = "https://www.acdelcotds.com/#code=example-authorization-code&client_info=1"


def test_the_password_update_posts_the_new_password_and_not_the_current_one(tmp_path):
    settings = Settings(
        username="person",
        password="current-secret",
        gateway="https://gateway.example",
        ciam="https://ciam.example",
        access_token="",
        download_dir=tmp_path,
        new_password="next-secret",
    )
    challenge = {
        "state": "verificationRequired",
        "codeLength": 8,
        "continuationToken": "continue-1",
        "_links": {"verify": {"href": "/tenant/api/v1.0/auth/methods/email/method/verify"}},
    }
    seen: list[tuple[str, str, bytes | None]] = []

    def exchange(method, url, body, headers):
        seen.append((method, url, body))
        assert headers["content-type"] == "application/json"
        if url.endswith("/verify"):
            return 200, json.dumps(
                {
                    "state": "continue",
                    "continuationToken": "continue-2",
                    "_links": {"next": {"href": "/tenant/api/v1.0/auth/methods/password/method/recover"}},
                }
            ).encode()
        if url.endswith("/recover"):
            posted = json.loads(body)
            assert "next-secret" not in posted.values()
            assert "current-secret" not in posted.values()
            return 200, json.dumps(
                {
                    "state": "methodUpdateRequired",
                    "continuationToken": "continue-3",
                    "_links": {"update": {"href": "/tenant/api/v1.0/auth/methods/password/method"}},
                }
            ).encode()
        if method == "PUT":
            assert json.loads(body) == password_update_body("continue-3", "next-secret")
            return 200, json.dumps(
                {
                    "state": "methodUpdatePending",
                    "continuationToken": "continue-4",
                    "_links": {"poll": {"href": "/tenant/api/v1.0/auth/methods/password/method/pollUpdate"}},
                }
            ).encode()
        posted = json.loads(body)
        assert posted == {"continuationToken": "continue-4"}
        assert "next-secret" not in posted.values()
        return 200, json.dumps({"state": "continue", "continuationToken": "continue-5"}).encode()

    result = submit_code(settings, parse_challenge(challenge), lambda _prompt: "abcd1234", exchange)
    assert result["state"] == "continue"
    assert [item[0] for item in seen] == ["POST", "POST", "PUT", "POST"]


def test_a_missing_password_is_not_invented(tmp_path):
    settings = Settings(
        username="person",
        password="",
        gateway="https://gateway.example",
        ciam="https://ciam.example",
        access_token="",
        download_dir=tmp_path,
    )
    with pytest.raises(PasswordUpdateRequiredError, match="TDS_NEW_PASSWORD"):
        password_update_body("continue-3", settings.new_password or settings.password)


def test_the_redirect_code_is_the_fragment():
    assert authorization_code(REDIRECT) == "example-authorization-code"
    with pytest.raises(TokenError, match="not the TDS"):
        authorization_code("https://evil.example/#code=example-authorization-code")


def test_the_token_form_has_no_password_field():
    form = dict(token_form("client", "https://www.acdelcotds.com", "example-authorization-code", VERIFIER))
    assert form["grant_type"] == "authorization_code"
    assert form["client_info"] == "1"
    assert form["code_verifier"] == VERIFIER
    assert "password" not in form
    assert "newPassword" not in form


def test_the_access_token_is_kept_and_the_refresh_token_is_dropped():
    token = parse_access_token(
        {
            "token_type": "Bearer",
            "access_token": "access-token-value-0001",
            "refresh_token": "refresh-token-value-0001",
        }
    )
    assert token == "access-token-value-0001"
    assert "refresh" not in token


def test_the_code_is_exchanged_and_the_profile_is_discarded(tmp_path):
    settings = Settings(
        username="person",
        password="stored-password",
        gateway="https://gateway.example",
        ciam="https://ciam.example",
        access_token="",
        download_dir=tmp_path,
        code_verifier=VERIFIER,
    )
    seen: list[tuple[str, bytes | None, dict[str, str]]] = []

    def exchange(method, url, body, headers):
        seen.append((url, body, dict(headers)))
        if "token.gen.acdelcotds.com" in url:
            assert method == "GET"
            assert body is None
            return 200, b"header.payload.signature"
        assert method == "POST"
        if url.endswith("/token"):
            posted = urllib.parse.parse_qs(body.decode())
            assert posted["grant_type"] == ["authorization_code"]
            assert headers["origin"] == "https://www.acdelcotds.com"
            assert "stored-password" not in body.decode()
            return 200, json.dumps(
                {"token_type": "Bearer", "access_token": "access-token-value-0001", "refresh_token": "refresh-secret"}
            ).encode()
        assert headers["Authorization"] == "Bearer header.payload.signature"
        assert headers["X-EEID-Access-Token"] == "access-token-value-0001"
        assert headers["Origin"] == "https://www.acdelcotds.com"
        assert headers["Referer"] == "https://www.acdelcotds.com/"
        assert body == b""
        assert "zoneId=America%2FLos_Angeles" in url
        return 200, json.dumps({"email": "person@example.com", "phone": "000"}).encode()

    access = exchange_authorization_code(settings, REDIRECT, exchange)
    open_backend_session(settings, access, exchange)
    assert access == "access-token-value-0001"
    assert seen[2][1] == b""


def test_a_refused_token_names_the_error_and_hides_the_description(tmp_path):
    settings = Settings(
        username="person",
        password="stored-password",
        gateway="https://gateway.example",
        ciam="https://ciam.example",
        access_token="",
        download_dir=tmp_path,
        code_verifier=VERIFIER,
    )

    def exchange(_method, url, _body, _headers):
        assert url.endswith("/token")
        return 400, json.dumps(
            {
                "error": "invalid_grant",
                "error_codes": [50148],
                "error_description": "AADSTS50148: secret-authorization-code",
            }
        ).encode()

    with pytest.raises(SessionExpiredError, match="invalid_grant") as caught:
        exchange_authorization_code(settings, REDIRECT, exchange)
    message = str(caught.value)
    assert "50148" in message
    assert "AADSTS50148" in message
    assert "secret-authorization-code" not in message


def test_a_refused_backend_names_the_error_and_hides_a_token(tmp_path):
    settings = Settings(
        username="person",
        password="stored-password",
        gateway="https://gateway.example",
        ciam="https://ciam.example",
        access_token="",
        download_dir=tmp_path,
        code_verifier=VERIFIER,
    )

    def exchange(method, url, body, headers):
        if "token.gen.acdelcotds.com" in url:
            assert method == "GET"
            return 200, b"header.payload.signature"
        assert "/api/v1/login" in url
        assert body == b""
        assert headers["Authorization"] == "Bearer header.payload.signature"
        assert headers["Origin"] == "https://www.acdelcotds.com"
        return 401, json.dumps({"message": "Unauthorized", "token": "header.payload.signature"}).encode()

    with pytest.raises(SessionExpiredError, match="Unauthorized") as caught:
        open_backend_session(settings, "access-token-value-0001", exchange)
    assert "header.payload.signature" not in str(caught.value)
