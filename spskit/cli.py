"""Command line. Network access lives here; the library functions take an exchange."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from http.client import HTTPMessage
from typing import IO

from spskit.catalog import LicensedModule
from spskit.client import (
    Exchange,
    exchange_authorization_code,
    fetch_module,
    list_modules,
    open_backend_session,
    request_grant,
    submit_code,
)
from spskit.config import ConfigError, load_settings
from spskit.login_start import prompt_email_code, redirect_location, request_email_code, submit_email_code
from spskit.session import (
    apply_saved_session,
    prompt_emailed_token,
    read_pending,
    session_path,
    write_session,
)
from spskit.verify import SessionExpiredError, parse_challenge


class _AuthorizationRedirectError(Exception):
    """The stay-signed-in response pointed at the TDS redirect. The code stays on the location."""

    def __init__(self, location: str) -> None:
        super().__init__("authorization redirect")
        self.location = location


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
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_JAR),
    _CodeRedirect(),
)
_COOKIE_NAME = re.compile(r"^[A-Za-z0-9_]{1,40}$")


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


def urllib_exchange(method: str, url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, bytes]:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise SessionExpiredError("refusing a URL that is not https")
    outgoing = dict(headers)
    extra_cookie = outgoing.pop("cookie", None)
    if extra_cookie:
        _store_cookie(url, extra_cookie)
    request = urllib.request.Request(url, data=body, headers=outgoing, method=method)  # noqa: S310
    try:
        with _OPENER.open(request, timeout=60) as response:
            return response.status, response.read()
    except _AuthorizationRedirectError as exc:
        return 302, exc.location.encode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def format_module(module: LicensedModule) -> str:
    return f"{module.resource_id}\t{module.version}\t{module.type_code}\t{module.name}"


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
    sub.add_parser("login", help="sign in with the password, then prompt for the emailed code")
    sub.add_parser("verify", help="prompt for the emailed code, or read a challenge on stdin")
    sub.add_parser("session", help="save an access token the person already holds")
    token = sub.add_parser("token", help="exchange the TDS redirect for an access token")
    token.add_argument("--redirect", required=True, help="the https://www.acdelcotds.com/#code=... URL")
    args = parser.parse_args(list(argv))
    try:
        settings = load_settings(pathlib.Path(args.env))
        if args.command == "login":
            requested = request_email_code(settings, exchange)
            print(f"Email challenge sent ({requested.challenge.code_length} characters).")
            code = prompt_email_code(requested.challenge.code_length, reader)
            redirect = submit_email_code(settings, requested, code, exchange)
            del code
            settings = replace(settings, code_verifier=requested.code_verifier)
            access = exchange_authorization_code(settings, redirect, exchange)
            open_backend_session(settings, access, exchange)
            path = session_path(settings)
            write_session(path, access)
            print(f"wrote the session to {path}")
            return 0
        if args.command == "session":
            emailed = prompt_emailed_token(reader)
            path = session_path(settings)
            write_session(path, emailed)
            print(f"wrote the session to {path}")
            return 0
        settings = apply_saved_session(settings)
        if args.command == "token":
            access = exchange_authorization_code(settings, args.redirect, exchange)
            open_backend_session(settings, access, exchange)
            path = session_path(settings)
            write_session(path, access)
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
        found = list_modules(settings, args.id, exchange)
        if args.command == "modules":
            for module in found:
                print(format_module(module))
            return 0
        for module in found:
            grant = request_grant(settings, module, exchange)
            fetch_module(settings, grant, exchange)
            print(f"wrote {settings.download_dir / grant.filename}")
        return 0
    except (ConfigError, SessionExpiredError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    return run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
