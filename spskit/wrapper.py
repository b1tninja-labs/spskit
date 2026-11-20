"""The GM wrapper contract spsvcs asks for by name.

This module does not load a library, open a registry key, or speak SAE J2534.
``CSpsVcsImpl::Init`` reads ``SOFTWARE\\GM\\J2534Wrapper`` value ``FunctionLibrary``
and resolves the four exports below on that file. The file was not on this machine.
``spsvcs.dll`` also exports the same four names as its own API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WRAPPER_KEY = "SOFTWARE\\GM\\J2534Wrapper"
WRAPPER_VALUE = "FunctionLibrary"
EXPORTS = (
    "GetDefaultDeviceInfo",
    "ClearDefaultDeviceInfo",
    "GetConnectedDeviceInfo",
    "GetDeviceStatus",
)

_WRAPPER = re.compile(r"^%([^%]*)%J2534,(.*)$")
_LEGACY = re.compile(r"^COM(\d+),(\d+)$")
_AUTO = re.compile(r"^AUTO(?:,(\d+))?$")


class WrapperError(ValueError):
    """The init string is not one of the forms Init logs."""


@dataclass(frozen=True, slots=True)
class InitString:
    """One connect string ``J2534Tool.init`` can hand to ``SPSTool.initialize``."""

    form: str
    version: str = ""
    name: str = ""


def parse_init(text: str) -> InitString:
    """Classify the connect string.

    An empty string is the default-device path. ``%04.04%J2534,<name>`` is the
    form Java builds when no VCI name is set. ``AUTO`` and ``COM<port>,<baud>``
    are the two forms the native Init special-cases. Any other text is a
    connection name Techline already selected.
    """
    if text == "":
        return InitString("default")
    match = _WRAPPER.fullmatch(text)
    if match is not None:
        version, name = match.group(1), match.group(2)
        if version == "" or name == "":
            raise WrapperError("the wrapper form names a version and a tool")
        return InitString("wrapper", version, name)
    match = _AUTO.fullmatch(text)
    if match is not None:
        return InitString("auto", name=match.group(1) or "")
    if _LEGACY.fullmatch(text) is not None:
        return InitString("legacy", name=text)
    return InitString("connection", name=text)
