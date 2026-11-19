"""The email verification step the TDS sign-in host returns when a session needs a code.

The host's challenge names the path and the code length. The code is typed by the person,
sent once, and not stored on the session object.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass


class VerificationError(ValueError):
    """The challenge or the code cannot be used."""


class SessionExpiredError(VerificationError):
    """The gateway refused the session and did not return a challenge to complete."""


@dataclass(frozen=True)
class VerificationChallenge:
    continuation_token: str
    code_length: int
    verify_path: str


def parse_challenge(payload: Mapping[str, object]) -> VerificationChallenge:
    if payload.get("state") != "verificationRequired":
        raise VerificationError("not a verification challenge")
    links = payload.get("_links")
    if not isinstance(links, Mapping):
        raise VerificationError("challenge has no links")
    verify = links.get("verify")
    if not isinstance(verify, Mapping):
        raise VerificationError("challenge has no verify link")
    href = verify.get("href")
    if not isinstance(href, str) or not _same_host_path(href):
        raise VerificationError("verify link is not a path on the sign-in host")
    length = payload.get("codeLength")
    if not isinstance(length, int) or not 4 <= length <= 12:
        raise VerificationError("code length is not usable")
    token = payload.get("continuationToken")
    if not isinstance(token, str) or not token:
        raise VerificationError("missing continuation")
    return VerificationChallenge(token, length, href)


def _same_host_path(href: str) -> bool:
    return href.startswith("/") and "://" not in href and "\\" not in href and ".." not in href


def otp_message(challenge: VerificationChallenge, code: str) -> dict[str, str]:
    """The body the verify call posts. The code must be the length the challenge stated."""
    if len(code) != challenge.code_length or not code.isalnum():
        raise VerificationError(f"the code must be {challenge.code_length} letters or digits")
    return {"continuationToken": challenge.continuation_token, "otp": code}


def prompt_code(challenge: VerificationChallenge, reader: Callable[[str], str]) -> str:
    """Ask once. The returned code is for the caller to send; this function keeps no copy."""
    typed = reader(f"Session needs a verification code ({challenge.code_length} characters): ")
    code = typed.strip()
    otp_message(challenge, code)
    return code


def challenge_from_body(payload: Mapping[str, object]) -> VerificationChallenge | None:
    """A response is a challenge only when the host says verification is required."""
    if payload.get("state") != "verificationRequired":
        return None
    return parse_challenge(payload)
