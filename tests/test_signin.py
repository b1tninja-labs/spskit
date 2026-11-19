from __future__ import annotations

import json
import urllib.parse

import pytest

from spskit.client import exchange_authorization_code, open_backend_session
from spskit.config import Settings
from spskit.signin import (
    PasswordUpdateRequiredError,
    TokenError,
    authorization_code,
    parse_access_token,
    refuse_password_update,
    token_form,
)

VERIFIER = "a" * 43
REDIRECT = "https://www.acdelcotds.com/#code=example-authorization-code&client_info=1"


def test_a_new_password_step_is_refused():
    with pytest.raises(PasswordUpdateRequiredError, match="not sent"):
        refuse_password_update(
            {
                "state": "methodUpdateRequired",
                "type": "password",
                "_links": {"update": {"href": "/tenant/api/v1.0/auth/methods/password/method"}},
            }
        )


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
        assert method == "POST"
        if url.endswith("/token"):
            posted = urllib.parse.parse_qs(body.decode())
            assert posted["grant_type"] == ["authorization_code"]
            assert "stored-password" not in body.decode()
            return 200, json.dumps(
                {"token_type": "Bearer", "access_token": "access-token-value-0001", "refresh_token": "refresh-secret"}
            ).encode()
        assert headers["X-EEID-Access-Token"] == "access-token-value-0001"
        assert body is None
        assert "zoneId=America%2FLos_Angeles" in url
        return 200, json.dumps({"email": "person@example.com", "phone": "000"}).encode()

    access = exchange_authorization_code(settings, REDIRECT, exchange)
    open_backend_session(settings, access, exchange)
    assert access == "access-token-value-0001"
    assert seen[1][1] is None
