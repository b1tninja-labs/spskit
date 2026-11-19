from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from spskit.cli import run
from spskit.client import sync_sps_vin
from spskit.config import Settings
from spskit.spsinfo import SpsInfoError, check_vin, parse_sporef_form, save_vin

VIN = "1G1TE5TVN00000001"
OTHER = "1G1TE5TVN00000002"
BEARER = "sps-bearer-value-0001"
ACCESS = "saved-access-token-0001"
TICKET = "sample-ticket"

FIXTURE = {
    "controllerReferenceTree": {
        "referenceTree": [
            [
                {"controllerCode": "K17", "controllerLabel": "Brake", "displayOrder": 0, "note": "keep"},
                [
                    [
                        {"displayOrder": 1, "functionLabel": "Programming"},
                        [
                            [
                                {"methodId": 128, "description": "Normal", "blockSameCal": True},
                                {
                                    "type": "ProductionOptionComposite",
                                    "currentSelectionIdx": 0,
                                    "selectedCodes": ["A"],
                                    "options": [{"label": "OnStar"}],
                                },
                            ]
                        ],
                    ]
                ],
            ]
        ],
        "treeNote": "kept",
    },
    "spsvin": {
        "type": "NAOVin",
        "vin": VIN,
        "sLineSeries": "RD",
        "engineeringModelYear": 2017,
        "truck": False,
        "vciNumbers": {"10": 1},
        "copControllers": {"C67": [10]},
        "deviceList": [{"id": 1}],
        "supportedControllers": [
            {
                "controllerId": 54,
                "displayName": {"controllerCode": "K73", "controllerLabel": "Telematics", "displayOrder": 0},
                "extra": "kept",
            }
        ],
        "asbuiltRpoCodes": ["AG6", "AYF"],
        "unknownMap": {"keep": True},
        "warrantyClaimCode": {"deviceID": "00"},
        "wmiByPass": [],
        "jobCard": "",
    },
    "rpoCodes": ["EXTRA"],
    "displayName": {"controllerCode": "controllercode", "controllerLabel": "controllerlabel", "displayOrder": 0},
}

SEQUENCE = {
    "calibrationData": {"11": [["84045917", "0", "Locking"], ["84176905", "1", "Updated"]]},
    "moduleData": [["11", "Lock Module"]],
    "cvnMap": {"84045917": "ABCD", "84176905": "EF01"},
    "hasValidChainOfParts": True,
    "adapterType": "NAOVin",
    "hasDependency": False,
    "futureField": {"n": 1},
}

FORM = """<!DOCTYPE html><html><head><title>SPOREF Redirection</title></head><body>
<form method="POST" action="https://gateway.example/authorization/oauth/user/sporef/ui">
<input type="hidden" name="appParm" value="sps2info">
<input type="hidden" name="ticket" value="sample-ticket">
</form></body></html>
"""


def _settings(directory: Path) -> Settings:
    return Settings(
        username="",
        password="",
        gateway="https://gateway.example",
        ciam="https://ciam.example",
        access_token=ACCESS,
        download_dir=directory,
        backend="https://backend.example",
    )


def _copy(document: dict[str, object]) -> dict[str, object]:
    copied = json.loads(json.dumps(document))
    if not isinstance(copied, dict):
        raise AssertionError("copy")
    return copied


def test_a_vin_must_be_seventeen_characters_without_i_o_or_q():
    assert check_vin(VIN) == VIN
    for rejected in ("1G1TE5TVN0000000I", "1G1TE5TVN0000000O", "1G1TE5TVN0000000Q", "SHORT", VIN.lower()):
        with pytest.raises(SpsInfoError, match="17 characters"):
            check_vin(rejected)


def test_the_sporef_form_keeps_the_action_and_the_fields():
    form = parse_sporef_form(FORM)
    assert form.action == "https://gateway.example/authorization/oauth/user/sporef/ui"
    assert form.fields == (("appParm", "sps2info"), ("ticket", TICKET))
    assert TICKET not in repr(form)
    with pytest.raises(SpsInfoError, match="did not return a form"):
        parse_sporef_form("<html><title>SPOREF Redirection</title></html>")


