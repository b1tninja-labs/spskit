"""Gateway calls. The transport is injected so tests never open a socket."""

from __future__ import annotations

import json
import pathlib
import re
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Protocol

from spskit.catalog import (
    CatalogError,
    LicensedModule,
    ResourceAccess,
    catalog_ids,
    parse_permissions,
    parse_prelaunch,
    parse_resource_access,
    resource_id,
)
from spskit.config import Settings
from spskit.download import (
    CREDENTIALS_PATH,
    FILE_USER_AGENT,
    DownloadGrant,
    cached_file,
    credentials_body,
    parse_grant,
    save_cached,
)
from spskit.session import access_expiring, session_path, write_session
from spskit.signin import (
    PasswordUpdateRequiredError,
    TokenPair,
    authorization_code,
    parse_refresh_response,
    parse_token_pair,
    password_update_body,
    refresh_form,
    token_form,
)
from spskit.spsinfo import (
    SporefForm,
    SpsInfoError,
    VinCatalog,
    check_vin,
    parse_sporef_form,
    save_vin,
    sequence_request,
)
from spskit.verify import SessionExpiredError, VerificationChallenge, challenge_from_body, otp_message, prompt_code


class Exchange(Protocol):
    def __call__(self, method: str, url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, bytes]: ...


def acl_headers(bearer: str = "") -> dict[str, str]:
    """Gateway ACL and downloadCredentials.

    ``bearer`` is the SPS-INFO_ACCESS_TOKEN cookie from the SPOREF handoff. The EEID access
    token is the credential for backend.acdelcotds.com and is not sent here.
    """
    headers = {"accept": "application/json"}
    if bearer:
        headers["authorization"] = f"Bearer {bearer}"
    return headers


def permissions_url(settings: Settings, raw_id: str) -> str:
    return f"{settings.gateway}/acl/cdl/resources/{resource_id(raw_id)}/permissions"


def _json_body(status: int, raw: bytes) -> Mapping[str, object]:
    if status == 401:
        raise SessionExpiredError("the gateway refused the session")
    if status != 200:
        raise CatalogError(f"gateway status {status}")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise CatalogError("response is not an object")
    return payload


def list_modules(settings: Settings, raw_id: str, exchange: Exchange, bearer: str = "") -> list[LicensedModule]:
    status, raw = exchange("GET", permissions_url(settings, raw_id), None, acl_headers(bearer))
    return parse_permissions(_json_body(status, raw))


def search_access(settings: Settings, exchange: Exchange, bearer: str = "") -> list[ResourceAccess]:
    """POST the launcher's permissions search. The body is an empty object."""
    headers = acl_headers(bearer)
    headers["content-type"] = "application/json"
    status, raw = exchange("POST", f"{settings.gateway}/acl/permissions/search", b"{}", headers)
    return parse_resource_access(_json_body(status, raw))


def _present(status: int, raw: bytes) -> Mapping[str, object] | None:
    if status == 404:
        return None
    return _json_body(status, raw)


def prelaunch_ids(settings: Settings, exchange: Exchange, bearer: str = "") -> list[str]:
    """Ids from the update manager's prelaunch catalog. A missing route yields an empty list."""
    status, raw = exchange(
        "GET",
        f"{settings.gateway}/acl/cdl/resources/prelaunch",
        None,
        acl_headers(bearer),
    )
    payload = _present(status, raw)
    if payload is None:
        return []
    return parse_prelaunch(payload)


def required_versions(settings: Settings, exchange: Exchange, bearer: str = "") -> list[LicensedModule]:
    """Versions from GET /acl/cdl/permissions/search. A missing route yields an empty list."""
    status, raw = exchange(
        "GET",
        f"{settings.gateway}/acl/cdl/permissions/search",
        None,
        acl_headers(bearer),
    )
    payload = _present(status, raw)
    if payload is None:
        return []
    return parse_permissions(payload)


def _versions(settings: Settings, raw_id: str, exchange: Exchange, bearer: str = "") -> list[LicensedModule]:
    status, raw = exchange("GET", permissions_url(settings, raw_id), None, acl_headers(bearer))
    payload = _present(status, raw)
    if payload is None:
        return []
    return parse_permissions(payload)


def licensed_downloads(settings: Settings, exchange: Exchange, bearer: str = "") -> list[LicensedModule]:
    """Every licensed file version the gateway will list.

    That is the installer, TUM, each runnable decimal id, each prelaunch decimal id, and the
    versions from the update manager's permissions search. A disabled version is omitted.
    """
    modules: list[LicensedModule] = []
    seen: set[tuple[str, str]] = set()

    def add(found: list[LicensedModule]) -> None:
        for module in found:
            key = (module.resource_id, module.version)
            if key in seen:
                continue
            seen.add(key)
            modules.append(module)

    for raw_id in catalog_ids(search_access(settings, exchange, bearer), prelaunch_ids(settings, exchange, bearer)):
        add(_versions(settings, raw_id, exchange, bearer))
    add(required_versions(settings, exchange, bearer))
    return modules


def request_grant(settings: Settings, module: LicensedModule, exchange: Exchange, bearer: str = "") -> DownloadGrant:
    body = json.dumps(credentials_body(module)).encode("utf-8")
    headers = acl_headers(bearer)
    headers["content-type"] = "application/json"
    status, raw = exchange("POST", settings.gateway + CREDENTIALS_PATH, body, headers)
    return parse_grant(_json_body(status, raw))


def fetch_module(settings: Settings, module: LicensedModule, grant: DownloadGrant, exchange: Exchange) -> pathlib.Path:
    headers = dict(grant.headers)
    headers["User-Agent"] = FILE_USER_AGENT
    status, raw = exchange("GET", grant.url, None, headers)
    if status != 200:
        raise CatalogError(f"file status {status}")
    if not raw:
        raise CatalogError("file was empty")
    return save_cached(settings.download_dir, module, grant.filename, raw)


