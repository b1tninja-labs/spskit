from __future__ import annotations

import json
import pathlib
import urllib.request
from http.client import HTTPMessage

import pytest

from spskit.catalog import LicensedModule
from spskit.cli import _CodeRedirect
from spskit.client import fetch_module, request_grant
from spskit.config import Settings
from spskit.download import DownloadError, credentials_body, parse_grant, refuse_storage_redirect, save_bytes

MODULE = LicensedModule("25", "Example module", "A licensed programming module", "SOFTWARE", "1.2.3")


def test_the_request_starts_with_empty_token_fields():
    body = credentials_body(MODULE)
    item = body["downloadCredentials"][0]
    assert item["humanReadableName"] == "Example module"
    assert item["url"] == ""
    assert item["tokenType"] == "TUM"
    assert item["tokenData"] == {"value": "", "expirationTime": -1}
    assert "password" not in item


def test_a_grant_must_be_https_and_a_plain_filename():
    grant = parse_grant(
        {
            "downloadCredentials": [
                {
                    "url": "https://cdn.example/modules/example.bin",
                    "filename": "example.bin",
                    "headers": {"Cookie": "download=1"},
                }
            ]
        }
    )
    assert grant.filename == "example.bin"
    assert grant.headers == {"Cookie": "download=1"}
    with pytest.raises(DownloadError):
        parse_grant({"downloadCredentials": [{"url": "http://cdn.example/a.bin", "filename": "a.bin", "headers": {}}]})
    with pytest.raises(DownloadError):
        parse_grant(
            {"downloadCredentials": [{"url": "https://cdn.example/a.bin", "filename": "../a.bin", "headers": {}}]}
        )


def test_a_netstorage_redirect_is_not_followed():
    handler = _CodeRedirect()
    request = urllib.request.Request("https://tlc-cdn.gm.com/cache-downloads/public/Prod/TUM2/26.8.28.0.zip")
    with pytest.raises(DownloadError, match="no public address"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            HTTPMessage(),
            "https://r36048-f-40560.c.1.dsdl.b.stor.lb.akamai.net/file.zip",
        )
    followed = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        HTTPMessage(),
        "https://cdn.example/file.zip",
    )
    assert followed is not None
    assert followed.full_url == "https://cdn.example/file.zip"
    refuse_storage_redirect("https://cdn.example/file.zip")


def test_download_writes_beside_the_given_directory(tmp_path: pathlib.Path):
    settings = Settings("person", "secret", "https://gateway.example", "https://ciam.example", "", tmp_path)
    grant_body = {
        "downloadCredentials": [
            {
                "url": "https://cdn.example/modules/example.bin",
                "filename": "example.bin",
                "headers": {"Cookie": "download=1"},
            }
        ]
    }

    def exchange(method, url, body, headers):
        if method == "POST":
            assert url.endswith("/cdn/files/public/downloadCredentials")
            posted = json.loads(body)
            assert posted["downloadCredentials"][0]["versionNumber"] == "1.2.3"
            assert b"secret" not in body
            return 200, json.dumps(grant_body).encode()
        assert headers["Cookie"] == "download=1"
        assert headers["User-Agent"] == "Java/11.0.19"
        return 200, b"module-bytes"

    grant = request_grant(settings, MODULE, exchange)
    written = fetch_module(settings, MODULE, grant, exchange)
    assert written == tmp_path / "cache" / "25" / "1.2.3" / "example.bin"
    assert written.read_bytes() == b"module-bytes"
    with pytest.raises(DownloadError):
        save_bytes(tmp_path, "..\\escape.bin", b"no")
