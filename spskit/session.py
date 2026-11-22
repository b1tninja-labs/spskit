"""A session file outside this repository.

An access token the person already holds can be saved here. A verification code is not.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
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


def access_expiring(token: str, *, within_seconds: int = 60) -> bool:
    """A JWT whose ``exp`` is within ``within_seconds`` of now, including one already past."""
    parts = token.split(".")
    if len(parts) != 3:
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (ValueError, json.JSONDecodeError):
        return False
    exp = payload.get("exp") if isinstance(payload, dict) else None
    if not isinstance(exp, int):
        return False
    return exp <= int(datetime.now(UTC).timestamp()) + within_seconds


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


def write_launcher_tokens(path: Path, access_token: str, refresh_token: str) -> None:
    """Store the Techline Connect launcher pair. The EEID access token stays as it was."""
    payload = _read_object(path)
    payload["launcher_access_token"] = accept_token(access_token)
    payload["launcher_refresh_token"] = accept_token(refresh_token)
    _write_object(path, payload)


def write_session(
    path: Path,
    token: str,
    *,
    refresh_token: str | None = None,
    backend_pending: bool = False,
) -> None:
    """Write the access token. A refresh token, when given, is stored beside it."""
    kept = accept_token(token)
    payload = _read_object(path)
    payload["access_token"] = kept
    if refresh_token is not None:
        payload["refresh_token"] = accept_token(refresh_token)
    if backend_pending:
        payload["backend_pending"] = True
    else:
        payload.pop("backend_pending", None)
    _write_object(path, payload)


def read_backend_pending(path: Path) -> str | None:
    """The access token saved before the TDS backend accepted it, when that call still needs a retry."""
    payload = _read_object(path)
    if payload.get("backend_pending") is not True:
        return None
    token = payload.get("access_token")
    if not isinstance(token, str):
        return None
    return accept_token(token)


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


@dataclass(frozen=True, slots=True)
class SavedSignIn:
    """The email challenge after BeginAuth. The verification code is not here."""

    code_length: int
    flow_token: str
    request_ctx: str
    canary: str
    hpg_request_id: str
    username: str
    code_verifier: str


@dataclass(frozen=True, slots=True)
class SavedStay:
    """The stay-signed-in form, saved before it is posted. The verification code is not here."""

    url: str
    fields: tuple[tuple[str, str], ...]
    code_verifier: str


_VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_STAY_FIELDS = {"LoginOptions", "type", "ctx", "hpgrequestid", "flowToken", "canary", "i19"}


def write_signin(
    path: Path,
    *,
    code_length: int,
    flow_token: str,
    request_ctx: str,
    canary: str,
    hpg_request_id: str,
    username: str,
    code_verifier: str,
) -> None:
    """Remember the email challenge. A new challenge drops a half-finished stay-signed-in post."""
    saved = SavedSignIn(
        code_length,
        _line(flow_token),
        _line(request_ctx),
        _line(canary),
        _line(hpg_request_id),
        _line(username),
        _verifier(code_verifier),
    )
    if not 4 <= saved.code_length <= 12:
        raise TokenError("the saved sign-in cannot be read")
    payload = _read_object(path)
    payload.pop("stay", None)
    payload["signin"] = {
        "code_length": saved.code_length,
        "flow_token": saved.flow_token,
        "request_ctx": saved.request_ctx,
        "canary": saved.canary,
        "hpg_request_id": saved.hpg_request_id,
        "username": saved.username,
        "code_verifier": saved.code_verifier,
    }
    _write_object(path, payload)


def read_signin(path: Path) -> SavedSignIn:
    raw = _read_object(path).get("signin")
    if not isinstance(raw, dict):
        raise TokenError("there is no email challenge waiting")
    length = raw.get("code_length")
    if not isinstance(length, int):
        raise TokenError("there is no email challenge waiting")
    return SavedSignIn(
        length,
        _line(raw.get("flow_token")),
        _line(raw.get("request_ctx")),
        _line(raw.get("canary")),
        _line(raw.get("hpg_request_id")),
        _line(raw.get("username")),
        _verifier(raw.get("code_verifier")),
    )


def write_stay(path: Path, url: str, fields: list[tuple[str, str]], code_verifier: str) -> None:
    """Remember the stay-signed-in form before posting it, so that post can be repeated."""
    saved = SavedStay(url, tuple(fields), _verifier(code_verifier))
    _stay_url(saved.url)
    for name, value in saved.fields:
        if name not in _STAY_FIELDS or any(char in value for char in "\r\n"):
            raise TokenError("the saved sign-in cannot be read")
    payload = _read_object(path)
    payload["stay"] = {
        "url": saved.url,
        "fields": [[name, value] for name, value in saved.fields],
        "code_verifier": saved.code_verifier,
    }
    _write_object(path, payload)


def read_stay(path: Path) -> SavedStay | None:
    raw = _read_object(path).get("stay")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise TokenError("the saved sign-in cannot be read")
    pairs = raw.get("fields")
    if not isinstance(pairs, list):
        raise TokenError("the saved sign-in cannot be read")
    fields: list[tuple[str, str]] = []
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str) or not isinstance(pair[1], str):
            raise TokenError("the saved sign-in cannot be read")
        if pair[0] not in _STAY_FIELDS:
            raise TokenError("the saved sign-in cannot be read")
        fields.append((pair[0], pair[1]))
    return SavedStay(_stay_url(raw.get("url")), tuple(fields), _verifier(raw.get("code_verifier")))


def write_cookies(path: Path, records: list[dict[str, object]]) -> None:
    """Keep the sign-in cookies beside the challenge. They stay in this file, outside the repository."""
    payload = _read_object(path)
    payload["cookies"] = records
    _write_object(path, payload)


def read_cookies(path: Path) -> list[dict[str, object]]:
    raw = _read_object(path).get("cookies")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def clear_sign_in(path: Path) -> None:
    """Drop the challenge, the stay-signed-in form, and the sign-in cookies. The access token stays."""
    payload = _read_object(path)
    payload.pop("signin", None)
    payload.pop("stay", None)
    payload.pop("cookies", None)
    _write_object(path, payload)


def _line(value: object) -> str:
    if not isinstance(value, str) or not value or any(char in value for char in "\r\n"):
        raise TokenError("the saved sign-in cannot be read")
    return value


def _verifier(value: object) -> str:
    if not isinstance(value, str) or _VERIFIER.fullmatch(value) is None:
        raise TokenError("the saved sign-in cannot be read")
    return value


def _stay_url(value: object) -> str:
    if not isinstance(value, str):
        raise TokenError("the saved sign-in cannot be read")
    parts = urllib.parse.urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or not parts.path.rstrip("/").endswith("/kmsi"):
        raise TokenError("the saved sign-in cannot be read")
    return value


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
    payload = _read_object(path)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        return replace(settings, token_file=path)
    refresh = payload.get("refresh_token")
    kept_refresh = accept_token(refresh) if isinstance(refresh, str) and refresh else ""
    return replace(settings, access_token=accept_token(token), refresh_token=kept_refresh, token_file=path)
