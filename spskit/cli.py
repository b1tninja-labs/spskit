"""Command line. Network access lives here; the library functions take an exchange."""

from __future__ import annotations

import argparse
import contextlib
import errno
import http.client
import http.cookiejar
import json
import pathlib
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Buffer, Callable, Mapping, Sequence
from dataclasses import replace
from http.client import HTTPMessage
from typing import IO

from spskit.catalog import LicensedModule
from spskit.client import (
    Exchange,
    exchange_authorization_code,
    licensed_downloads,
    list_modules,
    open_backend_session,
    open_gateway_session,
    renew_access_token,
    request_sps_form,
    store_licensed,
    submit_code,
    submit_sporef_form,
    sync_sps_vin,
)
from spskit.config import ConfigError, Settings, load_settings
from spskit.download import refuse_storage_redirect
from spskit.login_start import (
    BROWSER_USER_AGENT,
    CodeRejectedError,
    EmailRequest,
    LoginError,
    MfaChallenge,
    post_stay_signed_in,
    prompt_email_code,
    redirect_location,
    request_email_code,
    submit_email_code,
)
from spskit.session import (
    SavedSignIn,
    apply_saved_session,
    clear_sign_in,
    prompt_emailed_token,
    read_backend_pending,
    read_cookies,
    read_pending,
    read_signin,
    read_stay,
    session_path,
    write_cookies,
    write_session,
    write_signin,
    write_stay,
)
from spskit.spsinfo import SpsInfoError, check_vin
from spskit.verify import SessionExpiredError, parse_challenge


class _AuthorizationRedirectError(Exception):
    """The stay-signed-in response pointed at the TDS redirect. The code stays on the location."""

    def __init__(self, location: str) -> None:
        super().__init__("authorization redirect")
        self.location = location


class _TryingHTTPSConnection(http.client.HTTPSConnection):
    """Handshake each address. A reset on one address does not abandon the rest."""

    def connect(self) -> None:
        sys.audit("http.client.connect", self, self.host, self.port)
        last: OSError | None = None
        infos = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        source = getattr(self, "source_address", None)
        context = getattr(self, "_context", None)
        if not isinstance(context, ssl.SSLContext):
            raise OSError("the sign-in connection has no TLS context")
        for family, socktype, proto, _canon, address in infos:
            raw = socket.socket(family, socktype, proto)
            if isinstance(self.timeout, (int, float)):
                raw.settimeout(self.timeout)
            try:
                if source:
                    raw.bind(source)
                raw.connect(address)
                try:
                    raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError as exc:
                    if exc.errno != errno.ENOPROTOOPT:
                        raise
                self.sock = context.wrap_socket(raw, server_hostname=self.host)
                return
            except OSError as exc:
                last = exc
                self.sock = None
                with contextlib.suppress(OSError):
                    raw.close()
        if last is not None:
            raise last
        raise OSError(f"no address for {self.host}")

    def putheader(self, header: str | bytes, *values: Buffer | str | int) -> None:
        text = header.decode("ascii") if isinstance(header, bytes) else header
        super().putheader(_EXACT_HEADERS.get(text.lower(), text), *values)


class _HTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        context = getattr(self, "_context", None)
        return self.do_open(_TryingHTTPSConnection, req, context=context)


class _CodeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        location = redirect_location(newurl)
        if location is not None:
            raise _AuthorizationRedirectError(location)
        refuse_storage_redirect(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_JAR),
    _CodeRedirect(),
    _HTTPS(),
)
_RETRY_DELAYS = (1.0, 2.0, 4.0)
_COOKIE_NAME = re.compile(r"^[A-Za-z0-9_]{1,40}$")
_EXACT_HEADERS = {
    "user-agent": "User-Agent",
    "x-eeid-access-token": "X-EEID-Access-Token",
}


def _store_cookie(url: str, header: str) -> None:
    """Keep one extra cookie on the jar. The jar still sends the cookies the host set."""
    name, separator, value = header.strip().partition("=")
    if separator != "=" or _COOKIE_NAME.fullmatch(name) is None or not value or any(c in value for c in "\r\n;"):
        return
    parts = urllib.parse.urlsplit(url)
    if not parts.hostname:
        return
    _JAR.set_cookie(
        http.cookiejar.Cookie(
            0,
            name,
            value,
            None,
            False,
            parts.hostname,
            True,
            False,
            "/",
            True,
            True,
            int(time.time()) + 60,
            False,
            None,
            None,
            {},
        )
    )


