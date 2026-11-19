"""Gateway calls. The transport is injected so tests never open a socket."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Protocol

from spskit.catalog import CatalogError, LicensedModule, parse_permissions, resource_id
from spskit.config import Settings
from spskit.download import (
    CREDENTIALS_PATH,
    DownloadGrant,
    credentials_body,
    parse_grant,
    save_bytes,
)
from spskit.verify import SessionExpiredError, VerificationChallenge, challenge_from_body, otp_message, prompt_code


class Exchange(Protocol):
    def __call__(self, method: str, url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, bytes]: ...


def auth_headers(settings: Settings) -> dict[str, str]:
    """Send a bearer only when the person supplied one. An empty token is not a header."""
    headers = {"accept": "application/json"}
    if settings.access_token:
        headers["authorization"] = f"Bearer {settings.access_token}"
    return headers


def permissions_url(settings: Settings, raw_id: str) -> str:
    return f"{settings.gateway}/acl/cdl/resources/{resource_id(raw_id)}/permissions"


def _json_body(status: int, raw: bytes) -> Mapping[str, object]:
    if status == 401:
        raise SessionExpiredError("the TDS session expired")
    if status != 200:
        raise CatalogError(f"gateway status {status}")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise CatalogError("response is not an object")
    return payload


def list_modules(settings: Settings, raw_id: str, exchange: Exchange) -> list[LicensedModule]:
    status, raw = exchange("GET", permissions_url(settings, raw_id), None, auth_headers(settings))
    return parse_permissions(_json_body(status, raw))


def request_grant(settings: Settings, module: LicensedModule, exchange: Exchange) -> DownloadGrant:
    body = json.dumps(credentials_body(module)).encode("utf-8")
    headers = auth_headers(settings)
    headers["content-type"] = "application/json"
    status, raw = exchange("POST", settings.gateway + CREDENTIALS_PATH, body, headers)
    return parse_grant(_json_body(status, raw))


def fetch_module(settings: Settings, grant: DownloadGrant, exchange: Exchange) -> bytes:
    status, raw = exchange("GET", grant.url, None, grant.headers)
    if status != 200:
        raise CatalogError(f"file status {status}")
    if not raw:
        raise CatalogError("file was empty")
    save_bytes(settings.download_dir, grant.filename, raw)
    return raw


def submit_code(
    settings: Settings,
    challenge: VerificationChallenge,
    reader: Callable[[str], str],
    exchange: Exchange,
) -> Mapping[str, object]:
    """Prompt, post the code to the path the challenge named, and keep the code off the settings object."""
    code = prompt_code(challenge, reader)
    message = otp_message(challenge, code)
    del code
    url = settings.ciam + challenge.verify_path
    status, raw = exchange(
        "POST",
        url,
        json.dumps(message).encode("utf-8"),
        {"content-type": "application/json", "accept": "application/json"},
    )
    if status != 200:
        raise SessionExpiredError(f"verification was refused ({status})")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise SessionExpiredError("verification response is not an object")
    if payload.get("state") != "continue":
        again = challenge_from_body(payload)
        if again is not None:
            raise SessionExpiredError("the host asked for the code again")
        raise SessionExpiredError("verification did not continue")
    return payload