def test_the_catalog_is_replaced_when_the_same_vin_is_synced_again(tmp_path: Path):
    database = tmp_path / "spsinfo.sqlite"
    first = save_vin(database, VIN, FIXTURE, SEQUENCE)
    other = _copy(FIXTURE)
    other["spsvin"]["vin"] = OTHER
    other["spsvin"]["asbuiltRpoCodes"] = ["OTHER"]
    save_vin(database, OTHER, other, SEQUENCE)
    assert first.path == database
    assert first.controllers == 1
    assert first.functions == 1
    assert first.methods == 1
    assert first.supported_controllers == 1
    assert first.calibrations == 2
    assert first.module_slots == 1
    assert first.rpos == 3

    connection = sqlite3.connect(database)
    vin_row = connection.execute(
        """
        SELECT vehicle_type, s_line_series, engineering_model_year, truck, job_card, vci_json, cop_json,
               device_json, extras_json, adapter_type, has_dependency, has_valid_chain, sequence_json, fetched_at
        FROM vin WHERE vin = ?
        """,
        (VIN,),
    ).fetchone()
    assert vin_row is not None
    assert vin_row[0] == "NAOVin"
    assert vin_row[1] == "RD"
    assert vin_row[2] == 2017
    assert vin_row[3] == 0
    assert vin_row[4] == ""
    assert json.loads(vin_row[5]) == {"10": 1}
    assert json.loads(vin_row[6]) == {"C67": [10]}
    assert json.loads(vin_row[7]) == [{"id": 1}]
    extras = json.loads(vin_row[8])
    assert extras["unknownMap"] == {"keep": True}
    assert extras["warrantyClaimCode"] == {"deviceID": "00"}
    assert extras["wmiByPass"] == []
    assert extras["fixture"]["displayName"]["controllerLabel"] == "controllerlabel"
    assert extras["controllerReferenceTree"] == {"treeNote": "kept"}
    assert extras["referenceFields"][0]["fields"][0] == {"note": "keep"}
    assert vin_row[9] == "NAOVin"
    assert vin_row[10] == 0
    assert vin_row[11] == 1
    assert json.loads(vin_row[12]) == {"futureField": {"n": 1}}
    assert vin_row[13].endswith("+00:00")
    controller = connection.execute(
        "SELECT code, label, display_order FROM controller WHERE vin = ?", (VIN,)
    ).fetchone()
    assert controller == ("K17", "Brake", 0)
    function = connection.execute("SELECT label, display_order FROM function WHERE vin = ?", (VIN,)).fetchone()
    assert function == ("Programming", 1)
    method = connection.execute(
        """
        SELECT method_id, description, block_same_cal, method_type, current_selection_idx, selected_codes_json, options_json
        FROM method WHERE vin = ?
        """,
        (VIN,),
    ).fetchone()
    assert method is not None
    assert method[:5] == (128, "Normal", 1, "ProductionOptionComposite", 0)
    assert json.loads(method[5]) == ["A"]
    assert json.loads(method[6])["options"] == [{"label": "OnStar"}]
    supported = connection.execute(
        "SELECT controller_id, display_name, document_json FROM supported_controller WHERE vin = ?",
        (VIN,),
    ).fetchone()
    assert supported is not None
    assert supported[0] == 54
    assert supported[1] == "Telematics"
    assert json.loads(supported[2])["extra"] == "kept"
    parts = connection.execute(
        "SELECT slot, sequence, part_number, flag, label, cvn FROM calibration WHERE vin = ? ORDER BY sequence",
        (VIN,),
    ).fetchall()
    assert parts == [("11", 0, "84045917", "0", "Locking", "ABCD"), ("11", 1, "84176905", "1", "Updated", "EF01")]
    assert connection.execute("SELECT slot, label FROM module_slot WHERE vin = ?", (VIN,)).fetchone() == (
        "11",
        "Lock Module",
    )
    rpos = connection.execute("SELECT source, code FROM rpo WHERE vin = ? ORDER BY source, position", (VIN,)).fetchall()
    assert rpos == [("asbuilt", "AG6"), ("asbuilt", "AYF"), ("selected", "EXTRA")]

    replacement = _copy(SEQUENCE)
    replacement["calibrationData"] = {"2": [["999", "0", "Only"]]}
    replacement["cvnMap"] = {"999": "FFFF"}
    replaced_fixture = _copy(FIXTURE)
    replaced_fixture["spsvin"]["asbuiltRpoCodes"] = ["ZZZ"]
    replaced_fixture["rpoCodes"] = []
    again = save_vin(database, VIN, replaced_fixture, replacement)
    assert again.calibrations == 1
    assert again.rpos == 1
    assert connection.execute("SELECT part_number FROM calibration WHERE vin = ?", (VIN,)).fetchall() == [("999",)]
    assert connection.execute("SELECT code FROM rpo WHERE vin = ?", (VIN,)).fetchall() == [("ZZZ",)]
    assert connection.execute("SELECT part_number FROM calibration WHERE vin = ?", (OTHER,)).fetchone() == ("84045917",)
    connection.close()


def test_a_database_inside_the_repository_is_refused():
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(SpsInfoError, match="outside the repository"):
        save_vin(root / "spsinfo.sqlite", VIN, FIXTURE, SEQUENCE)
    with pytest.raises(SpsInfoError, match="outside the repository"):
        save_vin(Path("spsinfo.sqlite"), VIN, FIXTURE, SEQUENCE)
    assert not (root / "spsinfo.sqlite").exists()