def urllib_exchange(
    method: str,
    url: str,
    body: bytes | None,
    headers: Mapping[str, str],
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[int, bytes]:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise SessionExpiredError("refusing a URL that is not https")
    outgoing = dict(headers)
    if not any(name.lower() == "user-agent" for name in outgoing):
        outgoing["User-Agent"] = BROWSER_USER_AGENT
    extra_cookie = outgoing.pop("cookie", None)
    if extra_cookie:
        _store_cookie(url, extra_cookie)
    request = urllib.request.Request(url, data=body, headers=outgoing, method=method)  # noqa: S310
    delays = iter(_RETRY_DELAYS)
    while True:
        try:
            with _OPENER.open(request, timeout=60) as response:
                return response.status, response.read()
        except _AuthorizationRedirectError as exc:
            return 302, exc.location.encode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except urllib.error.URLError as exc:
            if not _transient(exc):
                raise LoginError("the sign-in host could not be reached") from exc
            delay = next(delays, None)
            if delay is None:
                raise LoginError("the sign-in host closed the connection") from exc
            print("the sign-in host closed the connection; retrying", file=sys.stderr)
            sleeper(delay)


def gateway_cookie_names(host: str) -> list[str]:
    """Cookie names the gateway set. Values stay in the jar and are not returned."""
    host = host.lower()
    names: list[str] = []
    for cookie in _JAR:
        domain = (cookie.domain or "").lstrip(".").lower()
        if not domain or (host != domain and not host.endswith("." + domain)):
            continue
        if cookie.name not in names:
            names.append(cookie.name)
    return names


def _gateway_bearer(settings: Settings, exchange: Exchange) -> str:
    """Read the SPOREF cookie and use it as the gateway bearer. The EEID token is not.

    A test exchange does not store Set-Cookie, so it returns an empty bearer. The real
    transport reads SPS-INFO_ACCESS_TOKEN from the jar after the handoff.
    """
    if not settings.access_token:
        return ""
    open_gateway_session(settings, exchange)
    if exchange is not urllib_exchange:
        return ""
    return sps_info_bearer()


def sps_info_bearer() -> str:
    """The SPS Info cookie is the bearer. The page removes that cookie; the value is not printed."""
    found: str | None = None
    for cookie in list(_JAR):
        if cookie.name != "SPS-INFO_ACCESS_TOKEN":
            continue
        if cookie.value and found is None:
            found = cookie.value
        _JAR.clear(cookie.domain, cookie.path, cookie.name)
    if not found:
        raise SpsInfoError("SPS Info did not return a session")
    return found


def _transient(exc: urllib.error.URLError) -> bool:
    reason = exc.reason
    if isinstance(reason, ssl.SSLCertVerificationError):
        return False
    return isinstance(reason, (TimeoutError, ConnectionError, OSError))


def format_module(module: LicensedModule) -> str:
    return f"{module.resource_id}\t{module.version}\t{module.type_code}\t{module.name}"


def _cookie_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for cookie in _JAR:
        records.append(
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": bool(cookie.secure),
                "expires": cookie.expires,
            }
        )
    return records


def _restore_cookie(record: Mapping[str, object]) -> None:
    name = record.get("name")
    value = record.get("value")
    domain = record.get("domain")
    path = record.get("path")
    if not isinstance(name, str) or _COOKIE_NAME.fullmatch(name) is None:
        return
    if not isinstance(value, str) or not value or any(char in value for char in "\r\n;"):
        return
    if not isinstance(domain, str) or not domain or not isinstance(path, str) or not path:
        return
    expires = record.get("expires")
    expires_at = expires if isinstance(expires, int) else None
    _JAR.set_cookie(
        http.cookiejar.Cookie(
            0,
            name,
            value,
            None,
            False,
            domain,
            True,
            domain.startswith("."),
            path,
            True,
            bool(record.get("secure", True)),
            expires_at,
            expires_at is None,
            None,
            None,
            {},
        )
    )


