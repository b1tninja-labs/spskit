from __future__ import annotations

import json

from spskit.catalog import parse_permissions, parse_prelaunch, parse_resource_access
from spskit.cli import run
from spskit.client import licensed_downloads, list_modules, open_gateway_session
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


def test_a_disabled_version_is_left_out():
    payload = _version("25", "TLC Installer")
    versions = payload["resourceVersions"]
    assert isinstance(versions, list)
    versions.append(
        {
            "cdlResourceId": "25",
            "cdlResourceName": "Old installer",
            "cdlResourceDescription": "Turned off",
            "cdlResourceTypeCode": "INITIAL_SOFTWARE",
            "versionNumber": "1.0.0",
            "disabled": True,
        }
    )
    found = parse_permissions(payload)
    assert [module.version for module in found] == ["26.8.31.0"]
    assert parse_prelaunch(PRELAUNCH) == ["7"]


def test_resource_access_drops_the_account_id():
    found = parse_resource_access(SEARCH)
    assert [(item.resource_id, item.runnable) for item in found] == [
        ("74f7105a-dbc2-4b3b-9cf9-c69e165216e6", True),
        ("25", True),
        ("40", True),
        ("41", False),
    ]
    assert "person@example.com" not in repr(found)


PRELAUNCH = {
    "cdlResources": [
        {"id": "7", "name": "Prelaunch pack", "disabled": False},
        {"id": "8", "name": "Turned off", "disabled": True},
        {"id": "74f7105a-dbc2-4b3b-9cf9-c69e165216e6", "name": "A page"},
    ]
}


def test_the_installer_and_a_decimal_resource_are_listed(tmp_path):
    asked: list[str] = []

    def exchange(method, url, body, headers):
        asked.append(url)
        assert "authorization" not in {name.lower() for name in headers}
        assert "token-1" not in json.dumps(dict(headers))
        if method == "POST":
            assert url.endswith("/acl/permissions/search")
            assert body == b"{}"
            return 200, json.dumps(SEARCH).encode()
        assert method == "GET"
        if url.endswith("/acl/cdl/resources/prelaunch"):
            return 200, json.dumps(PRELAUNCH).encode()
        if url.endswith("/acl/cdl/permissions/search"):
            return 200, json.dumps(_version("9", "Search hit")).encode()
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
    assert [module.resource_id for module in found] == ["25", "40", "7", "1", "9"]
    assert found[0].name == "TLC Installer"
    assert not any("74f7105a" in url for url in asked)
    assert "person@example.com" not in repr(found)


