from __future__ import annotations

import json

from spskit.catalog import parse_permissions
from spskit.client import acl_headers, list_modules
from spskit.config import Settings

PERMISSIONS = {
    "message": "found",
    "cdlPermission": {"userId": "person@example.com", "resourceId": "25"},
    "resourceVersions": [
        {
            "cdlResourceId": "25",
            "cdlResourceName": "Example module",
            "cdlResourceDescription": "A licensed programming module",
            "cdlResourceTypeCode": "SOFTWARE",
            "versionNumber": "1.2.3",
        }
    ],
}


def _settings(tmp_path, token: str = "") -> Settings:
    return Settings("person", "secret", "https://gateway.example", "https://ciam.example", token, tmp_path)


def test_permissions_drop_the_account_id():
    modules = parse_permissions(PERMISSIONS)
    assert len(modules) == 1
    assert modules[0].name == "Example module"
    assert modules[0].version == "1.2.3"
    assert "person@example.com" not in repr(modules[0])


def test_listing_does_not_send_the_saved_access_token(tmp_path):
    captured: list[dict[str, str]] = []

    def exchange(method, url, body, headers):
        captured.append(dict(headers))
        assert method == "GET"
        assert body is None
        assert url.endswith("/acl/cdl/resources/25/permissions")
        return 200, json.dumps(PERMISSIONS).encode()

    found = list_modules(_settings(tmp_path), "25", exchange)
    assert found[0].type_code == "SOFTWARE"
    assert "authorization" not in {name.lower() for name in captured[0]}
    captured.clear()
    list_modules(_settings(tmp_path, token="token-1"), "25", exchange)
    sent = {name.lower(): value for name, value in captured[0].items()}
    assert "authorization" not in sent
    assert "token-1" not in json.dumps(sent)
    captured.clear()
    list_modules(_settings(tmp_path, token="token-1"), "25", exchange, "gateway-session")
    sent = {name.lower(): value for name, value in captured[0].items()}
    assert sent["authorization"] == "Bearer gateway-session"
    assert "x-eeid-access-token" not in sent
    assert "token-1" not in json.dumps(sent)
    assert acl_headers() == {"accept": "application/json"}
    assert acl_headers("gateway-session")["authorization"] == "Bearer gateway-session"
