"""The sign-in steps the capture actually showed.

The password call in that capture is a reset: the host said methodUpdateRequired and the
browser posted newPassword. This module refuses that step. The stored password is not sent.

The session the site keeps is an OAuth authorization code exchanged at the token endpoint.
The code arrives on the redirect fragment. The code verifier is the one the person who
started that login holds, not a value copied from a capture.
"""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Mapping

from spskit.verify import VerificationError

# Public identifiers from the TDS sign-in page, not credentials.
PUBLIC_CLIENT_ID = "f5ad86b7-efd9-4305-b9c0-2f880adf3195"
TENANT_ID = "450fd55c-b136-4d90-9e9f-a59b07772fab"
REDIRECT_URI = "https://www.acdelcotds.com"
_VERIFIER = re.compile(r"[A-Za-z0-9._~-]{43,128}")


class PasswordUpdateRequiredError(VerificationError):
    """The host asked for a new password. The stored password is not a substitute."""


class TokenError(ValueError):
    """An authorization code or a token response cannot be used."""


def refuse_password_update(payload: Mapping[str, object]) -> None:
    """A methodUpdateRequired step wants newPassword. Do not post the stored password there."""
    if payload.get("state") == "methodUpdateRequired":
        raise PasswordUpdateRequiredError("the sign-in host asked for a new password; the stored password is not sent")


def authorization_code(redirect_url: str) -> str:
    """Read the code from the fragment of the TDS redirect. The fragment is not sent to the site."""
    parts = urllib.parse.urlsplit(redirect_url)
    if parts.scheme != "https" or parts.hostname != "www.acdelcotds.com":
        raise TokenError("the redirect is not the TDS site")
    found = urllib.parse.parse_qs(parts.fragment, keep_blank_values=False)
    codes = found.get("code", [])
    if len(codes) != 1 or not codes[0] or any(character.isspace() for character in codes[0]):
        raise TokenError("the redirect has no authorization code")
    return codes[0]


def token_form(client_id: str, redirect_uri: str, code: str, code_verifier: str) -> list[tuple[str, str]]:
    """The form fields the token call posted, in the same order, with no password field."""
    if _VERIFIER.fullmatch(code_verifier) is None:
        raise TokenError("the code verifier must be 43 to 128 unreserved characters")
    if not code or any(character.isspace() for character in code):
        raise TokenError("the authorization code is empty")
    return [
        ("client_id", client_id),
        ("redirect_uri", redirect_uri),
        ("scope", f"{client_id}/.default openid profile offline_access"),
        ("code", code),
        ("code_verifier", code_verifier),
        ("grant_type", "authorization_code"),
        ("client_info", "1"),
    ]


def parse_access_token(payload: Mapping[str, object]) -> str:
    """Return the access token only. A refresh token in the same object is not returned."""
    kind = payload.get("token_type")
    token = payload.get("access_token")
    if not isinstance(kind, str) or not kind.strip():
        raise TokenError("token type is missing")
    if not isinstance(token, str) or len(token) < 20 or any(character.isspace() for character in token):
        raise TokenError("access token is missing")
    return token
