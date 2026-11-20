from __future__ import annotations

import json
from pathlib import Path

import pytest

from spskit.config import ConfigError, Settings
from spskit.session import apply_saved_session, outside_repository, prompt_emailed_token, write_session
from spskit.signin import TokenError


def test_the_email_prompt_keeps_an_access_token_and_refuses_the_short_code(tmp_path: Path):
    seen: list[str] = []

    def reader(prompt: str) -> str:
        seen.append(prompt)
        return "access-token-from-email"

    assert prompt_emailed_token(reader) == "access-token-from-email"
    assert "access token" in seen[0]
    with pytest.raises(TokenError, match="verification code"):
        prompt_emailed_token(lambda _prompt: "abcd1234")
    assert not (tmp_path / "session.json").exists()


def test_the_session_file_is_reloaded_and_a_path_in_the_repository_is_refused(tmp_path: Path):
    settings = Settings("person", "secret", "https://gateway.example", "https://ciam.example", "", tmp_path)
    write_session(
        tmp_path / "session.json",
        "access-token-from-email",
        refresh_token="refresh-token-value-0001",
    )
    loaded = apply_saved_session(settings)
    assert loaded.access_token == "access-token-from-email"
    assert loaded.refresh_token == "refresh-token-value-0001"
    assert "refresh-token-value-0001" not in repr(loaded)
    assert json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))["access_token"] == loaded.access_token
    with pytest.raises(ConfigError, match="outside the repository"):
        outside_repository(Path(__file__).resolve().parents[1] / "session.json")
