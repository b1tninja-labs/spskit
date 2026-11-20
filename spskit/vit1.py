"""Programming-data request for K17, K33, K20, and K9.

A saved module read is attribute pairs. Those pairs become the VIT1 control-module
block on the controller. This module returns the request body. It does not post it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from spskit.spsinfo import SpsInfoError, check_vin

PROGRAMMING_DATA_PATH = "/sps/legacy/cloud/getProgrammingData"
K17_DEVICE_ID = 40
K17_REQUEST_METHOD = 11228
PART_DIDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA")
_PARTS_41_4A = ("41", "42", "43", "44", "45", "46", "47", "48", "49", "4A")
PART_START = 1
PART_LENGTH = 4

_HEADER = frozenset({"sps_id", "chksum", "table_len", "nav_info", "reserved", "numcms", "devicetype", "spsmode"})
_BLOCK_START = frozenset({"ssecuhn", "blocklen", "disp_type", "protocol", "ecu_adr"})
_SECURITY = frozenset({"seed", "numseeds", "keycode", "msg_auth_sts"})


@dataclass(frozen=True, slots=True)
class _ReadRule:
    code: str
    device_id: int
    request_method: int
    part_dids: tuple[str, ...]
    cvn: bool


# ssecuhn is the string the reader already stored. The request-method hardware
# length and start byte are copied into the native record, and the function
# that would apply them to DID CC was not found. readCvn names no DID.
# cvn_in_vit1 is the character 1 or 0. The digits sit in partnum after a hyphen.
_RULES = (
    _ReadRule("K17", K17_DEVICE_ID, K17_REQUEST_METHOD, PART_DIDS, False),
    _ReadRule("K33", 153, 11231, PART_DIDS, False),
    _ReadRule("K20", 17, 11229, PART_DIDS, True),
    _ReadRule("K9", 64, 410, PART_DIDS + _PARTS_41_4A, False),
)
_BY_CODE = {rule.code: rule for rule in _RULES}


class Vit1Error(ValueError):
    """A module read cannot be attached to the programming-data request."""


def decimal_partno(payload: bytes) -> str:
    """Four bytes from byte 1 of a part DID, printed in base 10.

    The first byte of the payload is left off. The next four are an unsigned
    integer, first byte most significant.
    """
    if not isinstance(payload, bytes | bytearray):
        raise Vit1Error("a part DID payload is bytes")
    end = PART_START + PART_LENGTH
    if len(payload) < end:
        raise Vit1Error("a part DID needs 4 bytes from byte 1")
    return str(int.from_bytes(payload[PART_START:end], "big"))


def k17_attributes(*, vin: str, parts: Mapping[str, bytes], ssecuhn: str) -> tuple[tuple[str, str], ...]:
    """Pair a K17 read: vin from DID $90, one partno per $C1 through $CA, ssecuhn from $CC.

    The four-byte part slice is only for the part DIDs. ssecuhn is the string
    the reader stored.
    """
    return module_attributes("K17", vin=vin, parts=parts, hardware=ssecuhn)


def module_attributes(
    code: str,
    *,
    vin: str,
    parts: Mapping[str, bytes],
    hardware: str,
    cvn: str | None = None,
    partnums: Sequence[str] = (),
) -> tuple[tuple[str, str], ...]:
    """Pair a saved read for K17, K33, K20, or K9.

    Parts are 4 bytes from byte 1, printed in base 10, in request-method order.
    ``hardware`` is the ``ssecuhn`` string the reader stored. K20's ``cvn_in_vit1``
    is ``1`` or ``0``. When it is ``1``, each ``partnum`` is the part string, a
    hyphen, and the decimal from that part cell. The request method names no CVN DID.
    """
    rule = _BY_CODE.get(code)
    if rule is None:
        raise Vit1Error("a module read is K17, K33, K20, or K9")
    checked = _vin(vin)
    if not isinstance(hardware, str) or hardware == "":
        raise Vit1Error("ssecuhn is the hardware string from the read")
    if set(parts) != set(rule.part_dids):
        raise Vit1Error(f"{rule.code} needs one part payload per part DID on its request method")
    partnos = tuple(("partno", decimal_partno(parts[did])) for did in rule.part_dids)
    numbers = _cvn_tail(rule, cvn, partnums)
    return (("ssecuhn", hardware), ("vin", checked), *partnos, *numbers)


def build_vit1(attributes: Sequence[tuple[str, str]]) -> dict[str, object]:
    """Walk attribute pairs the way VIT1BuilderImpl does.

    Header names stay on the VIT1. An option value that contains ``;`` is split
    into one free-option pair. A block-start name that is already on the current
    block opens the next control-module block. The current block is appended when
    the list ends.
    """
    pairs = _pairs(attributes)
    header: list[tuple[str, str]] = []
    free: list[tuple[str, str]] = []
    blocks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    if not pairs:
        return _vit1(header, blocks, free)
    for name, value in pairs:
        if name in _BLOCK_START and any(key == name for key, _ in current):
            blocks.append(current)
            current = []
        if name == "option":
            option = _free_option(value)
            if option is not None:
                free.append(option)
            continue
        if name in _HEADER:
            header.append((name, value))
            continue
        current.append((name, value))
    blocks.append(current)
    return _vit1(header, blocks, free)


def programming_data_request(
    *,
    client_state: Mapping[str, object],
    sps_vin: Mapping[str, object],
    method: Mapping[str, object],
    controller: Mapping[str, object],
    option_composite: Mapping[str, object],
    attributes: Sequence[tuple[str, str]],
) -> dict[str, object]:
    """The body of POST /sps/legacy/cloud/getProgrammingData for K17, K33, K20, or K9.

    ``controller`` is the programming sequence. The saved read is attached as
    its ``vit1``. The caller supplies the catalog documents. This function does
    not read a VIN catalog, open a socket, or fill part numbers itself.
    """
    rule = _rule_for(controller)
    if method.get("methodId") != 128:
        raise Vit1Error("this body is the getProgrammingData request, method 128")
    pairs = _pairs(attributes)
    names = [name for name, _ in pairs]
    cvn_count = 1 if rule.cvn else 0
    if names.count("vin") != 1 or names.count("ssecuhn") != 1 or names.count("partno") != len(rule.part_dids):
        if rule.code == "K17":
            raise Vit1Error("a K17 read is one vin, ten part numbers, and one ssecuhn")
        raise Vit1Error(f"a {rule.code} read does not match its request method")
    if names.count("cvn_in_vit1") != cvn_count:
        if rule.cvn:
            raise Vit1Error("K20 stores cvn_in_vit1 as 1 or 0")
        raise Vit1Error("CVN stays off this request")
    cvn_values = [value for name, value in pairs if name == "cvn_in_vit1"]
    partnum_count = names.count("partnum")
    if cvn_values == ["1"] and partnum_count == 0:
        raise Vit1Error("cvn_in_vit1 1 carries at least one partnum")
    if cvn_values != ["1"] and partnum_count:
        raise Vit1Error("partnum belongs with cvn_in_vit1 1")
    if any(name in _SECURITY for name, _ in pairs):
        raise Vit1Error("security access stays off this request")
    for name, value in pairs:
        if name == "vin":
            _vin(value)
        elif name == "partno" and (not value.isdigit() or (len(value) > 1 and value.startswith("0"))):
            raise Vit1Error("a partno is the decimal from 4 bytes of the part DID")
        elif name == "ssecuhn" and value == "":
            raise Vit1Error("ssecuhn is the hardware id from DID CC")
        elif name == "cvn_in_vit1" and value not in {"0", "1"}:
            raise Vit1Error("cvn_in_vit1 is 1 or 0")
        elif name == "partnum":
            _check_partnum(value)
        elif name == "controller_supported" and value == "0":
            raise Vit1Error("the module read says the controller is unsupported")
    vit1 = build_vit1(pairs)
    blocks = vit1["cmbs"]
    if not isinstance(blocks, list) or not blocks:
        raise Vit1Error("the module read did not produce a control-module block")
    first = blocks[0]
    if not isinstance(first, dict) or not first.get("vitAttrs"):
        raise Vit1Error("the module read did not produce a control-module block")
    sequence = _document(controller, "controller")
    sequence["vit1"] = vit1
    return {
        "clientState": _document(client_state, "clientState"),
        "spsVin": _document(sps_vin, "spsVin"),
        "method": _document(method, "method"),
        "controller": sequence,
        "mcvm": None,
        "optionComposite": _document(option_composite, "optionComposite"),
    }


def _cvn_tail(rule: _ReadRule, cvn: str | None, partnums: Sequence[str]) -> tuple[tuple[str, str], ...]:
    if not rule.cvn:
        if cvn is not None or partnums:
            raise Vit1Error("CVN stays off this request")
        return ()
    if cvn not in {"0", "1"}:
        raise Vit1Error("cvn_in_vit1 is 1 or 0")
    if cvn == "0":
        if partnums:
            raise Vit1Error("partnum belongs with cvn_in_vit1 1")
        return (("cvn_in_vit1", "0"),)
    if not partnums:
        raise Vit1Error("cvn_in_vit1 1 carries at least one partnum")
    for value in partnums:
        _check_partnum(value)
    return (*(("partnum", value) for value in partnums), ("cvn_in_vit1", "1"))


def _check_partnum(value: str) -> None:
    pieces = value.split("-")
    if (
        len(pieces) != 2
        or pieces[0] == ""
        or not pieces[1].isdigit()
        or (len(pieces[1]) > 1 and pieces[1].startswith("0"))
    ):
        raise Vit1Error("partnum is the part string, a hyphen, and a decimal")


def _rule_for(controller: Mapping[str, object]) -> _ReadRule:
    request_method = controller.get("requestMethod")
    method_id = request_method.get("reqMethodID") if isinstance(request_method, Mapping) else None
    for rule in _RULES:
        if controller.get("deviceId") == rule.device_id and method_id == rule.request_method:
            return rule
    raise Vit1Error("this body is getProgrammingData for K17, K33, K20, or K9")


def _vin(vin: str) -> str:
    try:
        return check_vin(vin)
    except SpsInfoError as exc:
        raise Vit1Error(str(exc)) from exc


def _pairs(attributes: Sequence[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for item in attributes:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
        ):
            raise Vit1Error("a module read is attribute pairs")
        pairs.append((item[0], item[1]))
    return tuple(pairs)


def _attrs(pairs: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"key": key, "value": value} for key, value in pairs]


def _vit1(
    header: Sequence[tuple[str, str]],
    blocks: Sequence[Sequence[tuple[str, str]]],
    free: Sequence[tuple[str, str]],
) -> dict[str, object]:
    return {
        "vitAttrs": _attrs(header),
        "cmbs": [{"vitAttrs": _attrs(block)} for block in blocks],
        "freeOptions": {"vitAttrs": _attrs(free)},
    }


def _free_option(value: str) -> tuple[str, str] | None:
    parts = value.split(";")
    while parts and parts[-1] == "":
        parts.pop()
    pieces = [_trim_vit(part) for part in parts]
    if len(pieces) <= 1:
        return None
    return (pieces[0], pieces[1])


def _trim_vit(value: str) -> str:
    while value.startswith(("\t", " ")):
        value = value[1:]
    while value.endswith("\t") or value.startswith(" "):
        value = value[:-1]
    return value


def _document(value: Mapping[str, object], label: str) -> dict[str, object]:
    try:
        copied = json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise Vit1Error(f"{label} is not a document") from exc
    if not isinstance(copied, dict):
        raise Vit1Error(f"{label} is not a document")
    return copied
