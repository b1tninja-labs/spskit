"""Programming-data request for the method-128 reads on this VIN.

A saved module read is attribute pairs. Those pairs become the VIT1 control-module
block on the controller. This module returns the request body. It does not post it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from spskit.spsinfo import SpsInfoError, check_vin

PROGRAMMING_DATA_PATH = "/sps/legacy/cloud/getProgrammingData"
VCI_PROGRAMMING_DATA_PATH = "/sps/legacy/cloud/getVciProgrammingData"
SELECTED_CONTROLLER_PATH = "/sps/legacy/cloud/getSelectedController"
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
    hardware_decimal: bool
    cvn: bool
    read_vin: bool = True
    hardware_did: str | None = "CC"


def _rule(
    code: str,
    device_id: int,
    request_method: int,
    part_dids: tuple[str, ...],
    *,
    hardware_did: str | None,
    cvn: bool = False,
    read_vin: bool = False,
) -> _ReadRule:
    return _ReadRule(
        code,
        device_id,
        request_method,
        part_dids,
        hardware_did is not None,
        cvn,
        read_vin,
        hardware_did,
    )


_C1_C2 = ("C1", "C2")
_C1_C3 = ("C1", "C2", "C3")
_A11_PARTS = ("C1", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "73")
_P16_PARTS = (*PART_DIDS, "40", "42", "44", "67", "69", "71", "74", "76")

# GMLAN format 0, length 4, start 1 prints four bytes from the first data byte.
# K17's hardware length is 0, and that length does not print a decimal.
# cvn_in_vit1 is the character 1 or 0. The digits sit in partnum after a hyphen.
# A missing hardware DID means the request method does not read one.
_RULES = (
    _ReadRule("K17", K17_DEVICE_ID, K17_REQUEST_METHOD, PART_DIDS, False, False),
    _ReadRule("K33", 153, 11231, PART_DIDS, True, False),
    _ReadRule("K20", 17, 11229, PART_DIDS, True, True),
    _ReadRule("K9", 64, 410, PART_DIDS + _PARTS_41_4A, True, False),
    _rule("A22", 102, 446, ("C1",), hardware_did="CB"),
    _rule("A11", 128, 432, _A11_PARTS, hardware_did="CB"),
    _rule("B218R", 91, 11243, PART_DIDS, hardware_did="CB"),
    _rule("B218L", 185, 11239, PART_DIDS, hardware_did="CB"),
    _rule("B233B", 210, 388, _C1_C2, hardware_did="CB"),
    _rule("K43", 49, 417, _C1_C3, hardware_did="CB"),
    _rule("K84", 175, 427, _C1_C3, hardware_did="CB"),
    _rule("T3", 129, 434, ("C1", "CA"), hardware_did="CB"),
    _rule("K182", 187, 423, _C1_C2, hardware_did="CB"),
    _rule("K109", 188, 428, _C1_C2, hardware_did="CB"),
    _rule("K177", 43, 416, _C1_C2, hardware_did="CC"),
    _rule("K107A", 29, 531, _C1_C3, hardware_did="CB", cvn=True),
    _rule("K107B", 30, 532, _C1_C3, hardware_did="CC", cvn=True),
    _rule("K118", 156, 530, _C1_C2, hardware_did=None),
    _rule("P16", 96, 11242, _P16_PARTS, hardware_did="CB", read_vin=True),
    _rule("K73", 151, 601, (), hardware_did="CB", read_vin=True),
    _rule("K124", 108, 396, (*PART_DIDS, "60", "62", "64", "66", "68", "6A"), hardware_did="CB"),
    _rule("K74", 143, 579, ("C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "71"), hardware_did="C1"),
    _rule("K114B", 203, 529, _C1_C2, hardware_did=None, read_vin=True),
    _rule("K36", 88, 421, _C1_C3, hardware_did="C1", read_vin=True),
)
_BY_CODE = {rule.code: rule for rule in _RULES}


class Vit1Error(ValueError):
    """A module read cannot be attached to the programming-data request."""


def decimal_partno(payload: bytes) -> str:
    """Four bytes from byte 1 of a DID payload, printed in base 10.

    Byte 0 is the DID echo. The next four are an unsigned integer, first byte
    most significant. That is the GMLAN format-0 slice for start byte 1 and
    length 4. A value at or above 2**31 would be printed with a minus for a
    part. Hardware uses the unsigned print, and the part numbers in this
    catalog sit below that line.
    """
    if not isinstance(payload, bytes | bytearray):
        raise Vit1Error("a part DID payload is bytes")
    end = PART_START + PART_LENGTH
    if len(payload) < end:
        raise Vit1Error("a part DID needs 4 bytes from byte 1")
    return str(int.from_bytes(payload[PART_START:end], "big"))


def format0_decimal(response: bytes, start: int, length: int) -> str:
    """The GMLAN format-0 integer from a service ``$1A`` response.

    Response byte 2 is the service. ``0x7F`` writes nothing. The start byte is
    added to 3, so start 1 is response byte 4. Length is 1 to 4. The bytes are
    an unsigned integer, first byte most significant.
    """
    if not isinstance(response, bytes | bytearray):
        raise Vit1Error("a module response is bytes")
    if length not in range(1, 5):
        raise Vit1Error("format 0 length is 1 to 4")
    if len(response) < 3 or response[2] == 0x7F:
        raise Vit1Error("a negative response writes no number")
    begin = start + 3
    end = begin + length
    if begin < 0 or len(response) < end:
        raise Vit1Error("the response is shorter than the format-0 slice")
    return str(int.from_bytes(response[begin:end], "big"))


def _response_slice(response: bytes, start: int, length: int, limit: int) -> bytes:
    if not isinstance(response, bytes | bytearray):
        raise Vit1Error("a module response is bytes")
    if length not in range(1, limit + 1):
        raise Vit1Error(f"this format length is 1 to {limit}")
    if len(response) < 3 or response[2] == 0x7F:
        raise Vit1Error("a negative response writes no number")
    begin = start + 3
    end = begin + length
    if begin < 0 or len(response) < end:
        raise Vit1Error("the response is shorter than the format slice")
    return bytes(response[begin:end])


def format1_text(response: bytes, start: int, length: int) -> str:
    """Format 1: each selected byte becomes two characters.

    Each nibble is added to ``0x30``. The characters run ``0`` through ``9``
    and then ``:`` through ``?``. Length is 1 to 16. The slice is the same
    start-plus-3 index as format 0.
    """
    text = []
    for byte in _response_slice(response, start, length, 16):
        text.append(chr(0x30 + (byte >> 4)))
        text.append(chr(0x30 + (byte & 0x0F)))
    return "".join(text)


def format2_copy(response: bytes, start: int, length: int) -> bytes:
    """Format 2: the selected bytes, copied as they are.

    Length is 1 to 16. The rest of the native buffer stays 0, so this returns
    only the copied slice. K73's hardware DID ``$81`` uses length 3 and is not
    attached here, because those bytes are not yet a ``ssecuhn`` string.
    """
    return _response_slice(response, start, length, 16)


def k17_attributes(*, vin: str, parts: Mapping[str, bytes], ssecuhn: str) -> tuple[tuple[str, str], ...]:
    """Pair a K17 read: vin from DID $90, one partno per $C1 through $CA, ssecuhn from $CC.

    The four-byte slice is the part DIDs. Hardware length on this request method
    is 0, so ssecuhn stays the string from the read.
    """
    return module_attributes("K17", vin=vin, parts=parts, hardware=ssecuhn)


def module_attributes(
    code: str,
    *,
    vin: str,
    parts: Mapping[str, bytes],
    hardware: bytes | str | None = None,
    cvn: str | None = None,
    partnums: Sequence[str] = (),
) -> tuple[tuple[str, str], ...]:
    """Pair a saved read for one Normal request method on this VIN.

    Parts are 4 bytes from byte 1, printed in base 10, in request-method order.
    A hardware DID of format 0, length 4, start 1 is that same decimal. K17
    keeps the hardware string. A request method that does not read hardware or
    a VIN omits that pair. ``cvn_in_vit1`` is ``1`` or ``0``. When it is ``1``,
    each ``partnum`` is the part string, a hyphen, and a decimal.
    """
    rule = _BY_CODE.get(code)
    if rule is None:
        raise Vit1Error("this controller is not a saved-read rule")
    pairs: list[tuple[str, str]] = []
    if rule.hardware_did is None:
        if hardware is not None:
            raise Vit1Error(f"{rule.code} does not read a hardware id")
    elif rule.hardware_decimal:
        if not isinstance(hardware, bytes | bytearray):
            raise Vit1Error(f"{rule.code} hardware DID {rule.hardware_did} is 4 bytes from byte 1")
        pairs.append(("ssecuhn", decimal_partno(bytes(hardware))))
    elif not isinstance(hardware, str) or hardware == "":
        raise Vit1Error("ssecuhn is the hardware string from the read")
    else:
        pairs.append(("ssecuhn", hardware))
    if rule.read_vin:
        pairs.append(("vin", _vin(vin)))
    elif vin != "":
        raise Vit1Error(f"{rule.code} does not read a VIN")
    if set(parts) != set(rule.part_dids):
        raise Vit1Error(f"{rule.code} needs one part payload per part DID on its request method")
    if rule.hardware_decimal and rule.hardware_did in rule.part_dids:
        same = decimal_partno(parts[rule.hardware_did])
        if pairs[0] != ("ssecuhn", same):
            raise Vit1Error(f"{rule.code} hardware DID {rule.hardware_did} is that part's read")
    pairs.extend(("partno", decimal_partno(parts[did])) for did in rule.part_dids)
    pairs.extend(_cvn_tail(rule, cvn, partnums))
    return tuple(pairs)


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
    """The body of POST /sps/legacy/cloud/getProgrammingData for one saved read.

    ``controller`` is the programming sequence. The saved read is attached as
    its ``vit1``. The same body is what ``SelectedControllerTask`` posts to
    ``/getSelectedController``. The caller supplies the catalog documents. This
    function does not read a VIN catalog, open a socket, or fill part numbers.
    """
    if method.get("methodId") not in {1, 128}:
        raise Vit1Error("this body is the getProgrammingData request, method 1 or 128")
    sequence = _controller_with_read(controller, attributes)
    # SpsGson does not call serializeNulls(), so a null mcvm is omitted.
    return {
        "clientState": _document(client_state, "clientState"),
        "spsVin": _document(sps_vin, "spsVin"),
        "method": _document(method, "method"),
        "controller": sequence,
        "optionComposite": _document(option_composite, "optionComposite"),
    }


def after_selected_controller(
    current: Mapping[str, object],
    controllers: Sequence[Mapping[str, object]],
    *,
    composite_populated: bool,
) -> dict[str, object] | None:
    """The root after a non-GSPAS ``/getSelectedController`` response.

    One controller replaces the root. That object is the response controller,
    so a ``vit1`` on ``current`` is not copied onto it. More than one controller
    and a populated option composite stops on the options screen, and this
    returns ``None`` instead of a controller to post. More than one controller
    and an empty composite keeps ``current`` and the post still runs.
    """
    if not controllers:
        raise Vit1Error("the selected-controller response has no controller")
    if len(controllers) > 1 and composite_populated:
        return None
    if len(controllers) == 1:
        return _document(controllers[0], "controller")
    return _document(current, "controller")


def after_programming_data(response: Mapping[str, object]) -> dict[str, object]:
    """The root after ``/getProgrammingData`` returns.

    ``validateAndReturnResponse`` throws when ``success`` is not true, and
    ``GetProgrammingDataTask`` sets the root only after that return. A failed
    body, including ``VIT_NO_VALID_CMB``, raises here and the posted controller
    stays. A success returns the response ``controller`` alone.
    """
    document = _document(response, "response")
    if document.get("success") is not True:
        code = document.get("errorCode")
        if isinstance(code, str) and code:
            raise Vit1Error(code)
        raise Vit1Error("the programming-data response failed")
    controller = document.get("controller")
    if not isinstance(controller, dict):
        raise Vit1Error("the programming-data response has no controller")
    return _document(controller, "controller")


def sequences_after_programming_data(
    controller: Mapping[str, object],
) -> list[dict[str, object]]:
    """The sequences checked for ``programmingData`` before a security screen.

    Device 252 is a container. It is not itself a sequence, and each value of
    ``mapOfControllers`` is walked. Any other device is one sequence when that
    map is missing or empty and ``skipSameCalibration`` is not true. A missing
    map is treated as empty: ``Util.isEmptyHashMap`` is not in the decompiled
    sources, and the VIN catalog omits a null map. A sequence with no
    ``programmingData`` raises ``NO_CALIBRATIONS_SUPPORTED``.
    """
    found = _programming_sequences(_document(controller, "controller"))
    for sequence in found:
        if sequence.get("programmingData") is None:
            raise Vit1Error("NO_CALIBRATIONS_SUPPORTED")
    return found


def normal_programming_data_loop(
    sequences: Sequence[Mapping[str, object]],
    *,
    root: Mapping[str, object],
    current: Mapping[str, object] | None = None,
) -> None:
    """The loop in ``handleNormalAfterProgrammingData`` before any security screen.

    A null ``vit1`` on a device other than 253 is read before the later tests, so
    this raises and does not read ``keycode``. Pre-programming instructions on the
    root or the current sequence suppress the two throws below. Programming data
    whose ``id`` is 10 raises the unauthored-data error. An empty ``listOfModules``
    raises ``No modules found in programming data`` when there is no
    ``mcvmProgramming`` and the first control-module block is missing or carries a
    ``partno``. A first block with no ``partno`` does not raise. ``isEmptyCollection``
    is not in the decompiled sources; a null or empty list is empty.
    """
    root_document = _document(root, "controller")
    current_document = None if current is None else _document(current, "controller")
    suppressed = _has_pre_programming_instructions(root_document) or (
        current_document is not None and _has_pre_programming_instructions(current_document)
    )
    for sequence in sequences:
        document = _document(sequence, "controller")
        if document.get("vit1") is None and document.get("deviceId") != 253:
            raise Vit1Error("a null vit1 is read before the module test")
        if suppressed:
            continue
        data = document.get("programmingData")
        if isinstance(data, dict) and type(data.get("id")) is int and data.get("id") == 10:
            raise Vit1Error("VCI id of 10 indicates that the data is not authored, and is only for testing purposes")
        if document.get("mcvmProgramming") is not None or not isinstance(data, dict):
            continue
        if not _modules_empty(data) or not _empty_modules_are_unsupported(document.get("vit1")):
            continue
        raise Vit1Error("No modules found in programming data")


def _has_pre_programming_instructions(document: dict[str, object]) -> bool:
    raw = document.get("preProgrammingInstructions")
    if raw is None:
        return False
    if not isinstance(raw, list):
        raise Vit1Error("preProgrammingInstructions is not a list")
    return bool(raw)


def _modules_empty(data: dict[str, object]) -> bool:
    modules = data.get("listOfModules")
    if modules is None:
        return True
    if not isinstance(modules, list):
        raise Vit1Error("listOfModules is not a list")
    return not modules


def _empty_modules_are_unsupported(vit1: object) -> bool:
    """The control-module half of the empty-module condition."""
    if vit1 is None:
        return True
    if not isinstance(vit1, dict):
        raise Vit1Error("vit1 is not a document")
    blocks = vit1.get("cmbs")
    if not isinstance(blocks, list):
        raise Vit1Error("vit1 cmbs is not a list")
    if not blocks:
        return True
    if blocks[0] is None:
        return False
    first = blocks[0]
    if not isinstance(first, dict):
        raise Vit1Error("control module block is not a document")
    pairs = first.get("vitAttrs")
    if not isinstance(pairs, list):
        raise Vit1Error("vitAttrs is not a list")
    for pair in pairs:
        if not isinstance(pair, dict):
            raise Vit1Error("vit attribute is not a pair")
        if pair.get("key") == "partno":
            return True
    return False


def _programming_sequences(document: dict[str, object]) -> list[dict[str, object]]:
    device = document.get("deviceId")
    if type(device) is not int:
        raise Vit1Error("controller deviceId is not an integer")
    children = document.get("mapOfControllers")
    if children is None:
        empty = True
    elif isinstance(children, dict):
        empty = not children
    else:
        raise Vit1Error("mapOfControllers is not a map")
    if device != 252:
        skip = document.get("skipSameCalibration", False)
        if not isinstance(skip, bool):
            raise Vit1Error("skipSameCalibration is not a boolean")
        if empty and not skip:
            return [document]
        return []
    if empty or not isinstance(children, dict):
        return []
    found: list[dict[str, object]] = []
    for child in children.values():
        if not isinstance(child, dict):
            raise Vit1Error("mapOfControllers value is not a controller")
        found.extend(_programming_sequences(child))
    return found


def vci_programming_data_request(
    *,
    client_state: Mapping[str, object],
    sps_vin: Mapping[str, object],
    method: Mapping[str, object],
    controller: Mapping[str, object],
    attributes: Sequence[tuple[str, str]],
    function_steps: Sequence[Mapping[str, object]] | None = None,
    vci_steps: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """The body of POST /sps/legacy/cloud/getVciProgrammingData.

    Method 2 and method 256 take this shape. A null step list is the empty
    list the constructor stores. The documents inside the lists are the
    caller's. This function does not invent a VCI step, and it does not post.
    """
    if method.get("methodId") not in {2, 256}:
        raise Vit1Error("this body is the getVciProgrammingData request, method 2 or 256")
    sequence = _controller_with_read(controller, attributes)
    return {
        "clientState": _document(client_state, "clientState"),
        "spsVin": _document(sps_vin, "spsVin"),
        "method": _document(method, "method"),
        "controller": sequence,
        "functionSteps": [_document(item, "functionSteps") for item in function_steps or ()],
        "vciVOList": [_document(item, "vciVOList") for item in vci_steps or ()],
    }


def _controller_with_read(
    controller: Mapping[str, object],
    attributes: Sequence[tuple[str, str]],
) -> dict[str, object]:
    rule = _rule_for(controller)
    pairs = _pairs(attributes)
    names = [name for name, _ in pairs]
    cvn_count = 1 if rule.cvn else 0
    vin_count = 1 if rule.read_vin else 0
    hardware_count = 1 if rule.hardware_did is not None else 0
    if (
        names.count("vin") != vin_count
        or names.count("ssecuhn") != hardware_count
        or names.count("partno") != len(rule.part_dids)
    ):
        if rule.code == "K17":
            raise Vit1Error("a K17 read is one vin, ten part numbers, and one ssecuhn")
        raise Vit1Error(f"a {rule.code} read does not match its request method")
    if names.count("cvn_in_vit1") != cvn_count:
        if rule.cvn:
            raise Vit1Error(f"{rule.code} stores cvn_in_vit1 as 1 or 0")
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
            raise Vit1Error("ssecuhn is the hardware id from the read")
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
    return sequence


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
    raise Vit1Error("this controller is not a saved-read rule")


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
