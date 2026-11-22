from __future__ import annotations

import json
from pathlib import Path

import pytest

from spskit.handoff import (
    HandoffError,
    main,
    parse_clone_profile,
    request_from_read,
    vit1_from_read,
)
from spskit.vit1 import Vit1Error

VIN = "1G1TE5TVN00000001"
PART_DIDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA")


def _lid(ident: str, value: str) -> str:
    return f"lid {ident} {value}"


def _clone(ecu: str, lids: list[tuple[str, str]], *, req: str = "7E4", resp: str = "7EC") -> str:
    lines = [
        "# Captured module bytes. A did or lid line is the data after the service and the identifier.",
        "s3 5000",
        "",
        f"ecu {ecu} req={req} resp={resp} functional=yes pad=00 latency=4",
    ]
    lines.extend(_lid(ident, value) for ident, value in lids)
    return "\n".join(lines) + "\n"


def _part_value(number: int) -> str:
    return f"{number:08X}"


def _k17_lids() -> list[tuple[str, str]]:
    lids = [(did, _part_value(index)) for index, did in enumerate(PART_DIDS, start=1)]
    lids.append(("CC", b"HW000042".hex()))  # printable ASCII hardware string
    return lids


def test_parse_groups_lids_under_their_ecu_and_ignores_comments_and_notes():
    text = _clone("BECM", [("C1", "0000002A"), ("CC", "48573031")])
    text += "# lid 90 11\n# header 621 has no recorded response id\n"
    blocks = parse_clone_profile(text)
    assert list(blocks) == ["BECM"]
    assert blocks["BECM"].lids == {"C1": bytes.fromhex("0000002A"), "CC": bytes.fromhex("48573031")}


def test_a_captured_k17_read_becomes_the_vit1_block():
    envelope = vit1_from_read(_clone("BECM", _k17_lids()), code="K17", vin=VIN)
    assert envelope["code"] == "K17"
    assert envelope["deviceId"] == 40
    assert envelope["requestMethod"] == 11228
    assert envelope["vin"] == VIN
    attrs = envelope["vit1"]["cmbs"][0]["vitAttrs"]
    assert attrs == [
        {"key": "ssecuhn", "value": "HW000042"},
        {"key": "vin", "value": VIN},
        *({"key": "partno", "value": str(index)} for index in range(1, 11)),
    ]
    assert envelope["vit1"]["vitAttrs"] == []
    encoded = json.dumps(envelope)
    assert "urlopen" not in encoded
    assert "https://" not in encoded


def test_an_ssecuhn_override_replaces_the_derived_string():
    envelope = vit1_from_read(_clone("BECM", _k17_lids()), code="K17", vin=VIN, ssecuhn="given-hw")
    assert envelope["vit1"]["cmbs"][0]["vitAttrs"][0] == {"key": "ssecuhn", "value": "given-hw"}


def test_a_decimal_hardware_read_is_the_format0_slice():
    lids = [(did, _part_value(index)) for index, did in enumerate(PART_DIDS, start=1)]
    lids.append(("CC", _part_value(42)))
    envelope = vit1_from_read(_clone("M241", lids, req="241", resp="641"), code="K33", vin=VIN)
    attrs = envelope["vit1"]["cmbs"][0]["vitAttrs"]
    assert attrs[0] == {"key": "ssecuhn", "value": "42"}
    assert [item["value"] for item in attrs if item["key"] == "partno"] == [str(i) for i in range(1, 11)]


def test_a_cvn_controller_defaults_to_zero_and_takes_partnums():
    lids = [(did, _part_value(index)) for index, did in enumerate(PART_DIDS, start=1)]
    lids.append(("CC", _part_value(3)))
    quiet = vit1_from_read(_clone("BECM", lids), code="K20", vin=VIN)
    quiet_attrs = quiet["vit1"]["cmbs"][0]["vitAttrs"]
    assert quiet_attrs[-1] == {"key": "cvn_in_vit1", "value": "0"}

    cvn_lids = [(did, _part_value(index)) for index, did in enumerate(("C1", "C2", "C3"), start=1)]
    cvn_lids.append(("CB", _part_value(9)))
    flagged = vit1_from_read(
        _clone("HPCM2", cvn_lids, req="7E0", resp="7E8"), code="K107A", cvn="1", partnums=["cell-4"]
    )
    flagged_attrs = flagged["vit1"]["cmbs"][0]["vitAttrs"]
    assert "vin" not in [item["key"] for item in flagged_attrs]
    assert flagged_attrs[-2] == {"key": "partnum", "value": "cell-4"}
    assert flagged_attrs[-1] == {"key": "cvn_in_vit1", "value": "1"}