def _persist_cookies(path: pathlib.Path, exchange: Exchange) -> None:
    if exchange is not urllib_exchange:
        return
    write_cookies(path, _cookie_records())


def _load_cookies(path: pathlib.Path, exchange: Exchange) -> None:
    if exchange is not urllib_exchange:
        return
    _JAR.clear()
    for record in read_cookies(path):
        _restore_cookie(record)


def _remember_signin(path: pathlib.Path, requested: EmailRequest, exchange: Exchange) -> None:
    challenge = requested.challenge
    write_signin(
        path,
        code_length=challenge.code_length,
        flow_token=challenge.flow_token,
        request_ctx=challenge.request_ctx,
        canary=challenge.canary,
        hpg_request_id=challenge.hpg_request_id,
        username=challenge.username,
        code_verifier=requested.code_verifier,
    )
    _persist_cookies(path, exchange)


def _requested(saved: SavedSignIn) -> EmailRequest:
    return EmailRequest(
        MfaChallenge(
            saved.code_length,
            saved.flow_token,
            saved.request_ctx,
            saved.canary,
            saved.hpg_request_id,
            saved.username,
        ),
        saved.code_verifier,
    )


def run(
    argv: Sequence[str],
    exchange: Exchange = urllib_exchange,
    reader: Callable[[str], str] = input,
    stdin_text: str | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="spskit", description="Download licensed SPS2 modules.")
    parser.add_argument("--env", default=".env", help="path to the env file (default: .env)")
    sub = parser.add_subparsers(dest="command", required=True)
    modules = sub.add_parser("modules", help="list versions of one licensed resource")
    modules.add_argument("--id", required=True, help="decimal resource id")
    download = sub.add_parser("download", help="download every version of one licensed resource")
    download.add_argument("--id", required=True, help="decimal resource id")
    downloads = sub.add_parser(
        "downloads",
        help="list licensed files, including the Techline Connect installer",
    )
    downloads.add_argument("--get", action="store_true", dest="fetch", help="download each listed file into the cache")
    downloads.add_argument(
        "--refresh", action="store_true", help="fetch again even when the cache already has the file"
    )
    download.add_argument("--refresh", action="store_true", help="fetch again even when the cache already has the file")
    sub.add_parser("login", help="sign in with the password and ask the host to email a code")
    sub.add_parser("code", help="enter the emailed code for the saved challenge")
    sub.add_parser("verify", help="prompt for the emailed code, or read a challenge on stdin")
    sub.add_parser("session", help="save an access token the person already holds")
    token = sub.add_parser("token", help="exchange the TDS redirect for an access token")
    token.add_argument("--redirect", required=True, help="the https://www.acdelcotds.com/#code=... URL")
    sps = sub.add_parser("sps", help="save the SPS Info catalog for one VIN")
    sps.add_argument("--vin", required=True, help="17-character VIN")
    args = parser.parse_args(list(argv))
    try:
        settings = load_settings(pathlib.Path(args.env))
        if args.command == "login":
            if exchange is urllib_exchange:
                _JAR.clear()
            requested = request_email_code(settings, exchange)
            path = session_path(settings)
            _remember_signin(path, requested, exchange)
            print(f"Email challenge sent ({requested.challenge.code_length} characters).")
            print("Run python -m spskit code to enter it. Repeat that command if the connection drops.")
            return 0
        if args.command == "code":
            path = session_path(settings)
            pending = read_backend_pending(path)
            if pending is not None:
                open_backend_session(settings, pending, exchange)
                write_session(path, pending)
                clear_sign_in(path)
                print(f"wrote the session to {path}")
                return 0
            _load_cookies(path, exchange)
            stay = read_stay(path)
            if stay is not None:
                print("The email code was already accepted. Finishing the sign-in.", file=sys.stderr)
                redirect = post_stay_signed_in(settings, stay.url, list(stay.fields), exchange)
                verifier = stay.code_verifier
            else:
                requested = _requested(read_signin(path))
                verifier = requested.code_verifier

                def remember(url: str, fields: list[tuple[str, str]]) -> None:
                    write_stay(path, url, fields, verifier)
                    _persist_cookies(path, exchange)

                while True:
                    try:
                        code = prompt_email_code(requested.challenge.code_length, reader)
                    except LoginError as exc:
                        print(str(exc), file=sys.stderr)
                        continue
                    try:
                        redirect = submit_email_code(settings, requested, code, exchange, on_stay=remember)
                    except CodeRejectedError as rejected:
                        print("That code was rejected.", file=sys.stderr)
                        requested = EmailRequest(rejected.challenge, verifier)
                        _remember_signin(path, requested, exchange)
                        del code
                        continue
                    del code
                    break
            settings = replace(settings, code_verifier=verifier)
            pair = exchange_authorization_code(settings, redirect, exchange)
            write_session(path, pair.access_token, refresh_token=pair.refresh_token, backend_pending=True)
            open_backend_session(settings, pair.access_token, exchange)
            write_session(path, pair.access_token, refresh_token=pair.refresh_token)
            clear_sign_in(path)
            print(f"wrote the session to {path}")
            return 0
        if args.command == "session":
            emailed = prompt_emailed_token(reader)
            path = session_path(settings)
            write_session(path, emailed)
            print(f"wrote the session to {path}")
            return 0
        settings = renew_access_token(apply_saved_session(settings), exchange)
        if args.command == "token":
            pair = exchange_authorization_code(settings, args.redirect, exchange)
            path = session_path(settings)
            write_session(path, pair.access_token, refresh_token=pair.refresh_token, backend_pending=True)
            open_backend_session(settings, pair.access_token, exchange)
            write_session(path, pair.access_token, refresh_token=pair.refresh_token)
            print(f"wrote the session to {path}")
            return 0
        if args.command == "verify":
            if stdin_text == "" or (stdin_text is None and sys.stdin.isatty()):
                challenge = read_pending(session_path(settings))
            else:
                raw = sys.stdin.read() if stdin_text is None else stdin_text
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise SessionExpiredError("the challenge is not an object")
                challenge = parse_challenge(payload)
            result = submit_code(settings, challenge, reader, exchange)
            print(f"verification state: {result.get('state')}")
            return 0
        if args.command == "sps":
            check_vin(args.vin)
            if not settings.access_token:
                raise SessionExpiredError("there is no saved session")
            form = request_sps_form(settings, exchange)
            submit_sporef_form(settings, form, exchange)
            catalog = sync_sps_vin(settings, args.vin, sps_info_bearer(), exchange)
            print(
                f"{catalog.controllers} controllers, {catalog.functions} functions, "
                f"{catalog.methods} methods, {catalog.supported_controllers} supported, "
                f"{catalog.calibrations} calibrations, {catalog.module_slots} modules, {catalog.rpos} rpo"
            )
            print(catalog.path)
            return 0
        bearer = ""
        if args.command in {"downloads", "modules", "download"}:
            bearer = _gateway_bearer(settings, exchange)
        if args.command == "downloads":
            found = licensed_downloads(settings, exchange, bearer)
            if args.fetch:
                failed = 0
                for module in found:
                    try:
                        path, cached = store_licensed(settings, module, exchange, bearer, refresh=args.refresh)
                    except SessionExpiredError:
                        raise
                    except ValueError as exc:
                        failed += 1
                        print(f"skipped {module.resource_id} {module.version}: {exc}", file=sys.stderr)
                        continue
                    print(f"{'cached' if cached else 'wrote'} {path}")
                return 1 if failed else 0
            for module in found:
                print(format_module(module))
            return 0
        found = list_modules(settings, args.id, exchange, bearer)
        if args.command == "modules":
            for module in found:
                print(format_module(module))
            return 0
        refresh = args.refresh
        for module in found:
            path, cached = store_licensed(settings, module, exchange, bearer, refresh=refresh)
            print(f"{'cached' if cached else 'wrote'} {path}")
        return 0
    except (ConfigError, SessionExpiredError, SpsInfoError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        first_line = str(exc).splitlines()[0]
        if args.command == "code" and first_line not in {
            "there is no email challenge waiting",
            "the sign-in challenge expired",
            "the sign-in session expired",
        }:
            print("The challenge is still saved. Run python -m spskit code again.", file=sys.stderr)
        elif args.command == "login" and str(exc) == "the sign-in host closed the connection":
            print("Run python -m spskit login again.", file=sys.stderr)
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    return run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
