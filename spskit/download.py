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
                "tokenType": "TUM",
                "url": "",
                "tokenData": {"value": "", "expirationTime": -1},
                "headers": {},
                "md5": "",
                "filename": "",
            }
        ]
    }


def refuse_storage_redirect(url: str) -> None:
    """Stop before a cached NetStorage redirect. The edge is supposed to chase that name itself."""
    host = urllib.parse.urlsplit(url).hostname
    if host is None:
        return
    lowered = host.lower().rstrip(".")
    if lowered == "stor.lb.akamai.net" or lowered.endswith(".stor.lb.akamai.net"):
        raise DownloadError(f"the CDN cached a redirect to {lowered}, and that host has no public address")


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


def version_segment(value: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or any(
            character not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz._-" for character in value
        )
    ):
        raise DownloadError("version is not a plain segment")
    return value


def cache_folder(directory: pathlib.Path, module: LicensedModule) -> pathlib.Path:
    """One directory per resource version, under the download directory."""
    root = (directory / "cache").resolve()
    folder = (root / version_segment(module.resource_id) / version_segment(module.version)).resolve()
    if root not in folder.parents:
        raise DownloadError("version escapes the cache")
    return folder


def cached_file(directory: pathlib.Path, module: LicensedModule) -> pathlib.Path | None:
    """The file already stored for this version, when there is exactly one."""
    folder = cache_folder(directory, module)
    if not folder.is_dir():
        return None
    found = [
        path
        for path in folder.iterdir()
        if path.is_file() and path.stat().st_size > 0 and not path.name.startswith(".")
    ]
    if len(found) != 1:
        return None
    return found[0]


def save_cached(directory: pathlib.Path, module: LicensedModule, filename: str, data: bytes) -> pathlib.Path:
    folder = cache_folder(directory, module)
    name = safe_filename(filename)
    folder.mkdir(parents=True, exist_ok=True)
    target = (folder / name).resolve()
    if target.parent != folder:
        raise DownloadError("filename escapes the cache")
    target.write_bytes(data)
    return target


def save_bytes(directory: pathlib.Path, filename: str, data: bytes) -> pathlib.Path:
    """Write one module. The filename is checked again so a grant cannot escape the directory."""
    name = safe_filename(filename)
    directory.mkdir(parents=True, exist_ok=True)
    target = (directory / name).resolve()
    if target.parent != directory.resolve():
        raise DownloadError("filename escapes the download directory")
    target.write_bytes(data)
    return target
