"""A session file outside this repository.

An access token the person already holds can be saved here. A verification code is not.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from spskit.config import ConfigError, Settings
from spskit.signin import TokenError
from spskit.verify import VerificationChallenge

_PROMPT = "Paste an access token: "


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
        raise TokenError("paste an access token; the verification code is not saved")
    return token


def prompt_emailed_token(reader: Callable[[str], str]) -> str:
    """Ask once for an access token the person already holds. The token is not printed."""
    return accept_token(reader(_PROMPT).strip())


def _read_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TokenError("the session file cannot be read") from exc
    if not isinstance(payload, dict):
        raise TokenError("the session file cannot be read")
    return payload


def _write_object(path: Path, payload: dict[str, object]) -> None:
    destination = outside_repository(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def write_session(path: Path, token: str) -> None:
    """Write the access token. Callers pass a path from `session_path`."""
    kept = accept_token(token)
    payload = _read_object(path)
    payload["access_token"] = kept
    _write_object(path, payload)


def write_pending(
    path: Path,
    *,
    continuation_token: str,
    verify_path: str,
    code_length: int,
    code_verifier: str,
) -> None:
    """Remember the email challenge. The verification code is not written."""
    payload = _read_object(path)
    payload["code_verifier"] = code_verifier
    payload["pending"] = {
        "continuation_token": continuation_token,
        "verify_path": verify_path,
        "code_length": code_length,
    }
    _write_object(path, payload)


def read_pending(path: Path) -> VerificationChallenge:
    pending = _read_object(path).get("pending")
    if not isinstance(pending, dict):
        raise TokenError("there is no email challenge waiting")
    token = pending.get("continuation_token")
    href = pending.get("verify_path")
    length = pending.get("code_length")
    if not isinstance(token, str) or not isinstance(href, str) or not isinstance(length, int):
        raise TokenError("there is no email challenge waiting")
    return VerificationChallenge(token, length, href)


def read_session(path: Path) -> str:
    token = _read_object(path).get("access_token")
    if not isinstance(token, str) or not token:
        raise TokenError("the session file has no access token")
    return accept_token(token)


def apply_saved_session(settings: Settings) -> Settings:
    """Use the saved access token when the environment did not set one."""
    path = session_path(settings)
    if settings.access_token or not path.is_file():
        return replace(settings, token_file=path)
    token = _read_object(path).get("access_token")
    if not isinstance(token, str) or not token:
        return replace(settings, token_file=path)
    return replace(settings, access_token=accept_token(token), token_file=path)
