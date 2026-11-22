"""Turn a captured voltkit clone-profile read into a VIT1 programming-data request.

``voltkit profile ... --clone`` writes a module read as ``ecu``/``did``/``lid``
text. This command maps one controller's saved read onto the inputs
``spskit.vit1`` expects and returns the VIT1 control-module block, or the whole
``getProgrammingData`` body when a request template carries the catalog
documents.

It is an offline transform: a captured file and a VIN in, a request body out. It
does not import voltkit, open a socket, post to TDS, read a dongle, or program a
vehicle. The deliberate gaps stay: K16 and K73 request methods 520 and 566 have
no saved-read rule, so ``read_shape`` refuses them; method 601 is K73's rule.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from spskit.spsinfo import SpsInfoError
from spskit.vit1 import (
    ReadShape,
    Vit1Error,
    build_vit1,
    module_attributes,
    programming_data_request,
    read_codes,
    read_shape,
    vci_programming_data_request,
)

_PRINTABLE = range(0x20, 0x7F)
_PROGRAMMING_METHODS = frozenset({1, 128})
_VCI_METHODS = frozenset({2, 256})


class HandoffError(ValueError):
    """The captured read cannot be mapped onto a saved-read rule."""


@dataclass(slots=True)
class CloneBlock:
    """One ``ecu`` block of a clone profile: its ``$1A`` lids and ``$22`` dids."""

    ecu: str
    lids: dict[str, bytes] = field(default_factory=dict)
    dids: dict[str, bytes] = field(default_factory=dict)


def parse_clone_profile(text: str) -> dict[str, CloneBlock]:
    """Group the ``did``/``lid`` lines of a clone profile under their ``ecu`` block.

    Comment lines, the ``s3`` timing line, and reads printed before any ``ecu``
    line (the clone comments those out) are skipped. Each ``lid``/``did`` value
    is the hex after the identifier, which is the data the module answered after
    the service byte and the identifier.
    """
    blocks: dict[str, CloneBlock] = {}
    current: CloneBlock | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        tag = parts[0]
        if tag == "ecu":
            current = _begin_block(parts, blocks)
            continue
        if tag not in {"lid", "did"}:
            continue
        if current is None:
            continue
        ident, value = _read_line(parts)
        table = current.lids if tag == "lid" else current.dids
        if ident in table and table[ident] != value:
            raise HandoffError(f"the {current.ecu} read gives {tag} {ident} two different values")
        table[ident] = value
    return blocks


def attributes_for(
    block: CloneBlock,
    shape: ReadShape,
    *,
    vin: str,
    ssecuhn: str | None = None,
    cvn: str | None = None,
    partnums: Sequence[str] = (),
) -> tuple[tuple[str, str], ...]:
    """Pair one controller's captured read into the attributes ``build_vit1`` walks."""
    parts = {did: _part_payload(block, did) for did in shape.part_dids}
    hardware = _hardware(block, shape, ssecuhn)
    cvn_value, partnum_values = _cvn_for(shape, cvn, partnums)
    return module_attributes(
        shape.code,
        vin=vin,
        parts=parts,
        hardware=hardware,
        cvn=cvn_value,
        partnums=partnum_values,
    )


def vit1_from_read(
    text: str,
    *,
    code: str,
    vin: str = "",
    ecu: str | None = None,
    ssecuhn: str | None = None,
    cvn: str | None = None,
    partnums: Sequence[str] = (),
) -> dict[str, object]:
    """The VIT1 control-module block a captured read becomes, with its attributes.

    The result is self-describing: the controller code, its device and request
    method, the resolved VIN, the attribute pairs, and the ``vit1`` document
    ``build_vit1`` produces. That ``vit1`` is what ``programming_data_request``
    attaches to the controller.
    """
    shape = read_shape(code)
    block = _select_block(parse_clone_profile(text), ecu)
    resolved_vin = _vin_for(shape, vin)
    attributes = attributes_for(block, shape, vin=resolved_vin, ssecuhn=ssecuhn, cvn=cvn, partnums=partnums)
    envelope: dict[str, object] = {
        "code": shape.code,
        "deviceId": shape.device_id,
        "requestMethod": shape.request_method,
        "ecu": block.ecu,
    }
    if shape.reads_vin:
        envelope["vin"] = resolved_vin
    envelope["attributes"] = [list(pair) for pair in attributes]
    envelope["vit1"] = build_vit1(attributes)
    return envelope


