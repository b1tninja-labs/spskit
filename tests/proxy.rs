//! The GM J2534 proxy binding contract, exercised through the public API the `vcxtoolkit` `cdylib`
//! will call. RE'd from `sps-nativelibs.jar` (`sae-j2534-api-contract.md` §8–§9); no SAE message
//! path is spoken here.

use spskit::error::Error;
use spskit::proxy::{
    CloseOutcome, DeviceAssignment, DeviceDescriptor, OpenDecision, PROXY_API_VERSION, PROXY_KEY,
    PROXY_LIBRARY_NAME, PROXY_VALUE, ProxyState, VersionInfo, first_match, gmlan, registration,
};

/// A VCX advertising its own name and vendor and 04.04 — it matches only the trailing catch-all.
fn vcx() -> DeviceDescriptor {
    DeviceDescriptor::new("VXDIAG VCX", "VXDIAG", "04.04")
}

#[test]
fn the_proxy_registry_names_are_the_gm_j2534proxy_key_and_jna_library() {
    assert_eq!(PROXY_KEY, r"SOFTWARE\Wow6432Node\GM\J2534Proxy");
    assert_eq!(PROXY_VALUE, "FunctionLibrary");
    assert_eq!(PROXY_LIBRARY_NAME, "J2534Wrapper_proxy");
}

#[test]
fn the_default_allow_list_catch_all_selects_any_vcx() {
    let state = ProxyState::with_default_lists();
    assert!(state.accepts(&vcx()));
    // It matches the final catch-all entry, not an earlier named vendor row.
    assert_eq!(
        first_match(state.allow(), &vcx()).unwrap(),
        state.allow().last().unwrap()
    );
}

#[test]
fn open_auto_accepts_without_a_picker_and_threads_the_device_id_through_close() {
    let mut state = ProxyState::with_default_lists();
    let assignment = DeviceAssignment {
        device_id: 3,
        serial_number: 998_877,
    };
    let decision = state.open(&vcx(), assignment);
    assert_eq!(decision, OpenDecision::Accept(assignment));
    assert_eq!(decision.return_code(), Some(0));
    assert!(state.is_open(3));

    assert_eq!(state.close(3), CloseOutcome::Closed);
    assert_eq!(state.close(3), CloseOutcome::NotOpen);
}

#[test]
fn a_deny_entry_rejects_an_otherwise_allowed_device() {
    let mut state =
        ProxyState::new(spskit::proxy::DEFAULT_ALLOW_LIST, "VXDIAG VCX:VXDIAG:*:0;").unwrap();
    let decision = state.open(
        &vcx(),
        DeviceAssignment {
            device_id: 3,
            serial_number: 1,
        },
    );
    assert_eq!(decision, OpenDecision::Reject);
    assert_eq!(decision.return_code(), None);
    assert!(!state.is_open(3));
}

#[test]
fn read_version_reports_04_04_only_once_a_device_is_open() {
    let mut state = ProxyState::with_default_lists();
    assert!(matches!(
        state.read_version(3, "fw", "dll"),
        Err(Error::Proxy(_))
    ));
    state.open(
        &vcx(),
        DeviceAssignment {
            device_id: 3,
            serial_number: 1,
        },
    );
    let v = state.read_version(3, "VCX-FW", "VCX-DLL").unwrap();
    assert_eq!(v.api, PROXY_API_VERSION);
    assert_eq!(v.api, "04.04");
}

#[test]
fn a_version_string_longer_than_the_buffer_is_refused() {
    assert!(matches!(
        VersionInfo::new("x".repeat(256), "dll"),
        Err(Error::Proxy(_))
    ));
    assert!(VersionInfo::new("x".repeat(255), "dll").is_ok());
}

#[test]
fn registration_points_the_proxy_key_at_the_dll() {
    let reg = registration(r"C:\VCX\j2534_proxy.dll").unwrap();
    assert_eq!(reg.hive, "HKEY_LOCAL_MACHINE");
    assert_eq!(reg.key, PROXY_KEY);
    assert_eq!(reg.value, PROXY_VALUE);
    assert_eq!(reg.function_library, r"C:\VCX\j2534_proxy.dll");
    assert!(matches!(registration(""), Err(Error::Proxy(_))));
}

#[test]
fn the_gm_programming_channel_values_match_the_re_d_constants() {
    assert_eq!(gmlan::HS_GMLAN_DATA_RATE, 500_000);
    assert_eq!(gmlan::SW_CAN_DATA_RATE, 33_333);
    assert_eq!(gmlan::SW_CAN_HS_DATA_RATE, 83_333);
    let adapt = gmlan::timeout_adaptation();
    assert_eq!(adapt.override_stmin_ms, 1);
    assert!(adapt.resend_flow_control && adapt.retry && adapt.mixed_format_frames);
}
