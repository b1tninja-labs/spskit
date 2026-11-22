//! Port of `tests/test_wrapper.py`: the connect-string forms and the format-0 decoder.

use spskit::vit1::format0_decimal;
use spskit::wrapper::{EXPORTS, InitString, WRAPPER_KEY, parse_init};

fn wrapper(version: &str, name: &str) -> InitString {
    InitString {
        form: "wrapper".to_owned(),
        version: version.to_owned(),
        name: name.to_owned(),
    }
}

fn named(form: &str, name: &str) -> InitString {
    InitString {
        form: form.to_owned(),
        version: String::new(),
        name: name.to_owned(),
    }
}

#[test]
fn the_percent_form_names_the_version_and_the_tool() {
    assert_eq!(
        parse_init("%04.04%J2534,VXDIAG").unwrap(),
        wrapper("04.04", "VXDIAG")
    );
    assert_eq!(WRAPPER_KEY, "SOFTWARE\\GM\\J2534Wrapper");
    assert_eq!(
        EXPORTS,
        [
            "GetDefaultDeviceInfo",
            "ClearDefaultDeviceInfo",
            "GetConnectedDeviceInfo",
            "GetDeviceStatus",
        ]
    );
}

#[test]
fn an_empty_string_asks_for_the_default_device() {
    assert_eq!(parse_init("").unwrap(), named("default", ""));
}

#[test]
fn a_selected_connection_name_is_kept() {
    assert_eq!(
        parse_init("Bosch - MDI").unwrap(),
        named("connection", "Bosch - MDI")
    );
}

#[test]
fn auto_and_the_old_com_form_are_not_the_wrapper_form() {
    assert_eq!(parse_init("AUTO").unwrap(), named("auto", ""));
    assert_eq!(parse_init("AUTO,38400").unwrap(), named("auto", "38400"));
    assert_eq!(
        parse_init("COM4,115200").unwrap(),
        named("legacy", "COM4,115200")
    );
}

#[test]
fn a_wrapper_form_without_a_name_is_refused() {
    let err = parse_init("%04.04%J2534,").unwrap_err();
    assert!(err.to_string().contains("version and a tool"));
}

#[test]
fn a_positive_gmlan_response_is_the_format0_decimal() {
    let response = [0x00, 0x00, 0x5A, 0xC1, 0x00, 0x00, 0x00, 0x2A];
    assert_eq!(format0_decimal(&response, 1, 4).unwrap(), "42");
}

#[test]
fn a_negative_response_writes_no_number() {
    let response = [0x00, 0x00, 0x7F, 0x1A];
    let err = format0_decimal(&response, 1, 4).unwrap_err();
    assert!(err.to_string().contains("negative"));
}