def test_a_token_shaped_string_is_refused(tmp_path: Path):
    database = tmp_path / "nested" / "spsinfo.sqlite"
    poisoned = _copy(FIXTURE)
    poisoned["spsvin"]["jobCard"] = "eyJhbGciOi.eyJzdWI.sig"
    with pytest.raises(SpsInfoError, match="token"):
        save_vin(database, VIN, poisoned, SEQUENCE)
    sequenced = _copy(SEQUENCE)
    sequenced["futureField"] = {"note": "eyJaaa.bbb.ccc"}
    with pytest.raises(SpsInfoError, match="token"):
        save_vin(database, VIN, FIXTURE, sequenced)
    assert not database.exists()


def test_the_bearer_is_read_from_the_cookie_and_then_dropped():
    import time
    from http.cookiejar import Cookie

    from spskit.cli import _JAR, sps_info_bearer

    _JAR.clear()
    _JAR.set_cookie(
        Cookie(
            0,
            "SPS-INFO_ACCESS_TOKEN",
            BEARER,
            None,
            False,
            "gateway.example",
            True,
            False,
            "/",
            True,
            True,
            int(time.time()) + 60,
            False,
            None,
            None,
            {},
        )
    )
    assert sps_info_bearer() == BEARER
    assert all(cookie.name != "SPS-INFO_ACCESS_TOKEN" for cookie in _JAR)
    _JAR.clear()


def test_sync_sends_the_bearer_and_posts_the_fixture(tmp_path: Path):
    fixture_bytes = json.dumps(FIXTURE).encode("utf-8")
    calls: list[tuple[str, str, bytes | None, dict[str, str]]] = []

    def exchange(method: str, url: str, body: bytes | None, headers: dict[str, str]) -> tuple[int, bytes]:
        calls.append((method, url, body, dict(headers)))
        if method == "GET" and url.endswith(f"/vin/fixture/{VIN}"):
            assert headers["Authorization"] == "Bearer " + BEARER
            assert body is None
            return 200, fixture_bytes
        assert method == "POST"
        assert url == "https://gateway.example/spsinfo/progseq"
        assert body is not None
        posted = json.loads(body)
        assert posted["spsvin"] == FIXTURE["spsvin"]
        assert posted["displayName"]["controllerCode"] == "K17"
        assert posted["programmingMethod"]["description"] == "Normal"
        assert headers["Authorization"] == "Bearer " + BEARER
        assert headers["Accept"] == "*/*"
        assert headers["content-type"] == "application/json"
        assert headers["Origin"] == "https://gateway.example"
        return 200, json.dumps(SEQUENCE).encode("utf-8")

    catalog = sync_sps_vin(_settings(tmp_path), VIN, BEARER, exchange)
    assert [call[0] for call in calls] == ["GET", "POST"]
    assert catalog.calibrations == 2
    assert BEARER.encode() not in (tmp_path / "spsinfo.sqlite").read_bytes()


def test_sps_prints_the_catalog_path_and_not_the_bearer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    download = tmp_path / "out"
    download.mkdir()
    (download / "session.json").write_text(json.dumps({"access_token": ACCESS}) + "\n", encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text(
        "SPS_DOWNLOAD_DIR="
        + str(download)
        + "\nTDS_GATEWAY=https://gateway.example\nTDS_BACKEND=https://backend.example\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("spskit.cli.sps_info_bearer", lambda: BEARER)
    fixture_bytes = json.dumps(FIXTURE).encode("utf-8")

    def exchange(method: str, url: str, body: bytes | None, headers: dict[str, str]) -> tuple[int, bytes]:
        if url.endswith("/api/tds-backend"):
            assert method == "GET"
            return 200, b"header.payload.signature"
        if url.endswith("/spsCallibration/accessSPSCal"):
            assert method == "GET"
            assert headers["Authorization"] == "Bearer header.payload.signature"
            assert headers["X-EEID-Access-Token"] == ACCESS
            assert body is None
            return 200, FORM.encode("utf-8")
        if url.endswith("/sporef/ui"):
            assert method == "POST"
            assert body is not None
            assert b"appParm=sps2info" in body
            assert TICKET.encode() in body
            return 200, b"<html></html>"
        if url.endswith(f"/vin/fixture/{VIN}"):
            assert headers["Authorization"] == "Bearer " + BEARER
            return 200, fixture_bytes
        assert url.endswith("/spsinfo/progseq")
        assert body is not None
        assert json.loads(body)["programmingMethod"]["methodId"] == 128
        return 200, json.dumps(SEQUENCE).encode("utf-8")

    code = run(["--env", str(env), "sps", "--vin", VIN], exchange)
    captured = capsys.readouterr()
    assert code == 0
    assert str(download / "spsinfo.sqlite") in captured.out
    assert "2 calibrations" in captured.out
    assert BEARER not in captured.out
    assert BEARER not in captured.err
    assert ACCESS not in captured.out
    assert TICKET not in captured.out
    assert BEARER.encode() not in (download / "spsinfo.sqlite").read_bytes()
