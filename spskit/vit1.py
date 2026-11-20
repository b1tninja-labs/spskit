"""Programming-data request for brake controller K17.

A saved module read is attribute pairs. Those pairs become the VIT1 control-module
block on the controller. This module returns the request body. It does not post it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from spskit.spsinfo import SpsInfoError, check_vin

PROGRAMMING_DATA_PATH = "/sps/legacy/cloud/getProgrammingData"
K17_DEVICE_ID = 40
K17_REQUEST_METHOD = 11228
PART_DIDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA")
PART_START = 1
PART_LENGTH = 4

_HEADER = frozenset({"sps_id", "chksum", "table_len", "nav_info", "reserved", "numcms", "devicetype", "spsmode"})
_BLOCK_START = frozenset({"ssecuhn", "blocklen", "disp_type", "protocol", "ecu_adr"})
_REFUSED = frozenset({"seed", "numseeds", "keycode", "msg_auth_sts", "cvn_in_vit1"})


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

    Hardware length and start byte on this request method are both 0, so ssecuhn
    is the string from the read. The four-byte part slice is only for the part DIDs.
    """
    checked = _vin(vin)
    if not isinstance(ssecuhn, str) or ssecuhn == "":
        raise Vit1Error("ssecuhn is the hardware id from DID CC")
    if set(parts) != set(PART_DIDS):
        raise Vit1Error("K17 needs one part payload for DID C1 through CA")
    partnos = tuple(("partno", decimal_partno(parts[did])) for did in PART_DIDS)
    return (("ssecuhn", ssecuhn), ("vin", checked), *partnos)


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
    """The body of POST /sps/legacy/cloud/getProgrammingData for K17.

    ``controller`` is the programming sequence. The saved read is attached as
    its ``vit1``. The caller supplies the catalog documents. This function does
    not read a VIN catalog, open a socket, or fill part numbers itself.
    """
    if controller.get("deviceId") != K17_DEVICE_ID:
        raise Vit1Error("this request is brake controller K17, device 40")
    request_method = controller.get("requestMethod")
    if not isinstance(request_method, Mapping) or request_method.get("reqMethodID") != K17_REQUEST_METHOD:
        raise Vit1Error("K17 uses request method 11228")
    if method.get("methodId") != 128:
        raise Vit1Error("this body is the getProgrammingData request, method 128")
    pairs = _pairs(attributes)
    names = [name for name, _ in pairs]
    if names.count("vin") != 1 or names.count("ssecuhn") != 1 or names.count("partno") != 10:
        raise Vit1Error("a K17 read is one vin, ten part numbers, and one ssecuhn")
    if any(name in _REFUSED for name, _ in pairs):
        raise Vit1Error("security access and CVN stay off this request")
    for name, value in pairs:
        if name == "vin":
            _vin(value)
        elif name == "partno" and (not value.isdigit() or (len(value) > 1 and value.startswith("0"))):
            raise Vit1Error("a partno is the decimal from 4 bytes of the part DID")
        elif name == "ssecuhn" and value == "":
            raise Vit1Error("ssecuhn is the hardware id from DID CC")
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
