"""Sign in with the password, then the email code the host sends.

The browser does this in order: the authorize page, GetCredentialType, the login
form (`passwd`), then `POST /common/SAS/BeginAuth` with `AuthMethodId` `Email`.
That call is what sends the code. The person types it, and `POST /common/SAS/ProcessAuth`
carries it as `otc`. The next page is the stay-signed-in form, posted to `/kmsi`,
and that response redirects to the TDS site with the authorization code in the fragment.
Password recovery is not part of this path.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import secrets
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from spskit.client import Exchange
from spskit.config import Settings
from spskit.signin import PUBLIC_CLIENT_ID, authorization_code
from spskit.verify import VerificationError

_CONFIG = "$Config="
_BEGIN = "/common/SAS/BeginAuth"
_PROCESS = "/common/SAS/ProcessAuth"
_KMSI = "/kmsi"
_COOKIE_NAME = re.compile(r"^[A-Za-z0-9_]{1,40}$")
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class LoginError(VerificationError):
    """The sign-in host did not accept the password or the email code."""


@dataclass(frozen=True, slots=True)
class MfaChallenge:
    """What the code form posts, apart from the code itself. The code is not stored here."""

    code_length: int
    flow_token: str
    request_ctx: str
    canary: str
    hpg_request_id: str
    username: str


@dataclass(frozen=True, slots=True)
class EmailRequest:
    challenge: MfaChallenge
    code_verifier: str


def code_verifier() -> str:
    return secrets.token_urlsafe(32)


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def authorize_url(settings: Settings, verifier: str) -> str:
    """The authorize URL the browser opened, with a verifier this process generated."""
    query = urllib.parse.urlencode(
        {
            "client_id": settings.client_id or PUBLIC_CLIENT_ID,
            "scope": f"{settings.client_id or PUBLIC_CLIENT_ID}/.default openid profile offline_access",
            "redirect_uri": settings.redirect_uri,
            "response_mode": "fragment",
            "client_info": "1",
            "prompt": "login",
            "nonce": secrets.token_urlsafe(16),
            "state": secrets.token_urlsafe(16),
            "response_type": "code",
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return f"{settings.ciam}/{settings.tenant}/oauth2/v2.0/authorize?{query}"


def redirect_location(url: str) -> str | None:
    """The TDS redirect, when this Location's fragment carries the authorization code."""
    if "code" not in urllib.parse.parse_qs(urllib.parse.urlsplit(url).fragment):
        return None
    return url


def parse_page_config(html: str) -> dict[str, object] | None:
    """Return the `$Config` object that carries `sFT`, if this page has one."""
    start = 0
    while True:
        marker = html.find(_CONFIG, start)
        if marker < 0:
            return None
        brace = html.find("{", marker)
        if brace < 0:
            return None
        try:
            obj, _end = json.JSONDecoder().raw_decode(html[brace:])
        except json.JSONDecodeError:
            start = marker + len(_CONFIG)
            continue
        if isinstance(obj, dict) and isinstance(obj.get("sFT"), str) and obj["sFT"]:
            return obj
        start = brace + 1


def credential_type_message(config: Mapping[str, object], username: str) -> dict[str, object]:
    """The GetCredentialType body. `flowToken` is the page's `sFT` and `originalRequest` is `sCtx`."""
    flow = config.get("sFT")
    original = config.get("sCtx")
    if not isinstance(flow, str) or not flow or not isinstance(original, str) or not original:
        raise LoginError("the sign-in page did not include a flow token")
    country = config.get("country")
    return {
        "checkPhones": False,
        "country": country if isinstance(country, str) and len(country) == 2 else "US",
        "federationFlags": 0,
        "flowToken": flow,
        "forceotclogin": False,
        "isCookieBannerShown": False,
        "isExternalFederationDisallowed": False,
        "isFederationDisabled": False,
        "isFidoSupported": True,
        "isOtherIdpSupported": False,
        "isReactLoginRequest": True,
        "isRemoteConnectSupported": False,
        "isRemoteNGCSupported": True,
        "isSignup": False,
        "originalRequest": original,
        "otclogindisallowed": False,
        "uaid": "",
        "username": username,
        "isAccessPassSupported": True,
        "isQrCodePinSupported": True,
    }


def sign_in_password(settings: Settings) -> str:
    """The password the login form posts. The reset value is current once it has been set."""
    password = settings.new_password or settings.password
    if not password:
        raise LoginError("set TDS_PASSWORD or TDS_NEW_PASSWORD")
    return password


