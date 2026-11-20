from __future__ import annotations

import pytest

from spskit.vit1 import Vit1Error, format0_decimal
from spskit.wrapper import EXPORTS, WRAPPER_KEY, InitString, WrapperError, parse_init


def test_the_percent_form_names_the_version_and_the_tool():
    parsed = parse_init("%04.04%J2534,VXDIAG")
    assert parsed == InitString("wrapper", "04.04", "VXDIAG")
    assert WRAPPER_KEY == "SOFTWARE\\GM\\J2534Wrapper"
    assert EXPORTS == (
        "GetDefaultDeviceInfo",
        "ClearDefaultDeviceInfo",
        "GetConnectedDeviceInfo",
        "GetDeviceStatus",
    )


def test_an_empty_string_asks_for_the_default_device():
    assert parse_init("") == InitString("default")


def test_a_selected_connection_name_is_kept():
    assert parse_init("Bosch - MDI") == InitString("connection", name="Bosch - MDI")


def test_auto_and_the_old_com_form_are_not_the_wrapper_form():
    assert parse_init("AUTO") == InitString("auto")
    assert parse_init("AUTO,38400") == InitString("auto", name="38400")
    assert parse_init("COM4,115200") == InitString("legacy", name="COM4,115200")


def test_a_wrapper_form_without_a_name_is_refused():
    with pytest.raises(WrapperError, match="version and a tool"):
        parse_init("%04.04%J2534,")


def test_a_positive_gmlan_response_is_the_format0_decimal():
    response = bytes([0x00, 0x00, 0x5A, 0xC1, 0x00, 0x00, 0x00, 0x2A])
    assert format0_decimal(response, 1, 4) == "42"


def test_a_negative_response_writes_no_number():
    response = bytes([0x00, 0x00, 0x7F, 0x1A])
    with pytest.raises(Vit1Error, match="negative"):
        format0_decimal(response, 1, 4)
