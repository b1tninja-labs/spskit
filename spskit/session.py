"""The access token from the email, kept in a file outside this repository.

The verification code is a different prompt and is not written here.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from spskit.config import ConfigError, Settings
from spskit.signin import TokenError

_PROMPT = "Paste the access token from the email: "


def session_path(settings: Settings) -> Path:
    """`TDS_TOKEN_FILE` when it is set, otherwise `session.json` beside the downloads."""
    path = settings.token_file or (settings.download_dir / "session.json")
    return outside_repository(path)


def outside_repository(path: Path) -> Path:
    if not path.is_absolute():
        raise ConfigError("the session file must be an absolute path outside the repository")
    root = Path(__file__).resolve().parents[1]
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return path
    raise ConfigError("the session file must be an absolute path outside the repository")


def accept_token(token: str) -> str:
    """An access token has no spaces. A short verification code is not one."""
    if any(character.isspace() for character in token) or len(token) < 20:
        raise TokenError("paste the access token from the email; the verification code is not saved")
    return token


def prompt_emailed_token(reader: Callable[[str], str]) -> str:
    """Ask once for the access token that arrived by email. The token is not printed."""
    return accept_token(reader(_PROMPT).strip())


def write_session(path: Path, token: str) -> None:
    """Write the access token. Callers pass a path from `session_path`."""
    destination = outside_repository(path)
    kept = accept_token(token)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"access_token": kept}) + "\n", encoding="utf-8")


def read_session(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TokenError("the session file cannot be read") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise TokenError("the session file has no access token")
    return accept_token(payload["access_token"])


def apply_saved_session(settings: Settings) -> Settings:
    """Use the saved access token when the environment did not set one."""
    path = session_path(settings)
    if settings.access_token:
        return replace(settings, token_file=path)
    if not path.is_file():
        return replace(settings, token_file=path)
    return replace(settings, access_token=read_session(path), token_file=path)