def login_form(config: Mapping[str, object], username: str, password: str, flow_token: str) -> list[tuple[str, str]]:
    """The password form the browser posted. The password is only the `passwd` field."""
    canary = _text(config, "canary") or _text(config, "apiCanary")
    ctx = _text(config, "sCtx")
    request_id = _text(config, "correlationId")
    if not canary or not ctx or not flow_token or not request_id:
        raise LoginError("the sign-in page did not include a flow token")
    return [
        ("passwd", password),
        ("ps", "2"),
        ("psRNGCDefaultType", ""),
        ("psRNGCEntropy", ""),
        ("psRNGCSLK", ""),
        ("isReactBundle", "1"),
        ("canary", canary),
        ("ctx", ctx),
        ("hpgrequestid", request_id),
        ("flowToken", flow_token),
        ("PPSX", ""),
        ("NewUser", "1"),
        ("FoundMSAs", ""),
        ("fspost", "0"),
        ("i21", "0"),
        ("CookieDisclosure", "0"),
        ("IsFidoSupported", "1"),
        ("isSignupPost", "0"),
        ("i13", "0"),
        ("login", username),
        ("loginfmt", username),
        ("type", "11"),
        ("LoginOptions", "3"),
        ("lrt", ""),
        ("lrtPartition", ""),
        ("hisRegion", ""),
        ("hisScaleUnit", ""),
    ]


def page_headers(config: Mapping[str, object], referer: str) -> dict[str, str]:
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "referer": referer,
        "user-agent": _UA,
    }
    pairs = (
        ("canary", "apiCanary"),
        ("client-request-id", "correlationId"),
        ("correlationId", "correlationId"),
        ("hpgact", "hpgact"),
        ("hpgid", "hpgid"),
        ("sessionId", "sessionId"),
    )
    for header, key in pairs:
        value = config.get(key)
        if isinstance(value, str) and value:
            headers[header] = value
        elif isinstance(value, int):
            headers[header] = str(value)
    return headers


def prompt_email_code(code_length: int, reader: Callable[[str], str]) -> str:
    """Ask once. The returned code is for the caller to send; this function keeps no copy."""
    typed = reader(f"Enter the email code ({code_length} characters): ").strip()
    if len(typed) != code_length or not typed.isalnum():
        raise LoginError(f"the code must be {code_length} letters or digits")
    return typed


def request_email_code(settings: Settings, exchange: Exchange) -> EmailRequest:
    """Open the sign-in page, post the password, and ask the host to email a code.

    The returned challenge is what `submit_email_code` posts after the person types the code.
    The code itself is not requested here, and password recovery is not called.
    """
    if not settings.username or any(character.isspace() for character in settings.username):
        raise LoginError("TDS_USERNAME is empty")
    password = sign_in_password(settings)
    verifier = code_verifier()
    config, page_url = _load_config(settings, exchange, authorize_url(settings, verifier))
    headers = page_headers(config, page_url)
    credential = _json_call(
        exchange,
        f"{settings.ciam}/common/GetCredentialType",
        credential_type_message(config, settings.username),
        headers,
    )
    if credential.get("IfExistsResult") not in (0, None):
        raise LoginError("the username was not accepted")
    refreshed = credential.get("apiCanary")
    if isinstance(refreshed, str):
        headers = dict(headers)
        headers["canary"] = refreshed
    flow = credential.get("FlowToken")
    flow_token = flow if isinstance(flow, str) and flow else _text(config, "sFT")
    login_url = f"{settings.ciam}/{settings.tenant}/login"
    status, raw = _form_call(
        exchange,
        login_url,
        login_form(config, settings.username, password, flow_token),
        page_url,
    )
    del password
    if status != 200:
        raise LoginError(f"the sign-in host refused the password ({status})")
    signed_in = parse_page_config(raw.decode("utf-8", errors="replace"))
    if signed_in is None:
        status, raw = _post_redirect(settings, exchange, raw.decode("utf-8", errors="replace"), login_url)
        if status != 200:
            raise LoginError(f"the sign-in host refused the password ({status})")
        signed_in = parse_page_config(raw.decode("utf-8", errors="replace"))
    if signed_in is None:
        raise LoginError("the sign-in page did not include a flow token")
    if _error_code(signed_in) == "50126":
        raise LoginError("the username or password was not accepted")
    if not _asks_for_email(signed_in):
        raise LoginError("the sign-in host did not ask for an email code")
    started = _json_call(
        exchange,
        _begin_url(settings, signed_in),
        {
            "AuthMethodId": "Email",
            "Method": "BeginAuth",
            "ctx": _text(signed_in, "sCtx"),
            "flowToken": _text(signed_in, "sFT"),
        },
        page_headers(signed_in, page_url),
    )
    return EmailRequest(_challenge(settings, signed_in, started), verifier)


