from __future__ import annotations

import pathlib

import pytest

from spskit.config import ConfigError, load_settings, parse_env_text, settings_from

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / ".env.example"


def test_the_example_names_the_secrets_and_leaves_them_empty():
    values = parse_env_text(EXAMPLE.read_text(encoding="utf-8"))
    assert values["TDS_USERNAME"] == ""
    assert values["TDS_PASSWORD"] == ""
    assert values["TDS_NEW_PASSWORD"] == ""
    assert values["TDS_ACCESS_TOKEN"] == ""
    assert values["TDS_CODE_VERIFIER"] == ""
    assert values["TDS_TOKEN_FILE"] == ""
    assert values["TDS_GATEWAY"].startswith("https://")
    assert values["SPS_DOWNLOAD_DIR"]
    assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_process_environment_overrides_the_file(tmp_path: pathlib.Path):
    env_file = tmp_path / ".env"
    anchor = pathlib.Path(tmp_path.anchor)
    env_file.write_text(
        f"TDS_USERNAME=from-file\nTDS_PASSWORD=file-secret\nSPS_DOWNLOAD_DIR={anchor / 'data' / 'spskit'}\n",
        encoding="utf-8",
    )
    override = anchor / "data" / "other"
    settings = load_settings(env_file, {"TDS_USERNAME": "from-shell", "SPS_DOWNLOAD_DIR": str(override)})
    assert settings.username == "from-shell"
    assert settings.password == "file-secret"
    assert settings.download_dir == override


def test_a_relative_download_directory_is_refused():
    with pytest.raises(ConfigError, match="absolute"):
        settings_from({"SPS_DOWNLOAD_DIR": "downloads"})


def test_comments_and_quotes_parse():
    values = parse_env_text("# note\nTDS_USERNAME=\"person\"\n\nexport TDS_PASSWORD='secret'\n")
    assert values == {"TDS_USERNAME": "person", "TDS_PASSWORD": "secret"}
