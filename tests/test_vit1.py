from __future__ import annotations

import json
from pathlib import Path

import pytest

from spskit.vit1 import (
    PROGRAMMING_DATA_PATH,
    Vit1Error,
    build_vit1,
    decimal_partno,
    format1_text,
    format2_copy,
    k17_attributes,
    module_attributes,
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
SPS_VIN = {"type": "NAOVin", "vin": VIN}
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
OPTIONS = {"type": "ProductionOptionComposite", "currentSelectionIdx": 0, "selectedCodes": [], "options": []}


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
    assert list(body) == ["clientState", "spsVin", "method", "controller", "optionComposite"]
    assert "mcvm" not in list(body)
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
    assert "mcvm" not in encoded
    assert body["spsVin"]["type"] == "NAOVin"
    assert body["optionComposite"]["type"] == "ProductionOptionComposite"
    assert "@type" not in encoded
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
    with pytest.raises(Vit1Error, match="not a saved-read rule"):
        programming_data_request(
            client_state=CLIENT,
            sps_vin=SPS_VIN,
            method=METHOD,
            controller=radio,
            option_composite=OPTIONS,
            attributes=k17_attributes(vin=VIN, parts=_parts(), ssecuhn="fixture-hw"),
        )


def _controller(
    code: str, device_id: int, request_method: int, part_addresses: str, *, read_cvn: int
) -> dict[str, object]:
    return {
        "deviceId": device_id,
        "displayName": {"controllerCode": code, "controllerLabel": code, "displayOrder": 0},
        "requestMethod": {
            "reqMethodID": request_method,
            "deviceID": device_id,
            "vinAddresses": "90",
            "partAddresses": part_addresses,
            "partLength": "4",
            "partStartByte": "1",
            "hardwareIdAddresses": "CC",
            "readVIN": 1,
            "readParts": 1,
            "readHardwareId": 1,
            "readCvn": read_cvn,
            "readSecuritySeed": 1,
        },
        "secCodeRequired": True,
    }


def _body_for(controller: dict[str, object], attributes: tuple[tuple[str, str], ...]) -> dict[str, object]:
    return programming_data_request(
        client_state=CLIENT,
        sps_vin=SPS_VIN,
        method=METHOD,
        controller=controller,
        option_composite=OPTIONS,
        attributes=attributes,
    )


def test_k33_k20_and_k9_reads_attach_as_vit1_blocks():
    k33_parts = {did: _payload(index) for index, did in enumerate(PART_DIDS, start=1)}
    k33 = _body_for(
        _controller("K33", 153, 11231, ",".join(PART_DIDS), read_cvn=0),
        module_attributes("K33", vin=VIN, parts=k33_parts, hardware=_payload(42)),
    )
    k33_attrs = k33["controller"]["vit1"]["cmbs"][0]["vitAttrs"]
    assert k33["controller"]["deviceId"] == 153
    assert k33["controller"]["requestMethod"]["reqMethodID"] == 11231
    assert k33_attrs[0] == {"key": "ssecuhn", "value": "42"}
    assert [item["value"] for item in k33_attrs if item["key"] == "partno"] == [str(index) for index in range(1, 11)]
    assert "cvn_in_vit1" not in json.dumps(k33_attrs)

    k9_dids = (*PART_DIDS, "41", "42", "43", "44", "45", "46", "47", "48", "49", "4A")
    k9_parts = {did: _payload(index) for index, did in enumerate(k9_dids, start=1)}
    k9 = _body_for(
        _controller("K9", 64, 410, ",".join(k9_dids), read_cvn=0),
        module_attributes("K9", vin=VIN, parts=k9_parts, hardware=_payload(7)),
    )
    k9_partnos = [item["value"] for item in k9["controller"]["vit1"]["cmbs"][0]["vitAttrs"] if item["key"] == "partno"]
    assert k9["controller"]["requestMethod"]["reqMethodID"] == 410
    assert k9_partnos == [str(index) for index in range(1, 21)]

    k20 = _body_for(
        _controller("K20", 17, 11229, ",".join(PART_DIDS), read_cvn=1),
        module_attributes("K20", vin=VIN, parts=k33_parts, hardware=_payload(3), cvn="1", partnums=("cell-15",)),
    )
    k20_attrs = k20["controller"]["vit1"]["cmbs"][0]["vitAttrs"]
    assert k20["controller"]["deviceId"] == 17
    assert k20_attrs[-2] == {"key": "partnum", "value": "cell-15"}
    assert k20_attrs[-1] == {"key": "cvn_in_vit1", "value": "1"}
    encoded = json.dumps(k20)
    assert all(part not in encoded for part in CATALOG_PARTS)
    assert "0000A407" not in encoded

    quiet = module_attributes("K20", vin=VIN, parts=k33_parts, hardware=_payload(3), cvn="0")
    assert quiet[-1] == ("cvn_in_vit1", "0")
    assert quiet[0] == ("ssecuhn", "3")
    with pytest.raises(Vit1Error, match="1 or 0"):
        module_attributes("K20", vin=VIN, parts=k33_parts, hardware=_payload(3), cvn="fixture-cvn")
    with pytest.raises(Vit1Error, match="CVN stays off"):
        module_attributes("K33", vin=VIN, parts=k33_parts, hardware=_payload(42), cvn="1", partnums=("cell-15",))


def test_the_other_method_128_reads_attach():
    rows = (
        ("A22", 102, 446, ("C1",), "CB", False, ""),
        ("A11", 128, 432, ("C1", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "73"), "CB", False, ""),
        ("B218R", 91, 11243, PART_DIDS, "CB", False, ""),
        ("B218L", 185, 11239, PART_DIDS, "CB", False, ""),
        ("B233B", 210, 388, ("C1", "C2"), "CB", False, ""),
        ("K43", 49, 417, ("C1", "C2", "C3"), "CB", False, ""),
        ("K84", 175, 427, ("C1", "C2", "C3"), "CB", False, ""),
        ("T3", 129, 434, ("C1", "CA"), "CB", False, ""),
        ("K182", 187, 423, ("C1", "C2"), "CB", False, ""),
        ("K109", 188, 428, ("C1", "C2"), "CB", False, ""),
        ("K177", 43, 416, ("C1", "C2"), "CC", False, ""),
        ("K107A", 29, 531, ("C1", "C2", "C3"), "CB", True, ""),
        ("K107B", 30, 532, ("C1", "C2", "C3"), "CC", True, ""),
        ("K118", 156, 530, ("C1", "C2"), None, False, ""),
        ("P16", 96, 11242, (*PART_DIDS, "40", "42", "44", "67", "69", "71", "74", "76"), "CB", False, VIN),
        ("K73", 151, 601, (), "CB", False, VIN),
    )
    for code, device, method, dids, hardware_did, cvn, vin in rows:
        parts = {did: _payload(index) for index, did in enumerate(dids, start=1)}
        hardware = None if hardware_did is None else _payload(9)
        attributes = module_attributes(code, vin=vin, parts=parts, hardware=hardware, cvn="0" if cvn else None)
        body = _body_for(_controller(code, device, method, ",".join(dids), read_cvn=int(cvn)), attributes)
        attrs = body["controller"]["vit1"]["cmbs"][0]["vitAttrs"]
        names = [item["key"] for item in attrs]
        assert body["controller"]["deviceId"] == device
        assert body["controller"]["requestMethod"]["reqMethodID"] == method
        assert names.count("partno") == len(dids)
        assert ("ssecuhn" in names) is (hardware_did is not None)
        assert ("vin" in names) is (vin != "")
        assert ("cvn_in_vit1" in names) is cvn
        assert all(part not in json.dumps(body) for part in CATALOG_PARTS)
    flagged = module_attributes(
        "K107A",
        vin="",
        parts={did: _payload(index) for index, did in enumerate(("C1", "C2", "C3"), start=1)},
        hardware=_payload(9),
        cvn="1",
        partnums=("cell-4",),
    )
    assert flagged[-1] == ("cvn_in_vit1", "1")
    with pytest.raises(Vit1Error, match="does not read a VIN"):
        module_attributes("A22", vin=VIN, parts={"C1": _payload(1)}, hardware=_payload(9))
    missing = _controller("K73", 151, 520, "C7", read_cvn=0)
    with pytest.raises(Vit1Error, match="not a saved-read rule"):
        _body_for(missing, (("ssecuhn", "1"), ("partno", "1")))


def test_format1_is_two_characters_per_byte_and_format2_is_the_slice():
    response = bytes([0x00, 0x00, 0x5A, 0x81, 0x2A, 0x00, 0x01])
    assert format1_text(response, 1, 1) == "2:"
    assert format2_copy(response, 1, 3) == bytes([0x2A, 0x00, 0x01])


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
