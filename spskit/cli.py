"""Command line. Network access lives here; the library functions take an exchange."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence

from spskit.catalog import LicensedModule
from spskit.client import Exchange, fetch_module, list_modules, request_grant, submit_code
from spskit.config import ConfigError, load_settings
from spskit.verify import SessionExpiredError, parse_challenge


def urllib_exchange(method: str, url: str, body: bytes | None, headers: Mapping[str, str]) -> tuple[int, bytes]:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise SessionExpiredError("refusing a URL that is not https")
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return response.status, response.read()
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
    sub.add_parser("verify", help="read a verification challenge on stdin and prompt for the code")
    args = parser.parse_args(list(argv))
    try:
        settings = load_settings(pathlib.Path(args.env))
        if args.command == "verify":
            raw = sys.stdin.read() if stdin_text is None else stdin_text
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise SessionExpiredError("the challenge is not an object")
            result = submit_code(settings, parse_challenge(payload), reader, exchange)
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
