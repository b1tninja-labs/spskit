"""Ask the gateway for a download grant and write the file outside the repository."""

from __future__ import annotations

import pathlib
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass

from spskit.catalog import LicensedModule

CREDENTIALS_PATH = "/cdn/files/public/downloadCredentials"


class DownloadError(ValueError):
    """A grant or a filename cannot be used."""


@dataclass(frozen=True)
class DownloadGrant:
    url: str
    filename: str
    headers: dict[str, str]


def credentials_body(module: LicensedModule) -> dict[str, object]:
    """The request the gateway fills in. Token fields start empty; the response supplies the file address."""
    return {
        "downloadCredentials": [
            {
                "humanReadableName": module.name,
                "versionNumber": module.version,
                "cdlResourceType": module.type_code,
                "tokenType": "",
                "url": "",
                "tokenData": "",
                "headers": {},
                "md5": "",
                "filename": "",
            }
        ]
    }


def safe_filename(name: str) -> str:
    if not name or name in {".", ".."} or "/" in name or "\\" in name or name.startswith("."):
        raise DownloadError("filename is not a single plain name")
    return name


def parse_grant(payload: Mapping[str, object]) -> DownloadGrant:
    items = payload.get("downloadCredentials")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], Mapping):
        raise DownloadError("downloadCredentials must be one object")
    item = items[0]
    url = item.get("url")
    if not isinstance(url, str):
        raise DownloadError("download url is missing")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise DownloadError("download url must be https and carry no userinfo")
    raw_name = item.get("filename")
    if not isinstance(raw_name, str) or not raw_name:
        raw_name = pathlib.PurePosixPath(parts.path).name
    headers = item.get("headers") or {}
    if not isinstance(headers, Mapping):
        raise DownloadError("headers must be an object")
    clean: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise DownloadError("a header is not text")
        if key.lower() in {"authorization", "cookie"} or key.lower().startswith("x-"):
            clean[key] = value
        else:
            raise DownloadError(f"refusing to replay header {key}")
    return DownloadGrant(url, safe_filename(raw_name), clean)


def save_bytes(directory: pathlib.Path, filename: str, data: bytes) -> pathlib.Path:
    """Write one module. The filename is checked again so a grant cannot escape the directory."""
    name = safe_filename(filename)
    directory.mkdir(parents=True, exist_ok=True)
    target = (directory / name).resolve()
    if target.parent != directory.resolve():
        raise DownloadError("filename escapes the download directory")
    target.write_bytes(data)
    return target