def request_from_read(
    text: str,
    template: object,
    *,
    code: str,
    vin: str = "",
    ecu: str | None = None,
    ssecuhn: str | None = None,
    cvn: str | None = None,
    partnums: Sequence[str] = (),
) -> dict[str, object]:
    """The whole getProgrammingData body for a captured read and a catalog template.

    ``template`` carries the documents the catalog supplies: ``clientState``,
    ``spsVin``, ``method``, ``controller``, and (for method 1 or 128)
    ``optionComposite``. The captured read is attached as the controller's
    ``vit1``. Method 2 and 256 take the VCI body and copy the template's step
    lists. This function does not invent a catalog document and does not post.
    """
    shape = read_shape(code)
    block = _select_block(parse_clone_profile(text), ecu)
    resolved_vin = _vin_for(shape, vin)
    attributes = attributes_for(block, shape, vin=resolved_vin, ssecuhn=ssecuhn, cvn=cvn, partnums=partnums)
    if not isinstance(template, Mapping):
        raise HandoffError("the request template is not an object")
    docs = _template_documents(template)
    method_id = docs["method"].get("methodId")
    if method_id in _PROGRAMMING_METHODS:
        return programming_data_request(
            client_state=docs["clientState"],
            sps_vin=docs["spsVin"],
            method=docs["method"],
            controller=docs["controller"],
            option_composite=docs["optionComposite"],
            attributes=attributes,
        )
    if method_id in _VCI_METHODS:
        return vci_programming_data_request(
            client_state=docs["clientState"],
            sps_vin=docs["spsVin"],
            method=docs["method"],
            controller=docs["controller"],
            attributes=attributes,
            function_steps=_step_list(template.get("functionSteps")),
            vci_steps=_step_list(template.get("vciVOList")),
        )
    raise HandoffError("the template method is not 1, 2, 128, or 256")


def _begin_block(parts: list[str], blocks: dict[str, CloneBlock]) -> CloneBlock:
    if len(parts) < 2:
        raise HandoffError("an ecu line names no controller")
    name = parts[1]
    if name in blocks:
        raise HandoffError(f"the capture names ecu {name} twice")
    block = CloneBlock(name)
    blocks[name] = block
    return block


def _read_line(parts: list[str]) -> tuple[str, bytes]:
    if len(parts) < 2:
        raise HandoffError(f"a {parts[0]} line names no identifier")
    ident = parts[1].upper()
    token = parts[2] if len(parts) >= 3 and not parts[2].startswith("#") else ""
    try:
        return ident, bytes.fromhex(token)
    except ValueError as exc:
        raise HandoffError(f"the {parts[0]} {ident} line is not hex: {token!r}") from exc


def _select_block(blocks: Mapping[str, CloneBlock], ecu: str | None) -> CloneBlock:
    if not blocks:
        raise HandoffError("the capture has no ecu block with a module read")
    if ecu is not None:
        block = blocks.get(ecu)
        if block is None:
            raise HandoffError(f"the capture has no ecu {ecu}; it has {', '.join(blocks)}")
        return block
    if len(blocks) > 1:
        raise HandoffError(f"the capture has more than one ecu; choose one with --ecu from {', '.join(blocks)}")
    return next(iter(blocks.values()))


def _part_payload(block: CloneBlock, did: str) -> bytes:
    value = block.lids.get(did.upper())
    if value is None:
        raise HandoffError(f"the {block.ecu} read has no lid {did} for a part number")
    return bytes([int(did, 16)]) + value


def _hardware(block: CloneBlock, shape: ReadShape, ssecuhn: str | None) -> bytes | str | None:
    if shape.hardware_did is None:
        if ssecuhn is not None:
            raise HandoffError(f"{shape.code} does not read a hardware id")
        return None
    if shape.hardware_decimal:
        if ssecuhn is not None:
            raise HandoffError(f"{shape.code} reads a numeric hardware id, not a string; drop --ssecuhn")
        value = block.lids.get(shape.hardware_did.upper())
        if value is None:
            raise HandoffError(f"the {block.ecu} read has no lid {shape.hardware_did} for the hardware id")
        return bytes([int(shape.hardware_did, 16)]) + value
    if ssecuhn is not None:
        return ssecuhn
    value = block.lids.get(shape.hardware_did.upper())
    if value is None:
        raise HandoffError(f"the {block.ecu} read has no lid {shape.hardware_did} for the hardware id; pass --ssecuhn")
    return _ssecuhn_text(value)


