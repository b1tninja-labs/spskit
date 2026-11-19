"""SPS Info catalog for one VIN. The database is part numbers and module names, not a calibration file."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

from spskit.config import ConfigError
from spskit.session import outside_repository

_VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
_TOKEN = re.compile(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*")
_Kind = Literal["str", "int", "bool"]
_SCALARS: dict[str, tuple[str, _Kind]] = {
    "type": ("vehicle_type", "str"),
    "sLineSeries": ("s_line_series", "str"),
    "engineeringModelYear": ("engineering_model_year", "int"),
    "truck": ("truck", "bool"),
    "saturn": ("saturn", "bool"),
    "isDeviated": ("is_deviated", "bool"),
    "jobCard": ("job_card", "str"),
    "isOpenCampaign": ("is_open_campaign", "bool"),
    "wmi": ("wmi", "str"),
    "vds": ("vds", "str"),
    "vis": ("vis", "str"),
    "sid": ("sid", "str"),
    "vinMake": ("vin_make", "str"),
    "vinLine": ("vin_line", "str"),
    "vinSeries": ("vin_series", "str"),
    "vinEngine": ("vin_engine", "str"),
    "vinCheckDigit": ("vin_check_digit", "str"),
    "vinModelYear": ("vin_model_year", "str"),
    "vehicleLink": ("vehicle_link", "int"),
    "clearDTCs": ("clear_dtcs", "bool"),
    "offBoardCheckRequired": ("off_board_check_required", "bool"),
    "modelDesignator": ("model_designator", "str"),
    "proceedSameVin": ("proceed_same_vin", "bool"),
    "eventLogId": ("event_log_id", "int"),
    "spsEventId": ("sps_event_id", "int"),
    "selectedControllerId": ("selected_controller_id", "int"),
    "logModule": ("log_module", "bool"),
    "logOnstar": ("log_onstar", "bool"),
    "isDifferentVin": ("is_different_vin", "bool"),
    "activeSchema": ("active_schema", "str"),
}
_JSON_FIELDS = {"vciNumbers": "vci", "copControllers": "cop", "deviceList": "device"}
_TABLE_FIELDS = {"supportedControllers", "asbuiltRpoCodes"}
_SEQUENCE_FIELDS = {
    "calibrationData",
    "moduleData",
    "cvnMap",
    "hasValidChainOfParts",
    "adapterType",
    "hasDependency",
}
_SCHEMA = """
CREATE TABLE IF NOT EXISTS vin (
    vin TEXT PRIMARY KEY,
    vehicle_type TEXT,
    s_line_series TEXT,
    engineering_model_year INTEGER,
    truck INTEGER,
    saturn INTEGER,
    is_deviated INTEGER,
    job_card TEXT,
    is_open_campaign INTEGER,
    wmi TEXT,
    vds TEXT,
    vis TEXT,
    sid TEXT,
    vin_make TEXT,
    vin_line TEXT,
    vin_series TEXT,
    vin_engine TEXT,
    vin_check_digit TEXT,
    vin_model_year TEXT,
    vehicle_link INTEGER,
    clear_dtcs INTEGER,
    off_board_check_required INTEGER,
    model_designator TEXT,
    proceed_same_vin INTEGER,
    event_log_id INTEGER,
    sps_event_id INTEGER,
    selected_controller_id INTEGER,
    log_module INTEGER,
    log_onstar INTEGER,
    is_different_vin INTEGER,
    active_schema TEXT,
    vci_json TEXT NOT NULL,
    cop_json TEXT NOT NULL,
    device_json TEXT NOT NULL,
    extras_json TEXT NOT NULL,
    adapter_type TEXT,
    has_dependency INTEGER,
    has_valid_chain INTEGER,
    sequence_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS controller (
    vin TEXT NOT NULL,
    position INTEGER NOT NULL,
    code TEXT,
    label TEXT,
    display_order INTEGER,
    PRIMARY KEY (vin, position)
);
CREATE TABLE IF NOT EXISTS function (
    vin TEXT NOT NULL,
    controller_position INTEGER NOT NULL,
    position INTEGER NOT NULL,
    label TEXT,
    display_order INTEGER,
    PRIMARY KEY (vin, controller_position, position)
);
CREATE TABLE IF NOT EXISTS method (
    vin TEXT NOT NULL,
    controller_position INTEGER NOT NULL,
    function_position INTEGER NOT NULL,
    position INTEGER NOT NULL,
    method_id INTEGER,
    description TEXT,
    block_same_cal INTEGER,
    method_type TEXT,
    current_selection_idx INTEGER,
    selected_codes_json TEXT NOT NULL,
    options_json TEXT NOT NULL,
    PRIMARY KEY (vin, controller_position, function_position, position)
);
CREATE TABLE IF NOT EXISTS supported_controller (
    vin TEXT NOT NULL,
    position INTEGER NOT NULL,
    controller_id INTEGER,
    display_name TEXT,
    document_json TEXT NOT NULL,
    PRIMARY KEY (vin, position)
);
CREATE TABLE IF NOT EXISTS calibration (
    vin TEXT NOT NULL,
    slot TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    part_number TEXT,
    flag TEXT,
    label TEXT,
    cvn TEXT,
    PRIMARY KEY (vin, slot, sequence)
);
CREATE TABLE IF NOT EXISTS module_slot (
    vin TEXT NOT NULL,
    position INTEGER NOT NULL,
    slot TEXT,
    label TEXT,
    PRIMARY KEY (vin, position)
);
CREATE TABLE IF NOT EXISTS rpo (
    vin TEXT NOT NULL,
    source TEXT NOT NULL,
    position INTEGER NOT NULL,
    code TEXT NOT NULL,
    PRIMARY KEY (vin, source, position)
);
"""
_INSERT_VIN = """
INSERT INTO vin (
    vin, vehicle_type, s_line_series, engineering_model_year, truck, saturn, is_deviated, job_card,
    is_open_campaign, wmi, vds, vis, sid, vin_make, vin_line, vin_series, vin_engine, vin_check_digit,
    vin_model_year, vehicle_link, clear_dtcs, off_board_check_required, model_designator, proceed_same_vin,
    event_log_id, sps_event_id, selected_controller_id, log_module, log_onstar, is_different_vin, active_schema,
    vci_json, cop_json, device_json, extras_json, adapter_type, has_dependency, has_valid_chain, sequence_json,
    fetched_at
) VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?
)
"""


class SpsInfoError(ValueError):
    """The catalog document or its database path cannot be stored."""


@dataclass(frozen=True, slots=True)
class SporefForm:
    """The handoff form. ``repr`` names the fields and does not include their values."""

    action: str
    fields: tuple[tuple[str, str], ...]

    def __repr__(self) -> str:
        names = ", ".join(name for name, _value in self.fields)
        return f"SporefForm(action={self.action!r}, fields=[{names}])"


@dataclass(frozen=True, slots=True)
class VinCatalog:
    """How many rows one VIN occupies, and where they were written."""

    path: Path
    controllers: int
    functions: int
    methods: int
    supported_controllers: int
    calibrations: int
    module_slots: int
    rpos: int


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[tuple[str, list[tuple[str, str]]]] = []
        self._fields: list[tuple[str, str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = {key: value or "" for key, value in attrs}
        if tag == "form":
            self._fields = []
            self.forms.append((found.get("action", ""), self._fields))
            return
        if tag == "input" and self._fields is not None and found.get("name"):
            self._fields.append((found["name"], found.get("value", "")))


def check_vin(vin: str) -> str:
    """A VIN is 17 characters. I, O and Q are not used."""
    if not isinstance(vin, str) or _VIN.fullmatch(vin) is None:
        raise SpsInfoError("a VIN is 17 characters and does not use I, O or Q")
    return vin


def parse_sporef_form(page: str | bytes) -> SporefForm:
    """Read the SPOREF form action and its fields. The values stay on the form and are not logged."""
    text = page.decode("utf-8", "replace") if isinstance(page, bytes) else page
    parser = _FormParser()
    parser.feed(text)
    parser.close()
    chosen: tuple[str, list[tuple[str, str]]] | None = None
    for action, fields in parser.forms:
        if "sporef" in action:
            chosen = (action, fields)
            break
    if chosen is None:
        for action, fields in parser.forms:
            if action:
                chosen = (action, fields)
                break
    if chosen is None or not chosen[0].startswith("https://") or any(char in chosen[0] for char in " \r\n"):
        raise SpsInfoError("SPS Info did not return a form")
    return SporefForm(chosen[0], tuple(chosen[1]))


def sequence_request(fixture: Mapping[str, object]) -> dict[str, object]:
    """The fixture, with the selection the viewer writes before it asks for the sequence.

    The captured call uses the first method described as Normal. An unselected fixture is refused by the server.
    """
    try:
        copied = json.loads(json.dumps(fixture))
    except (TypeError, ValueError) as exc:
        raise SpsInfoError("the fixture is not a document") from exc
    if not isinstance(copied, dict):
        raise SpsInfoError("the fixture is not a document")
    selection = _normal_selection(copied)
    if selection is None:
        return copied
    controller, function, method = selection
    copied["displayName"] = {
        "controllerCode": controller.get("controllerCode"),
        "controllerLabel": controller.get("controllerLabel"),
        "displayOrder": controller.get("displayOrder"),
    }
    copied["controllerFunction"] = {
        "displayOrder": function.get("displayOrder"),
        "functionLabel": function.get("functionLabel"),
    }
    copied["programmingMethod"] = {
        "methodId": method.get("methodId"),
        "description": method.get("description"),
        "blockSameCal": method.get("blockSameCal"),
    }
    return copied


def _method_meta(node: object) -> dict[str, object] | None:
    if isinstance(node, dict) and all(isinstance(key, str) for key in node):
        return node
    if isinstance(node, list) and node and isinstance(node[0], dict) and all(isinstance(key, str) for key in node[0]):
        return node[0]
    return None


def _normal_selection(
    document: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]] | None:
    tree_root = document.get("controllerReferenceTree")
    if not isinstance(tree_root, dict):
        return None
    tree = tree_root.get("referenceTree")
    if not isinstance(tree, list):
        return None
    first: tuple[dict[str, object], dict[str, object], dict[str, object]] | None = None
    for node in tree:
        if not isinstance(node, list) or len(node) < 2 or not isinstance(node[1], list):
            continue
        controller = node[0] if isinstance(node[0], dict) else None
        if not isinstance(controller, dict):
            continue
        for function_node in node[1]:
            if not isinstance(function_node, list) or len(function_node) < 2 or not isinstance(function_node[1], list):
                continue
            function = function_node[0] if isinstance(function_node[0], dict) else None
            if not isinstance(function, dict):
                continue
            for method_node in function_node[1]:
                method = _method_meta(method_node)
                if method is None:
                    continue
                chosen = (controller, function, method)
                if first is None:
                    first = chosen
                if method.get("description") == "Normal":
                    return chosen
    return first


def save_vin(path: Path, vin: str, fixture: Mapping[str, object], sequence: Mapping[str, object]) -> VinCatalog:
    """Write one VIN. A later call replaces that VIN in a single transaction and leaves other VINs in place."""
    checked = check_vin(vin)
    destination = _outside(path)
    vehicle = _require_object(fixture, "the fixture")
    programming = _require_object(sequence, "the programming sequence")
    _reject_token(vehicle)
    _reject_token(programming)
    rows = _catalog_rows(checked, vehicle, programming)
    destination.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(destination)
    try:
        connection.executescript(_SCHEMA)
        with connection:
            _replace(connection, checked, rows)
    finally:
        connection.close()
    return VinCatalog(
        destination,
        len(rows.controllers),
        len(rows.functions),
        len(rows.methods),
        len(rows.supported),
        len(rows.calibrations),
        len(rows.modules),
        len(rows.rpos),
    )


@dataclass(frozen=True, slots=True)
class _Rows:
    vin: tuple[object, ...]
    controllers: list[tuple[object, ...]]
    functions: list[tuple[object, ...]]
    methods: list[tuple[object, ...]]
    supported: list[tuple[object, ...]]
    calibrations: list[tuple[object, ...]]
    modules: list[tuple[object, ...]]
    rpos: list[tuple[object, ...]]


def _outside(path: Path) -> Path:
    try:
        return outside_repository(path)
    except ConfigError as exc:
        raise SpsInfoError("the catalog database must be an absolute path outside the repository") from exc


def _require_object(value: Mapping[str, object], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise SpsInfoError(f"{label} is not a document")
    return dict(value)


def _reject_token(value: object) -> None:
    if isinstance(value, str):
        if _TOKEN.search(value) is not None:
            raise SpsInfoError("refusing to store a document that contains a token")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                _reject_token(key)
            _reject_token(item)
        return
    if isinstance(value, list):
        for item in value:
            _reject_token(item)


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _whole(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _flag(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    return None


def _bind(value: object, kind: _Kind) -> object:
    if kind == "str":
        return _text(value)
    if kind == "int":
        return _whole(value)
    return _flag(value)


def _object(value: object) -> dict[str, object] | None:
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return dict(value)
    return None


def _catalog_rows(vin: str, fixture: dict[str, object], sequence: dict[str, object]) -> _Rows:
    tree_root = _object(fixture.get("controllerReferenceTree"))
    spsvin = _object(fixture.get("spsvin"))
    if tree_root is None or not isinstance(tree_root.get("referenceTree"), list) or spsvin is None:
        raise SpsInfoError("the fixture has no controller tree")
    reference = tree_root["referenceTree"]
    if not isinstance(reference, list):
        raise SpsInfoError("the fixture has no controller tree")
    controllers, functions, methods, tree_extra = _reference_rows(vin, reference)
    supported, supported_extra = _supported_rows(vin, spsvin.get("supportedControllers"))
    calibrations, modules, sequence_columns, sequence_extra = _sequence_rows(vin, sequence)
    rpos, rpo_extra = _rpo_rows(vin, spsvin.get("asbuiltRpoCodes"), fixture.get("rpoCodes"))
    extras = _extras(vin, fixture, spsvin, tree_root, tree_extra, supported_extra, rpo_extra)
    blobs = _blobs(spsvin, extras)
    return _Rows(
        _vin_row(vin, spsvin, blobs, extras, sequence_columns, sequence_extra),
        controllers,
        functions,
        methods,
        supported,
        calibrations,
        modules,
        rpos,
    )


def _reference_rows(
    vin: str, tree: list[object]
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]], list[tuple[object, ...]], list[object]]:
    controllers: list[tuple[object, ...]] = []
    functions: list[tuple[object, ...]] = []
    methods: list[tuple[object, ...]] = []
    extra: list[object] = []
    for position, node in enumerate(tree):
        parsed = _controller(vin, position, node)
        if parsed is None:
            extra.append(node)
            continue
        controller, function_rows, method_rows, leftover = parsed
        controllers.append(controller)
        functions.extend(function_rows)
        methods.extend(method_rows)
        if leftover:
            extra.append({"position": position, "fields": leftover})
    return controllers, functions, methods, extra


def _controller(
    vin: str, position: int, node: object
) -> tuple[tuple[object, ...], list[tuple[object, ...]], list[tuple[object, ...]], list[object]] | None:
    if not isinstance(node, list) or len(node) < 2 or not isinstance(node[1], list):
        return None
    meta = _object(node[0])
    if meta is None:
        return None
    functions: list[tuple[object, ...]] = []
    methods: list[tuple[object, ...]] = []
    leftover: list[object] = [_unknown(meta, {"controllerCode", "controllerLabel", "displayOrder"})]
    if len(node) > 2:
        leftover.append({"rest": node[2:]})
    for function_position, item in enumerate(node[1]):
        parsed = _function(vin, position, function_position, item)
        if parsed is None:
            leftover.append(item)
            continue
        function_row, method_rows, function_extra = parsed
        functions.append(function_row)
        methods.extend(method_rows)
        leftover.extend(function_extra)
    leftover = [item for item in leftover if item != {}]
    return (
        (
            vin,
            position,
            _text(meta.get("controllerCode")),
            _text(meta.get("controllerLabel")),
            _whole(meta.get("displayOrder")),
        ),
        functions,
        methods,
        leftover,
    )


def _function(
    vin: str, controller_position: int, position: int, node: object
) -> tuple[tuple[object, ...], list[tuple[object, ...]], list[object]] | None:
    if not isinstance(node, list) or len(node) < 2 or not isinstance(node[1], list):
        return None
    meta = _object(node[0])
    if meta is None:
        return None
    methods: list[tuple[object, ...]] = []
    leftover: list[object] = [_unknown(meta, {"displayOrder", "functionLabel"})]
    if len(node) > 2:
        leftover.append({"rest": node[2:]})
    for method_position, item in enumerate(node[1]):
        parsed = _method(vin, controller_position, position, method_position, item)
        if parsed is None:
            leftover.append(item)
            continue
        method_row, method_extra = parsed
        methods.append(method_row)
        if method_extra:
            leftover.append(method_extra)
    return (
        (vin, controller_position, position, _text(meta.get("functionLabel")), _whole(meta.get("displayOrder"))),
        methods,
        [item for item in leftover if item != {}],
    )


def _method(
    vin: str, controller_position: int, function_position: int, position: int, node: object
) -> tuple[tuple[object, ...], object] | None:
    options: object
    rest: object
    if isinstance(node, dict):
        meta, options, rest = node, {}, None
    elif isinstance(node, list) and node and isinstance(node[0], dict):
        meta = node[0]
        options = node[1] if len(node) > 1 else {}
        rest = node[2:] if len(node) > 2 else None
    else:
        return None
    if not all(isinstance(key, str) for key in meta):
        return None
    option_document = _object(options) or {}
    stored: object = options
    unknown = _unknown(meta, {"methodId", "description", "blockSameCal"})
    if unknown or rest is not None:
        stored = {"options": options, "method": unknown, "rest": rest}
    selected = option_document.get("selectedCodes")
    selected_codes = selected if isinstance(selected, list) else []
    return (
        (
            vin,
            controller_position,
            function_position,
            position,
            _whole(meta.get("methodId")),
            _text(meta.get("description")),
            _flag(meta.get("blockSameCal")),
            _text(option_document.get("type")),
            _whole(option_document.get("currentSelectionIdx")),
            _dump(selected_codes),
            _dump(stored),
        ),
        unknown,
    )


def _unknown(meta: Mapping[str, object], known: set[str]) -> dict[str, object]:
    return {key: value for key, value in meta.items() if key not in known}


def _supported_rows(vin: str, raw: object) -> tuple[list[tuple[object, ...]], object]:
    if not isinstance(raw, list):
        return [], raw
    rows: list[tuple[object, ...]] = []
    for position, item in enumerate(raw):
        document = _object(item)
        if document is None:
            return [], raw
        rows.append((vin, position, _whole(document.get("controllerId")), _display_name(document), _dump(document)))
    return rows, None


def _display_name(document: Mapping[str, object]) -> str:
    raw = document.get("displayName")
    if isinstance(raw, str):
        return raw
    named = _object(raw)
    if named is None:
        return ""
    label = named.get("controllerLabel")
    if isinstance(label, str) and label:
        return label
    code = named.get("controllerCode")
    return code if isinstance(code, str) else ""


def _sequence_rows(
    vin: str, sequence: dict[str, object]
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]], dict[str, object], dict[str, object]]:
    cvn_raw = sequence.get("cvnMap")
    cvn_map = cvn_raw if isinstance(cvn_raw, dict) else {}
    calibrations, bad_calibrations = _calibrations(vin, sequence.get("calibrationData"), cvn_map)
    modules, bad_modules = _modules(vin, sequence.get("moduleData"))
    columns: dict[str, object] = {}
    adapter = sequence.get("adapterType")
    if isinstance(adapter, str):
        columns["adapter_type"] = adapter
    dependency = _flag(sequence.get("hasDependency"))
    if dependency is not None:
        columns["has_dependency"] = dependency
    chain = _flag(sequence.get("hasValidChainOfParts"))
    if chain is not None:
        columns["has_valid_chain"] = chain
    extra = {key: value for key, value in sequence.items() if key not in _SEQUENCE_FIELDS}
    if not isinstance(cvn_raw, dict) and "cvnMap" in sequence:
        extra["cvnMap"] = cvn_raw
    if bad_calibrations:
        extra["unparsedCalibrations"] = bad_calibrations
    if bad_modules:
        extra["unparsedModules"] = bad_modules
    return calibrations, modules, columns, extra


def _calibrations(
    vin: str, raw: object, cvn_map: Mapping[object, object]
) -> tuple[list[tuple[object, ...]], list[object]]:
    if raw is None:
        return [], []
    if not isinstance(raw, dict):
        return [], [raw]
    rows: list[tuple[object, ...]] = []
    bad: list[object] = []
    for slot, items in raw.items():
        if not isinstance(slot, str) or not isinstance(items, list):
            bad.append({str(slot): items})
            continue
        for index, item in enumerate(items):
            if isinstance(item, list) and len(item) >= 3 and all(isinstance(part, str) for part in item[:3]):
                cvn = cvn_map.get(item[0])
                rows.append((vin, slot, index, item[0], item[1], item[2], cvn if isinstance(cvn, str) else None))
                if len(item) > 3:
                    bad.append(item[3:])
                continue
            bad.append(item)
    return rows, bad


def _modules(vin: str, raw: object) -> tuple[list[tuple[object, ...]], list[object]]:
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [raw]
    rows: list[tuple[object, ...]] = []
    bad: list[object] = []
    for position, item in enumerate(raw):
        if isinstance(item, list) and len(item) >= 2 and isinstance(item[0], str) and isinstance(item[1], str):
            rows.append((vin, position, item[0], item[1]))
            continue
        bad.append(item)
    return rows, bad


def _rpo_rows(vin: str, asbuilt: object, selected: object) -> tuple[list[tuple[object, ...]], dict[str, object]]:
    rows: list[tuple[object, ...]] = []
    extra: dict[str, object] = {}
    for source, raw in (("asbuilt", asbuilt), ("selected", selected)):
        codes = _codes(raw)
        if codes is None:
            if raw is not None:
                extra[source] = raw
            continue
        rows.extend((vin, source, position, code) for position, code in enumerate(codes) if code)
    return rows, extra


def _codes(raw: object) -> list[str] | None:
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        return None
    return list(raw)


def _extras(
    vin: str,
    fixture: Mapping[str, object],
    spsvin: Mapping[str, object],
    tree_root: Mapping[str, object],
    tree_extra: list[object],
    supported_extra: object,
    rpo_extra: Mapping[str, object],
) -> dict[str, object]:
    consumed = set(_SCALARS) | set(_JSON_FIELDS) | _TABLE_FIELDS | {"vin"}
    extras = {key: value for key, value in spsvin.items() if key not in consumed}
    recorded = spsvin.get("vin")
    if "vin" in spsvin and recorded != vin:
        extras["vin"] = recorded
    root = {
        key: value for key, value in fixture.items() if key not in {"controllerReferenceTree", "spsvin", "rpoCodes"}
    }
    if root:
        extras["fixture"] = root
    tree_fields = {key: value for key, value in tree_root.items() if key != "referenceTree"}
    if tree_fields:
        extras["controllerReferenceTree"] = tree_fields
    if tree_extra:
        extras["referenceFields"] = tree_extra
    if supported_extra is not None:
        extras["supportedControllers"] = supported_extra
    if "asbuilt" in rpo_extra:
        extras["asbuiltRpoCodes"] = rpo_extra["asbuilt"]
    if "selected" in rpo_extra:
        fixture_extra = extras.get("fixture")
        selected = rpo_extra["selected"]
        if isinstance(fixture_extra, dict):
            fixture_extra["rpoCodes"] = selected
        else:
            extras["fixture"] = {"rpoCodes": selected}
    return extras


def _blobs(spsvin: Mapping[str, object], extras: dict[str, object]) -> dict[str, object]:
    vci = spsvin.get("vciNumbers")
    cop = spsvin.get("copControllers")
    device = spsvin.get("deviceList")
    blobs: dict[str, object] = {"vci": {}, "cop": {}, "device": []}
    if isinstance(vci, dict):
        blobs["vci"] = vci
    elif "vciNumbers" in spsvin:
        extras["vciNumbers"] = vci
    if isinstance(cop, dict):
        blobs["cop"] = cop
    elif "copControllers" in spsvin:
        extras["copControllers"] = cop
    if isinstance(device, list):
        blobs["device"] = device
    elif "deviceList" in spsvin:
        extras["deviceList"] = device
    return blobs


def _vin_row(
    vin: str,
    spsvin: Mapping[str, object],
    blobs: Mapping[str, object],
    extras: Mapping[str, object],
    sequence_columns: Mapping[str, object],
    sequence_extra: Mapping[str, object],
) -> tuple[object, ...]:
    columns: dict[str, object] = {}
    for key, (column, kind) in _SCALARS.items():
        if key not in spsvin:
            continue
        bound = _bind(spsvin[key], kind)
        if bound is None and spsvin[key] is not None:
            continue
        columns[column] = bound
    mismatched = [
        key
        for key, (column, _kind) in _SCALARS.items()
        if key in spsvin and column not in columns and spsvin[key] is not None
    ]
    if mismatched:
        moved = dict(extras)
        for key in mismatched:
            moved[key] = spsvin[key]
        extras = moved
    fetched_at = datetime.now(UTC).isoformat()
    return (
        vin,
        columns.get("vehicle_type"),
        columns.get("s_line_series"),
        columns.get("engineering_model_year"),
        columns.get("truck"),
        columns.get("saturn"),
        columns.get("is_deviated"),
        columns.get("job_card"),
        columns.get("is_open_campaign"),
        columns.get("wmi"),
        columns.get("vds"),
        columns.get("vis"),
        columns.get("sid"),
        columns.get("vin_make"),
        columns.get("vin_line"),
        columns.get("vin_series"),
        columns.get("vin_engine"),
        columns.get("vin_check_digit"),
        columns.get("vin_model_year"),
        columns.get("vehicle_link"),
        columns.get("clear_dtcs"),
        columns.get("off_board_check_required"),
        columns.get("model_designator"),
        columns.get("proceed_same_vin"),
        columns.get("event_log_id"),
        columns.get("sps_event_id"),
        columns.get("selected_controller_id"),
        columns.get("log_module"),
        columns.get("log_onstar"),
        columns.get("is_different_vin"),
        columns.get("active_schema"),
        _dump(blobs["vci"]),
        _dump(blobs["cop"]),
        _dump(blobs["device"]),
        _dump(dict(extras)),
        sequence_columns.get("adapter_type"),
        sequence_columns.get("has_dependency"),
        sequence_columns.get("has_valid_chain"),
        _dump(dict(sequence_extra)),
        fetched_at,
    )


def _replace(connection: sqlite3.Connection, vin: str, rows: _Rows) -> None:
    for statement in (
        "DELETE FROM calibration WHERE vin = ?",
        "DELETE FROM module_slot WHERE vin = ?",
        "DELETE FROM rpo WHERE vin = ?",
        "DELETE FROM method WHERE vin = ?",
        "DELETE FROM function WHERE vin = ?",
        "DELETE FROM controller WHERE vin = ?",
        "DELETE FROM supported_controller WHERE vin = ?",
        "DELETE FROM vin WHERE vin = ?",
    ):
        connection.execute(statement, (vin,))
    connection.execute(_INSERT_VIN, rows.vin)
    connection.executemany(
        "INSERT INTO controller (vin, position, code, label, display_order) VALUES (?, ?, ?, ?, ?)",
        rows.controllers,
    )
    connection.executemany(
        "INSERT INTO function (vin, controller_position, position, label, display_order) VALUES (?, ?, ?, ?, ?)",
        rows.functions,
    )
    connection.executemany(
        """
        INSERT INTO method (
            vin, controller_position, function_position, position, method_id, description, block_same_cal,
            method_type, current_selection_idx, selected_codes_json, options_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows.methods,
    )
    connection.executemany(
        """
        INSERT INTO supported_controller (vin, position, controller_id, display_name, document_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows.supported,
    )
    connection.executemany(
        """
        INSERT INTO calibration (vin, slot, sequence, part_number, flag, label, cvn)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows.calibrations,
    )
    connection.executemany(
        "INSERT INTO module_slot (vin, position, slot, label) VALUES (?, ?, ?, ?)",
        rows.modules,
    )
    connection.executemany(
        "INSERT INTO rpo (vin, source, position, code) VALUES (?, ?, ?, ?)",
        rows.rpos,
    )