def submit_email_code(settings: Settings, requested: EmailRequest, code: str, exchange: Exchange) -> str:
    """Post the typed code, accept the stay-signed-in page, and return the TDS redirect."""
    challenge = requested.challenge
    if len(code) != challenge.code_length or not code.isalnum():
        raise LoginError(f"the code must be {challenge.code_length} letters or digits")
    fields = [
        ("otc", code),
        ("canary", challenge.canary),
        ("flowToken", challenge.flow_token),
        ("request", challenge.request_ctx),
        ("login", challenge.username),
        ("hpgrequestid", challenge.hpg_request_id),
        ("mfaAuthMethod", "Email"),
    ]
    status, raw = _form_call(exchange, f"{settings.ciam}{_PROCESS}", fields, settings.ciam + _PROCESS)
    del code
    del fields
    if status != 200:
        raise LoginError(f"the email code was refused ({status})")
    page = parse_page_config(raw.decode("utf-8", errors="replace"))
    if page is None:
        raise LoginError("the email code was not accepted")
    kmsi = [
        ("LoginOptions", "1"),
        ("type", "28"),
        ("ctx", _text(page, "sCtx")),
        ("hpgrequestid", _text(page, "correlationId")),
        ("flowToken", _text(page, "sFT")),
        ("canary", _text(page, "canary") or _text(page, "apiCanary")),
        ("i19", "0"),
    ]
    if not all(value for name, value in kmsi if name != "i19"):
        raise LoginError("the email code was not accepted")
    status, raw = _form_call(exchange, _kmsi_url(settings, page), kmsi, settings.ciam + _PROCESS)
    return _redirect_url(status, raw)


def _sso_reload(url: str) -> str:
    """The authorize URL the redirect page loads next. `sso_reload=true` is the only addition."""
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    if not any(key == "sso_reload" for key, _value in query):
        query.append(("sso_reload", "true"))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), ""))


def _load_config(settings: Settings, exchange: Exchange, page_url: str) -> tuple[dict[str, object], str]:
    """Return the page config and the URL that carried it.

    The first authorize response is a Redirecting page with no `sFT`. The browser then
    requests the same URL with `sso_reload=true`, and that response is the sign-in form.
    """
    html_headers = {"accept": "text/html", "user-agent": _UA}
    status, raw = exchange("GET", page_url, None, html_headers)
    if status != 200:
        raise LoginError(f"the sign-in page was refused ({status})")
    config = parse_page_config(raw.decode("utf-8", errors="replace"))
    loaded = page_url
    if config is None:
        loaded = _sso_reload(page_url)
        status, raw = exchange("GET", loaded, None, {**html_headers, "referer": page_url})
        if status != 200:
            raise LoginError(f"the sign-in page was refused ({status})")
        config = parse_page_config(raw.decode("utf-8", errors="replace"))
    if config is None:
        raise LoginError("the sign-in page did not include a flow token")
    if urllib.parse.urlsplit(loaded).hostname != urllib.parse.urlsplit(settings.ciam).hostname:
        raise LoginError("the sign-in page is not on the sign-in host")
    return config, loaded


def _challenge(settings: Settings, page: Mapping[str, object], started: Mapping[str, object]) -> MfaChallenge:
    if started.get("Success") is not True or started.get("ErrCode") != 0 or started.get("ResultValue") != "Success":
        raise LoginError("the sign-in host did not email a code")
    flow = started.get("FlowToken")
    ctx = started.get("Ctx")
    if not isinstance(flow, str) or not flow or not isinstance(ctx, str) or not ctx:
        raise LoginError("the sign-in host did not email a code")
    correlation = started.get("CorrelationId")
    request_id = correlation if isinstance(correlation, str) and correlation else _text(page, "correlationId")
    canary = _text(page, "canary") or _text(page, "apiCanary")
    length = page.get("iEmailOtcLength")
    code_length = length if isinstance(length, int) and 4 <= length <= 12 else 8
    if not canary or not request_id:
        raise LoginError("the sign-in page did not include a flow token")
    return MfaChallenge(code_length, flow, ctx, canary, request_id, settings.username)


def _asks_for_email(config: Mapping[str, object]) -> bool:
    if _error_code(config) == "50074" or config.get("pgid") == "FabricTFA":
        return True
    begin = _text(config, "urlBeginAuth")
    return begin.endswith(_BEGIN)


def _begin_url(settings: Settings, config: Mapping[str, object]) -> str:
    raw = _text(config, "urlBeginAuth")
    url = _ciam_url(settings, raw) if raw else f"{settings.ciam}{_BEGIN}"
    if urllib.parse.urlsplit(url).path.rstrip("/") != _BEGIN:
        raise LoginError("the sign-in host did not ask for an email code")
    return url


