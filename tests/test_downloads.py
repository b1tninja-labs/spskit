from __future__ import annotations

import json

from spskit.catalog import parse_resource_access
from spskit.cli import run
from spskit.client import licensed_downloads
from spskit.config import Settings

SEARCH = {
    "userId": "person@example.com",
    "resourcePermissions": [
        {
            "resourceId": "74f7105a-dbc2-4b3b-9cf9-c69e165216e6",
            "runnable": True,
            "userId": "person@example.com",
        },
        {"resourceId": "25", "runnable": True, "securityGroupName": "acd_vinsub"},
        {"resourceId": "40", "runnable": True},
        {"resourceId": "41", "runnable": False},
    ],
}


def _version(raw_id: str, name: str) -> dict[str, object]:
    return {
        "message": "found",
        "cdlPermission": {"userId": "person@example.com", "resourceId": raw_id},
        "resourceVersions": [
            {
                "cdlResourceId": raw_id,
                "cdlResourceName": name,
                "cdlResourceDescription": "A licensed file",
                "cdlResourceTypeCode": "INITIAL_SOFTWARE",
                "versionNumber": "26.8.31.0",
            }
        ],
    }


def test_resource_access_drops_the_account_id():
    found = parse_resource_access(SEARCH)
    assert [(item.resource_id, item.runnable) for item in found] == [
        ("74f7105a-dbc2-4b3b-9cf9-c69e165216e6", True),
        ("25", True),
        ("40", True),
        ("41", False),
    ]
    assert "person@example.com" not in repr(found)


def test_the_installer_and_a_decimal_resource_are_listed(tmp_path):
    asked: list[str] = []

    def exchange(method, url, body, headers):
        asked.append(url)
        assert headers["authorization"] == "Bearer token-1"
        if method == "POST":
            assert url.endswith("/acl/permissions/search")
            assert body == b"{}"
            return 200, json.dumps(SEARCH).encode()
        assert method == "GET"
        raw_id = url.rstrip("/").split("/")[-2]
        name = "TLC Installer" if raw_id == "25" else "Other module"
        return 200, json.dumps(_version(raw_id, name)).encode()

    settings = Settings(
        "person",
        "secret",
        "https://gateway.example",
        "https://ciam.example",
        "token-1",
        tmp_path,
    )
    found = licensed_downloads(settings, exchange)
    assert [module.resource_id for module in found] == ["25", "40"]
    assert found[0].name == "TLC Installer"
    assert not any("74f7105a" in url for url in asked)
    assert "person@example.com" not in repr(found)


def test_downloads_lists_and_get_writes_the_file(tmp_path, capsys):
    env = tmp_path / ".env"
    out = tmp_path / "out"
    env.write_text("SPS_DOWNLOAD_DIR=" + str(out) + "\nTDS_ACCESS_TOKEN=token-1\n", encoding="utf-8")

    def exchange(method, url, body, headers):
        assert "person@example.com" not in json.dumps(dict(headers))
        if url.endswith("/acl/permissions/search"):
            assert body == b"{}"
            return 200, json.dumps(SEARCH).encode()
        if url.endswith("/permissions"):
            raw_id = url.rstrip("/").split("/")[-2]
            name = "TLC Installer" if raw_id == "25" else "Other module"
            return 200, json.dumps(_version(raw_id, name)).encode()
        if method == "POST":
            return 200, json.dumps(
                {
                    "downloadCredentials": [
                        {
                            "url": "https://cdn.example/TLCSuite.exe",
                            "filename": "TLCSuite.exe",
                            "headers": {},
                        }
                    ]
                }
            ).encode()
        assert url == "https://cdn.example/TLCSuite.exe"
        return 200, b"installer-bytes"

    code = run(["--env", str(env), "downloads"], exchange)
    assert code == 0
    listed = capsys.readouterr().out
    assert "TLC Installer" in listed
    assert "Other module" in listed
    assert "person@example.com" not in listed
    code = run(["--env", str(env), "downloads", "--get"], exchange)
    assert code == 0
    assert (out / "TLCSuite.exe").read_bytes() == b"installer-bytes"
    assert "token-1" not in capsys.readouterr().out