def store_licensed(
    settings: Settings,
    module: LicensedModule,
    exchange: Exchange,
    bearer: str = "",
    *,
    refresh: bool = False,
) -> tuple[pathlib.Path, bool]:
    """Write one version under cache/{id}/{version}/. A file already there is left in place."""
    if not refresh:
        hit = cached_file(settings.download_dir, module)
        if hit is not None:
            return hit, True
    grant = request_grant(settings, module, exchange, bearer)
    return fetch_module(settings, module, grant, exchange), False


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


def exchange_authorization_code(settings: Settings, redirect_url: str, exchange: Exchange) -> TokenPair:
    """Trade the redirect code for an access token and a refresh token."""
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
    return parse_token_pair(payload)


def refresh_access_token(settings: Settings, refresh_token: str, exchange: Exchange) -> TokenPair:
    """Exchange the refresh token for a new access token. RFC 6749 section 6."""
    form = refresh_form(settings.client_id, refresh_token)
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
        raise SessionExpiredError(f"the token endpoint refused the refresh token ({status}; {_token_error(raw)})")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise SessionExpiredError("token response is not an object")
    return parse_refresh_response(payload, refresh_token)


def renew_access_token(settings: Settings, exchange: Exchange) -> Settings:
    """Refresh the saved access token when it expires within a minute."""
    if not settings.refresh_token:
        return settings
    if settings.access_token and not access_expiring(settings.access_token):
        return settings
    pair = refresh_access_token(settings, settings.refresh_token, exchange)
    path = settings.token_file or session_path(settings)
    write_session(path, pair.access_token, refresh_token=pair.refresh_token)
    return replace(
        settings,
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_file=path,
    )


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


def _site_origin(settings: Settings) -> str:
    site = urllib.parse.urlsplit(settings.redirect_uri)
    return f"{site.scheme}://{site.netloc}"


def _sps_document(status: int, raw: bytes, step: str) -> dict[str, object]:
    if status == 401:
        raise SessionExpiredError("the TDS session expired")
    if status != 200:
        raise SpsInfoError(f"SPS Info {step} status {status}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpsInfoError("SPS Info did not return a document") from exc
    if not isinstance(payload, dict):
        raise SpsInfoError("SPS Info did not return a document")
    return payload


def request_sps_form(settings: Settings, exchange: Exchange) -> SporefForm:
    """GET the SPOREF page with the API Management bearer and the saved access token."""
    if not settings.access_token:
        raise SessionExpiredError("there is no saved session")
    origin = _site_origin(settings)
    apim = _apim_token(settings, exchange)
    headers = {
        "Authorization": f"Bearer {apim}",
        "X-EEID-Access-Token": settings.access_token,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Origin": origin,
        "Referer": origin + "/",
    }
    status, raw = 500, b""
    for _attempt in range(3):
        status, raw = exchange(
            "GET",
            f"{settings.backend}/api/v1/spsCallibration/accessSPSCal",
            None,
            headers,
        )
        if status == 200:
            return parse_sporef_form(raw)
        if status != 500:
            break
    raise SessionExpiredError(f"SPS Info was refused ({status}; {_backend_error(raw)})")


def open_gateway_session(settings: Settings, exchange: Exchange) -> None:
    """Post the SPOREF handoff so the gateway can set session cookies.

    The EEID access token is sent only on the backend page that returns the form.
    The gateway post does not carry it as Authorization.
    """
    submit_sporef_form(settings, request_sps_form(settings, exchange), exchange)


def submit_sporef_form(settings: Settings, form: SporefForm, exchange: Exchange) -> None:
    """POST the handoff form to the gateway. The field values are not logged."""
    target = urllib.parse.urlsplit(form.action)
    gateway = urllib.parse.urlsplit(settings.gateway)
    if target.scheme != "https" or not target.hostname or target.hostname != gateway.hostname:
        raise SpsInfoError("the SPS Info form is not on the gateway")
    origin = _site_origin(settings)
    status, _raw = exchange(
        "POST",
        form.action,
        urllib.parse.urlencode(form.fields).encode("utf-8"),
        {
            "content-type": "application/x-www-form-urlencoded",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Origin": origin,
            "Referer": origin + "/",
        },
    )
    if status != 200:
        raise SpsInfoError(f"SPS Info was refused ({status})")


def sync_sps_vin(settings: Settings, vin: str, bearer: str, exchange: Exchange) -> VinCatalog:
    """GET the fixture, POST that same document to the programming sequence, and store the catalog."""
    checked = check_vin(vin)
    if not bearer or any(character.isspace() for character in bearer):
        raise SpsInfoError("SPS Info did not return a session")
    headers = {"Authorization": f"Bearer {bearer}", "Accept": "application/json, text/plain, */*"}
    status, raw = exchange("GET", f"{settings.gateway}/spsinfo/vin/fixture/{checked}", None, headers)
    fixture = _sps_document(status, raw, "fixture")
    gateway = urllib.parse.urlsplit(settings.gateway)
    status, sequence_raw = exchange(
        "POST",
        f"{settings.gateway}/spsinfo/progseq",
        json.dumps(sequence_request(fixture), ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        {
            "Authorization": f"Bearer {bearer}",
            "Accept": "*/*",
            "content-type": "application/json",
            "Origin": f"{gateway.scheme}://{gateway.netloc}",
        },
    )
    sequence = _sps_document(status, sequence_raw, "sequence")
    return save_vin(settings.download_dir / "spsinfo.sqlite", checked, fixture, sequence)
