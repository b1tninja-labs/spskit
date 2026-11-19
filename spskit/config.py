"""Settings from the environment and a local .env file. No third-party env loader."""

from __future__ import annotations

import os
import pathlib
import re
from collections.abc import Mapping
from dataclasses import dataclass

from spskit.signin import PUBLIC_CLIENT_ID, REDIRECT_URI, TENANT_ID

_KEY = re.compile(r"[A-Z][A-Z0-9_]*")
_ASSIGN = re.compile(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$")


class ConfigError(ValueError):
    """A setting is missing or not usable."""


@dataclass(frozen=True)
class Settings:
    """What a run needs. TDS_NEW_PASSWORD is the reset value; TDS_PASSWORD is the current one."""

    username: str
    password: str
    gateway: str
    ciam: str
    access_token: str
    download_dir: pathlib.Path
    client_id: str = PUBLIC_CLIENT_ID
    tenant: str = TENANT_ID
    redirect_uri: str = REDIRECT_URI
    backend: str = "https://backend.acdelcotds.com"
    zone: str = "America/Los_Angeles"
    code_verifier: str = ""
    token_file: pathlib.Path | None = None
    new_password: str = ""


def parse_env_text(text: str) -> dict[str, str]:
    """Read KEY=VALUE lines. Blank lines and `#` comments are skipped. Values are not expanded."""
    found: dict[str, str] = {}
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _ASSIGN.match(line)
        if match is None:
            raise ConfigError(f"line {line_number} is not KEY=VALUE")
        key, value = match.group(1), match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if not _KEY.fullmatch(key):
            raise ConfigError(f"line {line_number} has a bad key")
        found[key] = value
    return found


def load_env_file(path: pathlib.Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return parse_env_text(path.read_text(encoding="utf-8"))


def settings_from(env: Mapping[str, str]) -> Settings:
    """Build settings. Process environment should already have overridden the file."""
    gateway = env.get("TDS_GATEWAY", "https://tlc-dmz-gateway.ext.gm.com").rstrip("/")
    ciam = env.get("TDS_CIAM", "https://gmb2bciamprod.ciamlogin.com").rstrip("/")
    backend = env.get("TDS_BACKEND", "https://backend.acdelcotds.com").rstrip("/")
    redirect_uri = env.get("TDS_REDIRECT_URI", REDIRECT_URI).rstrip("/")
    for name, value in (
        ("TDS_GATEWAY", gateway),
        ("TDS_CIAM", ciam),
        ("TDS_BACKEND", backend),
        ("TDS_REDIRECT_URI", redirect_uri),
    ):
        if not value.startswith("https://") or " " in value:
            raise ConfigError(f"{name} must be an https URL")
    raw_dir = env.get("SPS_DOWNLOAD_DIR", "").strip()
    if not raw_dir:
        raise ConfigError("SPS_DOWNLOAD_DIR is required")
    download_dir = pathlib.Path(raw_dir)
    if not download_dir.is_absolute():
        raise ConfigError("SPS_DOWNLOAD_DIR must be an absolute path outside the repository")
    raw_token_file = env.get("TDS_TOKEN_FILE", "").strip()
    token_file = pathlib.Path(raw_token_file) if raw_token_file else None
    if token_file is not None and not token_file.is_absolute():
        raise ConfigError("TDS_TOKEN_FILE must be an absolute path outside the repository")
    return Settings(
        username=env.get("TDS_USERNAME", ""),
        password=env.get("TDS_PASSWORD", ""),
        gateway=gateway,
        ciam=ciam,
        access_token=env.get("TDS_ACCESS_TOKEN", "").strip(),
        download_dir=download_dir,
        client_id=env.get("TDS_CLIENT_ID", PUBLIC_CLIENT_ID).strip() or PUBLIC_CLIENT_ID,
        tenant=env.get("TDS_TENANT", TENANT_ID).strip() or TENANT_ID,
        redirect_uri=redirect_uri,
        backend=backend,
        zone=env.get("TDS_ZONE", "America/Los_Angeles").strip() or "America/Los_Angeles",
        code_verifier=env.get("TDS_CODE_VERIFIER", "").strip(),
        token_file=token_file,
        new_password=env.get("TDS_NEW_PASSWORD", ""),
    )


def merged_env(file_values: Mapping[str, str], process: Mapping[str, str]) -> dict[str, str]:
    """The process environment wins, so a shell secret is not replaced by the file."""
    merged = dict(file_values)
    for key, value in process.items():
        if _KEY.fullmatch(key):
            merged[key] = value
    return merged


def load_settings(env_path: pathlib.Path, process: Mapping[str, str] | None = None) -> Settings:
    process_env = os.environ if process is None else process
    return settings_from(merged_env(load_env_file(env_path), process_env))