def test_k73_uses_its_decimal_hardware_and_no_parts():
    envelope = vit1_from_read(_clone("M241", [("CB", _part_value(9))], req="241", resp="641"), code="K73", vin=VIN)
    attrs = envelope["vit1"]["cmbs"][0]["vitAttrs"]
    names = [item["key"] for item in attrs]
    assert names.count("partno") == 0
    assert attrs[0] == {"key": "ssecuhn", "value": "9"}
    assert {"key": "vin", "value": VIN} in attrs


def test_k16_and_the_refused_k73_methods_have_no_rule():
    with pytest.raises(Vit1Error, match="not a saved-read rule"):
        vit1_from_read(_clone("BECM", [("C1", _part_value(1))]), code="K16", vin=VIN)


def test_a_missing_part_read_is_reported():
    with pytest.raises(HandoffError, match="no lid C2"):
        vit1_from_read(_clone("BECM", _k17_lids()[:1]), code="K17", vin=VIN)


def test_a_vin_is_required_only_when_the_controller_reads_one():
    with pytest.raises(HandoffError, match="reads a VIN"):
        vit1_from_read(_clone("BECM", _k17_lids()), code="K17")
    lids = [(did, _part_value(index)) for index, did in enumerate(("C1",), start=1)]
    lids.append(("CB", _part_value(9)))
    with pytest.raises(HandoffError, match="does not read a VIN"):
        vit1_from_read(_clone("BECM", lids), code="A22", vin=VIN)


def test_more_than_one_ecu_needs_a_choice():
    text = _clone("BECM", [("C1", _part_value(1))]) + _clone("IPC", [("C1", _part_value(2))], req="244", resp="644")
    with pytest.raises(HandoffError, match="more than one ecu"):
        vit1_from_read(text, code="K17", vin=VIN)


def test_the_template_body_carries_the_attached_read():
    controller = {"deviceId": 40, "requestMethod": {"reqMethodID": 11228}}
    template = {
        "clientState": {"vin": VIN},
        "spsVin": {"type": "NAOVin", "vin": VIN},
        "method": {"methodId": 128, "description": "Normal"},
        "controller": controller,
        "optionComposite": {"type": "ProductionOptionComposite"},
    }
    body = request_from_read(_clone("BECM", _k17_lids()), template, code="K17", vin=VIN)
    assert list(body) == ["clientState", "spsVin", "method", "controller", "optionComposite"]
    assert body["controller"]["vit1"]["cmbs"][0]["vitAttrs"][0] == {"key": "ssecuhn", "value": "HW000042"}
    assert "vit1" not in controller


def test_the_vci_template_copies_the_step_lists():
    template = {
        "clientState": {"vin": VIN},
        "spsVin": {"type": "NAOVin", "vin": VIN},
        "method": {"methodId": 2, "description": "VCI"},
        "controller": {"deviceId": 203, "requestMethod": {"reqMethodID": 529}},
        "vciVOList": [{"caller": "step"}],
    }
    lids = [("C1", _part_value(1)), ("C2", _part_value(2))]
    body = request_from_read(_clone("BECM", lids), template, code="K114B", vin=VIN)
    assert body["functionSteps"] == []
    assert body["vciVOList"] == [{"caller": "step"}]
    assert body["controller"]["vit1"]["cmbs"][0]["vitAttrs"][0]["key"] == "vin"


def test_the_cli_writes_the_vit1_json(tmp_path):
    read = tmp_path / "clone.txt"
    read.write_text(_clone("BECM", _k17_lids()), encoding="utf-8")
    out = tmp_path / "body.json"
    code = main(["--read", str(read), "--code", "K17", "--vin", VIN, "--out", str(out)])
    assert code == 0
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["vit1"]["cmbs"][0]["vitAttrs"][-1] == {"key": "partno", "value": "10"}


def test_the_cli_reports_a_refused_controller(tmp_path, capsys):
    read = tmp_path / "clone.txt"
    read.write_text(_clone("BECM", [("C1", _part_value(1))]), encoding="utf-8")
    code = main(["--read", str(read), "--code", "K16", "--vin", VIN])
    assert code == 2
    assert "not a saved-read rule" in capsys.readouterr().err


def test_the_module_opens_no_socket():
    source = Path(__file__).resolve().parents[1].joinpath("spskit", "handoff.py").read_text(encoding="utf-8")
    assert "urlopen" not in source
    assert "https://" not in source
    imports = [line.strip() for line in source.splitlines() if line.startswith(("import ", "from "))]
    joined = " ".join(imports)
    assert "voltkit" not in joined
    assert "socket" not in joined
    assert "urllib" not in joined
    assert "http" not in joined