def _kmsi_url(settings: Settings, config: Mapping[str, object]) -> str:
    raw = _text(config, "urlPost")
    if raw:
        url = _ciam_url(settings, raw)
        if urllib.parse.urlsplit(url).path.rstrip("/").endswith(_KMSI):
            return url
    if config.get("pgid") == "KmsiInterrupt":
        return f"{settings.ciam}{_KMSI}"
    raise LoginError("the email code was not accepted")


def _redirect_url(status: int, raw: bytes) -> str:
    if status not in (301, 302, 303, 307, 308):
        raise LoginError("the sign-in host did not return the TDS redirect")
    location = raw.decode("utf-8", errors="replace").strip()
    authorization_code(location)
    return location


def _page_object(html_text: str) -> dict[str, object] | None:
    """The first `$Config` object, including the redirect page that has no `sFT`."""
    start = 0
    while True:
        marker = html_text.find(_CONFIG, start)
        if marker < 0:
            return None
        brace = html_text.find("{", marker)
        if brace < 0:
            return None
        try:
            obj, _end = json.JSONDecoder().raw_decode(html_text[brace:])
        except json.JSONDecodeError:
            start = marker + len(_CONFIG)
            continue
        if isinstance(obj, dict):
            return obj
        start = brace + 1


def _post_redirect(settings: Settings, exchange: Exchange, html_text: str, referer: str) -> tuple[int, bytes]:
    """Post the redirect page's own form back, with `sso_reload=true`.

    That page is the browser-SSO interrupt. Its script posts `oPostParams` to `urlPost`
    after setting the `ssoPulled` cookie, and the next response is the sign-in form.
    """
    obj = _page_object(html_text)
    params = obj.get("oPostParams") if isinstance(obj, dict) else None
    posted = _text(obj, "urlPost") if isinstance(obj, dict) else ""
    if not isinstance(obj, dict) or not isinstance(params, dict) or not posted:
        raise LoginError("the sign-in page did not include a flow token")
    target = _ciam_url(settings, posted)
    if "sso_reload=" not in target:
        target += "&sso_reload=true" if urllib.parse.urlsplit(target).query else "?sso_reload=true"
    fields: list[tuple[str, str]] = []
    for key, value in params.items():
        if isinstance(key, str) and isinstance(value, str):
            fields.append((html.unescape(key), html.unescape(value)))
    if not fields:
        raise LoginError("the sign-in page did not include a flow token")
    return _form_call(exchange, target, fields, referer, {"cookie": f"{_sso_cookie(obj)}=1"})


def _sso_cookie(config: Mapping[str, object]) -> str:
    bsso = config.get("bsso")
    names = bsso.get("cookieNames") if isinstance(bsso, Mapping) else None
    pulled = names.get("ssoPulled") if isinstance(names, Mapping) else None
    if isinstance(pulled, str) and _COOKIE_NAME.fullmatch(pulled):
        return pulled
    return "SSOCOOKIEPULLED"


def _form_call(
    exchange: Exchange,
    url: str,
    fields: list[tuple[str, str]],
    referer: str,
    extra: Mapping[str, str] | None = None,
) -> tuple[int, bytes]:
    headers = {
        "accept": "text/html",
        "content-type": "application/x-www-form-urlencoded",
        "referer": referer,
        "user-agent": _UA,
    }
    if extra:
        headers.update(extra)
    return exchange("POST", url, urllib.parse.urlencode(fields).encode("utf-8"), headers)


def _json_call(
    exchange: Exchange,
    url: str,
    message: Mapping[str, object],
    headers: Mapping[str, str],
) -> Mapping[str, object]:
    status, raw = exchange("POST", url, json.dumps(message).encode("utf-8"), headers)
    if status != 200:
        raise LoginError(f"the sign-in host refused the email step ({status})")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise LoginError("the sign-in host did not return JSON") from exc
    if not isinstance(payload, dict):
        raise LoginError("the sign-in host did not return JSON")
    return payload


def _ciam_url(settings: Settings, url: str) -> str:
    host = urllib.parse.urlsplit(settings.ciam).hostname
    if url.startswith("/") and "://" not in url and "\\" not in url and ".." not in url:
        return settings.ciam + url
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https" and parts.hostname == host and ".." not in parts.path:
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    raise LoginError("the sign-in link is not on the sign-in host")


def _text(config: Mapping[str, object], key: str) -> str:
    value = config.get(key)
    if isinstance(value, str) and value:
        return value
    return ""


def _error_code(config: Mapping[str, object]) -> str:
    value = config.get("sErrorCode")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    return ""
