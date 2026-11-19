"""Gateway calls. The transport is injected so tests never open a socket."""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Callable, Mapping
from typing import Protocol

from spskit.catalog import (
    CatalogError,
    LicensedModule,
    ResourceAccess,
    download_ids,
    parse_permissions,
    parse_resource_access,
    resource_id,
)
from spskit.config import Settings
from spskit.download import (
    CREDENTIALS_PATH,
    DownloadGrant,
    credentials_body,
    parse_grant,
    save_bytes,
)
from spskit.signin import (
    PasswordUpdateRequiredError,
    authorization_code,
    parse_access_token,
    password_update_body,
    token_form,
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


def search_access(settings: Settings, exchange: Exchange) -> list[ResourceAccess]:
    """POST the launcher's permissions search. The body is an empty object."""
    headers = auth_headers(settings)
    headers["content-type"] = "application/json"
    status, raw = exchange("POST", f"{settings.gateway}/acl/permissions/search", b"{}", headers)
    return parse_resource_access(_json_body(status, raw))


def licensed_downloads(settings: Settings, exchange: Exchange) -> list[LicensedModule]:
    """The Techline Connect installer and any other decimal resource this account can run."""
    modules: list[LicensedModule] = []
    for raw_id in download_ids(search_access(settings, exchange)):
        modules.extend(list_modules(settings, raw_id, exchange))
    return modules


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
    payload = _finish_password_update(settings, payload, exchange)
    if payload.get("state") != "continue":
        again = challenge_from_body(payload)
        if again is not None:
            raise SessionExpiredError("the host asked for the code again")
        raise SessionExpiredError("verification did not continue")
    return payload


def _host_path(href: object, marker: str) -> str:
    if not isinstance(href, str) or not href.startswith("/") or "://" in href or "\\" in href or ".." in href:
        raise PasswordUpdateRequiredError("the sign-in link is not a path on the sign-in host")
    if marker not in href:
        raise PasswordUpdateRequiredError("the sign-in link is not the password method")
    return href


def _link(payload: Mapping[str, object], name: str) -> str | None:
    links = payload.get("_links")
    if not isinstance(links, Mapping):
        return None
    link = links.get(name)
    if not isinstance(link, Mapping):
        return None
    href = link.get("href")
    return href if isinstance(href, str) else None


def _post_json(
    settings: Settings,
    method: str,
    href: str,
    message: Mapping[str, str],
    exchange: Exchange,
) -> Mapping[str, object]:
    status, raw = exchange(
        method,
        settings.ciam + href,
        json.dumps(message).encode("utf-8"),
        {"content-type": "application/json", "accept": "application/json"},
    )
    if status == 504 and method == "PUT":
        status, raw = exchange(
            method,
            settings.ciam + href,
            json.dumps(message).encode("utf-8"),
            {"content-type": "application/json", "accept": "application/json"},
        )
    if status != 200:
        raise SessionExpiredError(f"the password step was refused ({status})")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise SessionExpiredError("the password step response is not an object")
    return payload


def _finish_password_update(
    settings: Settings, payload: Mapping[str, object], exchange: Exchange
) -> Mapping[str, object]:
    """Walk recover, then PUT newPassword, then poll. The password is only on that PUT."""
    token = payload.get("continuationToken")
    nxt = _link(payload, "next")
    if payload.get("state") == "continue" and isinstance(nxt, str) and nxt.endswith("/recover"):
        if not isinstance(token, str):
            raise PasswordUpdateRequiredError("missing continuation")
        payload = _post_json(
            settings, "POST", _host_path(nxt, "/auth/methods/password/"), {"continuationToken": token}, exchange
        )
        token = payload.get("continuationToken")
    if payload.get("state") != "methodUpdateRequired":
        return payload
    update = _link(payload, "update")
    if not isinstance(token, str):
        raise PasswordUpdateRequiredError("missing continuation")
    message = password_update_body(token, settings.new_password or settings.password)
    update_path = _host_path(update, "/auth/methods/password/")
    if update_path.rstrip("/").endswith("/recover") or update_path.rstrip("/").endswith("/pollUpdate"):
        raise PasswordUpdateRequiredError("the update link is not the password method")
    payload = _post_json(settings, "PUT", update_path, message, exchange)
    for _poll in range(5):
        if payload.get("state") != "methodUpdatePending":
            break
        token = payload.get("continuationToken")
        if not isinstance(token, str):
            raise PasswordUpdateRequiredError("missing continuation")
        payload = _post_json(
            settings,
            "POST",
            _host_path(_link(payload, "poll"), "/pollUpdate"),
            {"continuationToken": token},
            exchange,
        )
    return payload


def exchange_authorization_code(settings: Settings, redirect_url: str, exchange: Exchange) -> str:
    """Trade the redirect code for an access token. The refresh token in the response is discarded."""
    if not settings.code_verifier:
        raise SessionExpiredError("TDS_CODE_VERIFIER is empty")
    form = token_form(
        settings.client_id, settings.redirect_uri, authorization_code(redirect_url), settings.code_verifier
    )
    posted = dict(form).values()
    if any(secret and secret in posted for secret in (settings.password, settings.new_password)):
        raise SessionExpiredError("refusing to send the stored password to the token endpoint")
    url = f"{settings.ciam}/{settings.tenant}/oauth2/v2.0/token"
    origin = urllib.parse.urlsplit(settings.redirect_uri)
    status, raw = exchange(
        "POST",
        url,
        urllib.parse.urlencode(form).encode("utf-8"),
        {
            "content-type": "application/x-www-form-urlencoded",
            "accept": "application/json",
            "origin": f"{origin.scheme}://{origin.netloc}",
        },
    )
    if status != 200:
        raise SessionExpiredError(f"the token endpoint refused the code ({status}; {_token_error(raw)})")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise SessionExpiredError("token response is not an object")
    return parse_access_token(payload)


def _token_error(raw: bytes) -> str:
    """The OAuth error name and numeric codes. The description can echo the authorization code."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return "not json"
    if not isinstance(payload, dict):
        return "not an object"
    parts: list[str] = []
    error = payload.get("error")
    if isinstance(error, str) and re.fullmatch(r"[a-z_]{1,40}", error):
        parts.append(error)
    codes = payload.get("error_codes")
    if isinstance(codes, list):
        numbers = [str(code) for code in codes if isinstance(code, int)]
        if numbers:
            parts.append(",".join(numbers[:4]))
    description = payload.get("error_description")
    if isinstance(description, str):
        named = re.search(r"AADSTS\d{4,8}", description)
        if named is not None and named.group(0) not in parts:
            parts.append(named.group(0))
    return " ".join(parts) or "no error code"


def open_backend_session(settings: Settings, access_token: str, exchange: Exchange) -> None:
    """POST an empty body. The profile document in the response is not kept."""
    zone = urllib.parse.quote(settings.zone, safe="")
    url = f"{settings.backend}/api/v1/login?zoneId={zone}"
    site = urllib.parse.urlsplit(settings.redirect_uri)
    origin = f"{site.scheme}://{site.netloc}"
    apim = _apim_token(settings, exchange)
    status, raw = exchange(
        "POST",
        url,
        b"",
        {
            "Authorization": f"Bearer {apim}",
            "X-EEID-Access-Token": access_token,
            "Accept": "application/json, text/plain, */*",
            "Origin": origin,
            "Referer": origin + "/",
        },
    )
    if status != 200:
        raise SessionExpiredError(f"TDS login was refused ({status}; {_backend_error(raw)})")


def _apim_token(settings: Settings, exchange: Exchange) -> str:
    """The bearer API Management returns for the TDS site. It is not stored."""
    status, raw = exchange(
        "GET",
        settings.apim_token_url,
        None,
        {"accept": "application/json, text/plain, */*"},
    )
    if status != 200:
        raise SessionExpiredError(f"the API token was refused ({status})")
    token = _parse_apim_token(raw)
    if settings.password and settings.password in token:
        raise SessionExpiredError("refusing to send the stored password to TDS")
    return token


def _parse_apim_token(raw: bytes) -> str:
    text = raw.decode("utf-8").strip().strip('"')
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SessionExpiredError("the API token response has no token") from exc
        if not isinstance(payload, dict):
            raise SessionExpiredError("the API token response has no token")
        found = next(
            (
                payload.get(key)
                for key in ("access_token", "accessToken", "token", "bearerToken")
                if isinstance(payload.get(key), str)
            ),
            None,
        )
        if not isinstance(found, str):
            raise SessionExpiredError("the API token response has no token")
        text = found.strip()
    if text.count(".") != 2 or any(character.isspace() for character in text):
        raise SessionExpiredError("the API token response has no token")
    return text


def _backend_error(raw: bytes) -> str:
    """A short error name from the backend. A token or a profile is not included."""
    text = raw.decode("utf-8", "replace").strip()
    if re.fullmatch(r"[A-Za-z0-9 _.:-]{1,120}", text) and text.count(".") < 2 and "eyJ" not in text:
        return text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return "not json"
    if not isinstance(payload, dict):
        return "not an object"
    for key in ("error", "message", "title", "code"):
        value = payload.get(key)
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9 _.:-]{1,80}", value) and value.count(".") < 2:
            return value
    return "no error code"