def _ssecuhn_text(value: bytes) -> str:
    """The hardware string for a length-0 read: the printable ASCII, else the hex.

    K17's hardware length is 0, so ``vit1`` keeps ``ssecuhn`` as the string the
    read carried. The capture records the ``$CC`` bytes; a printable run is that
    string, and anything else is rendered as hex so the value is not lost.
    """
    if value and all(byte in _PRINTABLE for byte in value):
        return value.decode("ascii")
    return value.hex().upper()


def _vin_for(shape: ReadShape, vin: str) -> str:
    if shape.reads_vin:
        if not vin:
            raise HandoffError(f"{shape.code} reads a VIN; pass --vin")
        return vin
    if vin:
        raise HandoffError(f"{shape.code} does not read a VIN; drop --vin")
    return ""


def _cvn_for(shape: ReadShape, cvn: str | None, partnums: Sequence[str]) -> tuple[str | None, tuple[str, ...]]:
    if shape.reads_cvn:
        return (cvn if cvn is not None else "0"), tuple(partnums)
    if cvn is not None or partnums:
        raise HandoffError(f"{shape.code} does not carry a CVN")
    return None, ()


def _template_documents(template: Mapping[str, object]) -> dict[str, dict[str, object]]:
    method = template.get("method")
    if not isinstance(method, Mapping):
        raise HandoffError("the request template has no method object")
    required = ["clientState", "spsVin", "controller"]
    if method.get("methodId") in _PROGRAMMING_METHODS:
        required.append("optionComposite")
    out: dict[str, dict[str, object]] = {"method": dict(method)}
    for key in required:
        value = template.get(key)
        if not isinstance(value, Mapping):
            raise HandoffError(f"the request template has no {key} object")
        out[key] = dict(value)
    return out


def _step_list(value: object) -> list[Mapping[str, object]] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise HandoffError("a template step list is a list of objects")
    steps: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise HandoffError("a template step is not an object")
        steps.append(item)
    return steps


def _read_text(path: str) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")


def run(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="spskit-vit1",
        description="Attach a captured module read as the VIT1 programming-data block. Offline only.",
    )
    parser.add_argument("--read", required=True, help="a voltkit profile --clone file")
    parser.add_argument("--code", required=True, help=f"controller code, one of: {', '.join(read_codes())}")
    parser.add_argument("--vin", default="", help="17-character VIN (required when the controller reads one)")
    parser.add_argument("--ecu", default=None, help="the ecu block to read when the capture has more than one")
    parser.add_argument("--ssecuhn", default=None, help="override the hardware id string (length-0 reads, e.g. K17)")
    parser.add_argument("--cvn", default=None, choices=["0", "1"], help="cvn_in_vit1 for a CVN controller")
    parser.add_argument("--partnum", action="append", default=[], help="a partnum for cvn_in_vit1 1 (repeatable)")
    parser.add_argument(
        "--template", default=None, help="a getProgrammingData template that carries the catalog documents"
    )
    parser.add_argument("--out", default=None, help="write the JSON here instead of stdout")
    args = parser.parse_args(list(argv))
    try:
        text = _read_text(args.read)
        partnums = tuple(args.partnum)
        if args.template is not None:
            template = json.loads(_read_text(args.template))
            body = request_from_read(
                text,
                template,
                code=args.code,
                vin=args.vin,
                ecu=args.ecu,
                ssecuhn=args.ssecuhn,
                cvn=args.cvn,
                partnums=partnums,
            )
        else:
            body = vit1_from_read(
                text,
                code=args.code,
                vin=args.vin,
                ecu=args.ecu,
                ssecuhn=args.ssecuhn,
                cvn=args.cvn,
                partnums=partnums,
            )
    except (HandoffError, Vit1Error, SpsInfoError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    rendered = json.dumps(body, indent=2)
    if args.out is None:
        print(rendered)
    else:
        pathlib.Path(args.out).write_text(rendered + "\n", encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
