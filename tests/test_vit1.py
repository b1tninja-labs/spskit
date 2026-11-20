from __future__ import annotations

import json
from pathlib import Path

import pytest

from spskit.vit1 import (
    PROGRAMMING_DATA_PATH,
    Vit1Error,
    build_vit1,
    decimal_partno,
    k17_attributes,
    programming_data_request,
)

VIN = "1G1TE5TVN00000001"
# Catalog suggestions for the brake sequence. The fixture must not use them.
CATALOG_PARTS = (
    "23394159",
    "23394161",
    "84131365",
    "23394158",
    "23394157",
    "23394136",
    "23394154",
    "23394155",
)
PART_DIDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA")

CLIENT = {"sessionID": "", "vin": VIN, "isTLC": True}
SPS_VIN = {"@type": "NAOVin", "vin": VIN, "type": "NAOVin"}
METHOD = {"methodId": 128, "description": "Normal", "blockSameCal": True}
CONTROLLER = {
    "deviceId": 40,
    "displayName": {
        "controllerCode": "K17",
        "controllerLabel": "Electronic Brake Control Module",
        "displayOrder": 0,
    },
    "requestMethod": {
        "reqMethodID": 11228,
        "deviceID": 40,
        "vinAddresses": "90",
        "partAddresses": "C1,C2,C3,C4,C5,C6,C7,C8,C9,CA",
        "partLength": "4",
        "partStartByte": "1",
        "hardwareIdAddresses": "CC",
        "hardwareIdLength": 0,
        "hardwareIdStartByte": 0,
        "readVIN": 1,
        "readParts": 1,
        "readHardwareId": 1,
        "readCvn": 0,
        "readSecuritySeed": 1,
    },
    "secCodeRequired": True,
}
OPTIONS = {"@type": "ProductionOptionComposite", "currentSelectionIdx": 0, "selectedCodes": [], "options": []}


def _payload(number: int) -> bytes:
    return bytes([0xFF]) + number.to_bytes(4, "big")


def _parts() -> dict[str, bytes]:
    return {did: _payload(index) for index, did in enumerate(PART_DIDS, start=1)}


def test_a_saved_k17_read_is_the_vit1_block_on_the_request():
    attributes = k17_attributes(vin=VIN, parts=_parts(), ssecuhn="fixture-hw")
    body = programming_data_request(
        client_state=CLIENT,
        sps_vin=SPS_VIN,
        method=METHOD,
        controller=CONTROLLER,
        option_composite=OPTIONS,
        attributes=attributes,
    )
    assert PROGRAMMING_DATA_PATH == "/sps/legacy/cloud/getProgrammingData"
    assert list(body) == ["clientState", "spsVin", "method", "controller", "mcvm", "optionComposite"]
    assert body["mcvm"] is None
    assert body["method"] == METHOD
    assert body["optionComposite"] == OPTIONS
    controller = body["controller"]
    assert controller["deviceId"] == 40
    assert controller["requestMethod"]["reqMethodID"] == 11228
    assert "vit1" not in CONTROLLER
    block = controller["vit1"]["cmbs"]
    assert len(block) == 1
    assert block[0]["vitAttrs"] == [
        {"key": "ssecuhn", "value": "fixture-hw"},
        {"key": "vin", "value": VIN},
        *({"key": "partno", "value": str(index)} for index in range(1, 11)),
    ]
    assert controller["vit1"]["vitAttrs"] == []
    assert controller["vit1"]["freeOptions"] == {"vitAttrs": []}
    encoded = json.dumps(body)
    assert all(part not in encoded for part in CATALOG_PARTS)
    source = Path(__file__).resolve().parents[1].joinpath("spskit", "vit1.py").read_text(encoding="utf-8")
    assert "urlopen" not in source
    assert "https://" not in source
    assert all(part not in source for part in CATALOG_PARTS)


def test_four_bytes_from_byte_1_are_a_decimal_partno():
    assert decimal_partno(bytes.fromhex("ff0000002a")) == "42"
    with pytest.raises(Vit1Error, match="4 bytes from byte 1"):
        decimal_partno(bytes.fromhex("0000002a"))


def test_a_second_ssecuhn_starts_another_block():
    vit1 = build_vit1((("ssecuhn", "one"), ("partno", "1"), ("ssecuhn", "two"), ("partno", "2")))
    assert vit1["cmbs"] == [
        {"vitAttrs": [{"key": "ssecuhn", "value": "one"}, {"key": "partno", "value": "1"}]},
        {"vitAttrs": [{"key": "ssecuhn", "value": "two"}, {"key": "partno", "value": "2"}]},
    ]


def test_a_header_stays_off_the_block_and_an_option_becomes_a_free_pair():
    vit1 = build_vit1((("sps_id", "7"), ("option", "left;right"), ("ssecuhn", "hw")))
    assert vit1["vitAttrs"] == [{"key": "sps_id", "value": "7"}]
    assert vit1["freeOptions"] == {"vitAttrs": [{"key": "left", "value": "right"}]}
    assert vit1["cmbs"] == [{"vitAttrs": [{"key": "ssecuhn", "value": "hw"}]}]


def test_a_request_without_the_k17_read_is_refused():
    with pytest.raises(Vit1Error, match="one vin, ten part numbers"):
        programming_data_request(
            client_state=CLIENT,
            sps_vin=SPS_VIN,
            method=METHOD,
            controller=CONTROLLER,
            option_composite=OPTIONS,
            attributes=(),
        )
    radio = {**CONTROLLER, "deviceId": 128}
    with pytest.raises(Vit1Error, match="device 40"):
        programming_data_request(
            client_state=CLIENT,
            sps_vin=SPS_VIN,
            method=METHOD,
            controller=radio,
            option_composite=OPTIONS,
            attributes=k17_attributes(vin=VIN, parts=_parts(), ssecuhn="fixture-hw"),
        )


def test_security_access_attributes_stay_off_the_request():
    attributes = (*k17_attributes(vin=VIN, parts=_parts(), ssecuhn="fixture-hw"), ("seed", "aabb"))
    with pytest.raises(Vit1Error, match="security access"):
        programming_data_request(
            client_state=CLIENT,
            sps_vin=SPS_VIN,
            method=METHOD,
            controller=CONTROLLER,
            option_composite=OPTIONS,
            attributes=attributes,
        )