def test_downloads_lists_and_get_writes_the_file(tmp_path, capsys):
    env = tmp_path / ".env"
    out = tmp_path / "out"
    env.write_text(
        "SPS_DOWNLOAD_DIR="
        + str(out)
        + "\nTDS_ACCESS_TOKEN=token-1\nTDS_GATEWAY=https://gateway.example\nTDS_BACKEND=https://backend.example\n",
        encoding="utf-8",
    )

    fetches: list[str] = []

    def exchange(method, url, body, headers):
        lowered = {name.lower(): value for name, value in headers.items()}
        assert "person@example.com" not in json.dumps(lowered)
        if url.endswith("/api/tds-backend"):
            return 200, b"header.payload.signature"
        if url.endswith("/spsCallibration/accessSPSCal"):
            assert lowered["x-eeid-access-token"] == "token-1"
            assert lowered["authorization"] == "Bearer header.payload.signature"
            return 200, (
                b'<form method="POST" action="https://gateway.example/authorization/oauth/user/sporef/ui">'
                b'<input name="appParm" value="sps2info"></form>'
            )
        if url.endswith("/sporef/ui"):
            assert "authorization" not in lowered
            assert "x-eeid-access-token" not in lowered
            assert "token-1" not in json.dumps(lowered)
            return 200, b"<html></html>"
        if "gateway.example" in url:
            assert "authorization" not in lowered
            assert "x-eeid-access-token" not in lowered
        if url.endswith("/acl/permissions/search"):
            assert body == b"{}"
            return 200, json.dumps(SEARCH).encode()
        if url.endswith("/acl/cdl/resources/prelaunch"):
            return 200, json.dumps(PRELAUNCH).encode()
        if url.endswith("/acl/cdl/permissions/search"):
            return 200, json.dumps({"resourceVersions": []}).encode()
        if url.endswith("/permissions"):
            raw_id = url.rstrip("/").split("/")[-2]
            names = {"25": "TLC Installer", "7": "Prelaunch pack", "1": "TUM", "40": "Other module"}
            return 200, json.dumps(_version(raw_id, names.get(raw_id, "Other module"))).encode()
        if method == "POST":
            posted = json.loads(body)
            filename = posted["downloadCredentials"][0]["humanReadableName"].replace(" ", "-")
            return 200, json.dumps(
                {
                    "downloadCredentials": [
                        {
                            "url": "https://cdn.example/file.bin",
                            "filename": filename,
                            "headers": {},
                        }
                    ]
                }
            ).encode()
        fetches.append(url)
        return 200, b"installer-bytes"

    code = run(["--env", str(env), "downloads"], exchange)
    assert code == 0
    listed = capsys.readouterr().out
    assert "TLC Installer" in listed
    assert "Other module" in listed
    assert "Prelaunch pack" in listed
    assert "person@example.com" not in listed
    code = run(["--env", str(env), "downloads", "--get"], exchange)
    assert code == 0
    cached = out / "cache" / "25" / "26.8.31.0" / "TLC-Installer"
    assert cached.read_bytes() == b"installer-bytes"
    assert (out / "cache" / "7" / "26.8.31.0" / "Prelaunch-pack").is_file()
    assert (out / "cache" / "1" / "26.8.31.0" / "TUM").is_file()
    first_fetches = len(fetches)
    code = run(["--env", str(env), "downloads", "--get"], exchange)
    assert code == 0
    assert len(fetches) == first_fetches
    assert "cached" in capsys.readouterr().out
    assert "token-1" not in capsys.readouterr().out


def test_the_handoff_leaves_the_eeid_token_off_the_gateway(tmp_path):
    token = "saved-access-token"
    calls: list[str] = []

    def exchange(method, url, body, headers):
        calls.append(url)
        lowered = {name.lower(): value for name, value in headers.items()}
        if url.endswith("/api/tds-backend"):
            assert method == "GET"
            return 200, b"header.payload.signature"
        if url.endswith("/spsCallibration/accessSPSCal"):
            assert method == "GET"
            assert lowered["x-eeid-access-token"] == token
            assert lowered["authorization"].startswith("Bearer ")
            return 200, (
                b'<form method="POST" action="https://gateway.example/authorization/oauth/user/sporef/ui">'
                b'<input name="appParm" value="sps2info"></form>'
            )
        if url.endswith("/sporef/ui"):
            assert method == "POST"
            assert "authorization" not in lowered
            assert "x-eeid-access-token" not in lowered
            assert token.encode() not in (body or b"")
            return 200, b"<html></html>"
        assert method == "GET"
        assert url.endswith("/acl/cdl/resources/25/permissions")
        assert "authorization" not in lowered
        assert "x-eeid-access-token" not in lowered
        assert token not in json.dumps(lowered)
        return 200, json.dumps(_version("25", "TLC Installer")).encode()

    settings = Settings(
        "person",
        "secret",
        "https://gateway.example",
        "https://ciam.example",
        token,
        tmp_path,
        backend="https://backend.example",
    )
    open_gateway_session(settings, exchange)
    found = list_modules(settings, "25", exchange)
    assert found[0].name == "TLC Installer"
    assert [url.rsplit("/", 1)[-1] for url in calls] == [
        "tds-backend",
        "accessSPSCal",
        "ui",
        "permissions",
    ]
