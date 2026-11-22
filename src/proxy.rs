//! The GM J2534 "proxy" contract Techline Connect binds to — as pure, safe logic.
//!
//! This module does **not** export a C ABI, load a library, open a registry key, open the dongle, or
//! speak the SAE J2534 message path (`PassThruConnect`/`ReadMsgs`/`WriteMsgs`/`Ioctl`/
//! `StartMsgFilter`). Those are the unsafe, device-side responsibility of `vcxtoolkit`
//! (see `docs/tool-boundary.md`), which would build the actual `cdylib` and delegate the message
//! path to its own 04.04 pass-through. A `cdylib` cannot live here: this crate forbids `unsafe`, and
//! FFI over the raw `char*`/`unsigned long*` buffers below requires it.
//!
//! What lives here is the *binding contract* spskit owns: how `com.gm.sps.tool.jni.J2534DeviceImpl`
//! discovers and gates a device. The port classifies and decides; it resolves nothing.
//!
//! # What Techline Connect does (RE'd 2026-11-22 from `sps-nativelibs.jar`)
//!
//! `J2534DeviceImpl.loadLibrary()` reads [`PROXY_KEY`] value [`PROXY_VALUE`] (via `reg query`) and
//! `Native.load("`[`PROXY_LIBRARY_NAME`]`", J2534Wrapper.class)` — a JNA load of that GM proxy DLL.
//! The proxy's `PassThruOpen` is the **non-standard 6-argument** form in
//! `com.gm.sps.tool.jna.J2534Wrapper`; the device it opens is gated by an allow list and a deny
//! list (the [`FilterEntry`] grammar). `PassThruReadVersion` reports the API as [`PROXY_API_VERSION`]
//! into 256-byte buffers ([`VERSION_BUFFER_LEN`]). The GM-exact channel values the proxy carries for
//! a programming session are in [`gmlan`].
//!
//! The source paths are recorded in `docs/sources.md`; the ABI the `vcxtoolkit` `cdylib` must expose
//! is pinned in the shared RE note `sae-j2534-api-contract.md` §8–§9. None of these are SAE clauses,
//! so none is asserted from a spec: they are read from the decompiled GM libraries.

use std::collections::BTreeSet;

use crate::error::{Error, Result};

/// The registry key `J2534DeviceImpl.loadLibrary()` reads, under `HKEY_LOCAL_MACHINE`.
pub const PROXY_KEY: &str = r"SOFTWARE\Wow6432Node\GM\J2534Proxy";
/// The registry value under [`PROXY_KEY`] that names the proxy DLL path.
pub const PROXY_VALUE: &str = "FunctionLibrary";
/// The hive [`PROXY_KEY`] lives under. `J2534DeviceImpl` reads it with `reg query HKLM\...`.
pub const PROXY_HIVE: &str = "HKEY_LOCAL_MACHINE";
/// The JNA library name `J2534DeviceImpl.loadLibrary()` loads the proxy DLL under.
pub const PROXY_LIBRARY_NAME: &str = "J2534Wrapper_proxy";

/// The language id `J2534DeviceImpl.openJ2534Device` passes as the 6th `PassThruOpen` argument
/// (en-US LCID).
pub const OPEN_LANG_ID: u32 = 1033;
/// The `PassThruOpen` return value for success: the device id and serial number are set.
pub const OPEN_OK: i32 = 0;
/// The `PassThruOpen` return value for a user cancel in the proxy's picker UI. The auto-accept shim
/// never returns it, but a caller maps it, so it is named here.
pub const OPEN_USER_CANCELED: i32 = 9999;

/// The API version `PassThruReadVersion` reports: GM Techline Connect is J2534-1 04.04.
pub const PROXY_API_VERSION: &str = "04.04";
/// The size of each `char*` buffer `PassThruReadVersion` writes into. A reported string must leave
/// room for the trailing NUL, so its length must be at most `VERSION_BUFFER_LEN - 1`.
pub const VERSION_BUFFER_LEN: usize = 256;

/// The default GM allow list (`J2534Wrapper` `ALLOW_LIST`). The trailing `*:*:*:0` is a catch-all
/// that accepts any device, so a VCX advertising any name, any vendor and any API matches it.
pub const DEFAULT_ALLOW_LIST: &str =
    "Ford-VCM-II:*:04.04:0;M-VCI:Bosch:04.04:1;*:Bosch:*:1;*:*:*:0;";
/// The default GM deny list: empty, so nothing is denied.
pub const DEFAULT_DENY_LIST: &str = "";

/// One field of a [`FilterEntry`]: either the `*` wildcard or an exact literal.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Pattern {
    /// `*`: matches any value.
    Any,
    /// A literal that must equal the device field exactly.
    Exact(String),
}

impl Pattern {
    /// Parse one `:`-separated field: `*` becomes [`Pattern::Any`], anything else an exact literal.
    fn parse(field: &str) -> Self {
        if field == "*" {
            Pattern::Any
        } else {
            Pattern::Exact(field.to_owned())
        }
    }

    /// Whether this pattern matches a device field.
    #[must_use]
    pub fn matches(&self, value: &str) -> bool {
        match self {
            Pattern::Any => true,
            Pattern::Exact(literal) => literal == value,
        }
    }
}

/// The device a GM allow/deny list is matched against: the three fields before the flag.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeviceDescriptor {
    /// The device name (`Ford-VCM-II`, `M-VCI`, or a VCX name).
    pub name: String,
    /// The device vendor (`Bosch`, ...).
    pub vendor: String,
    /// The advertised J2534 API version (`04.04`).
    pub api_version: String,
}

impl DeviceDescriptor {
    /// A device descriptor from its three advertised fields.
    pub fn new(
        name: impl Into<String>,
        vendor: impl Into<String>,
        api_version: impl Into<String>,
    ) -> Self {
        Self {
            name: name.into(),
            vendor: vendor.into(),
            api_version: api_version.into(),
        }
    }
}

/// One entry of a GM allow or deny list: `DeviceName:Vendor:ApiVersion:Flag`.
///
/// `;`-separated, `*` the wildcard. The flag is `1` for an auto-selected device (Bosch / M-VCI — no
/// picker) and `0` for one the picker merely offers; the auto-accept shim selects any matched
/// device regardless.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FilterEntry {
    /// The device-name pattern.
    pub name: Pattern,
    /// The vendor pattern.
    pub vendor: Pattern,
    /// The API-version pattern.
    pub api_version: Pattern,
    /// The trailing flag: `1` auto-select, `0` picker-offered.
    pub flag: u8,
}

impl FilterEntry {
    /// Whether this entry matches a device (all three patterns match).
    #[must_use]
    pub fn matches(&self, device: &DeviceDescriptor) -> bool {
        self.name.matches(&device.name)
            && self.vendor.matches(&device.vendor)
            && self.api_version.matches(&device.api_version)
    }

    /// Whether the flag marks the device as auto-selected (no picker).
    #[must_use]
    pub fn auto_select(&self) -> bool {
        self.flag == 1
    }
}

/// Parse a GM allow or deny list into its entries.
///
/// An empty string is an empty list. A trailing `;` is tolerated (the deny-list and allow-list
/// literals both end with one). Each entry is exactly four `:`-separated fields and the flag is `0`
/// or `1`.
///
/// # Errors
/// Returns [`Error::Proxy`] when an entry does not have four fields or the flag is not `0` or `1`.
pub fn parse_filter_list(text: &str) -> Result<Vec<FilterEntry>> {
    let mut entries = Vec::new();
    for raw in text.split(';') {
        if raw.is_empty() {
            continue;
        }
        let fields: Vec<&str> = raw.split(':').collect();
        let [name, vendor, api_version, flag] = fields.as_slice() else {
            return Err(Error::proxy(format!(
                "a filter entry is name:vendor:api:flag, not {raw:?}"
            )));
        };
        let flag = match *flag {
            "0" => 0,
            "1" => 1,
            other => {
                return Err(Error::proxy(format!(
                    "a filter flag is 0 or 1, not {other:?}"
                )));
            }
        };
        entries.push(FilterEntry {
            name: Pattern::parse(name),
            vendor: Pattern::parse(vendor),
            api_version: Pattern::parse(api_version),
            flag,
        });
    }
    Ok(entries)
}

/// The first entry of a list that matches a device, or `None` when none does.
#[must_use]
pub fn first_match<'a>(
    entries: &'a [FilterEntry],
    device: &DeviceDescriptor,
) -> Option<&'a FilterEntry> {
    entries.iter().find(|entry| entry.matches(device))
}

/// The device id and serial number the VCX supplies when the proxy accepts it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DeviceAssignment {
    /// The device id `PassThruOpen` writes to `*pDeviceID`.
    pub device_id: u32,
    /// The serial number `PassThruOpen` writes to `*pSerialNumber`.
    pub serial_number: i32,
}

/// What the 6-argument GM `PassThruOpen` decides for a device, before the return code is formed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OpenDecision {
    /// The device matched the allow list and no deny entry: `PassThruOpen` returns [`OPEN_OK`] and
    /// writes this device id and serial number.
    Accept(DeviceAssignment),
    /// The device matched no allow entry, or a deny entry: `PassThruOpen` returns an error.
    Reject,
}

impl OpenDecision {
    /// Whether the decision is to accept the device.
    #[must_use]
    pub fn is_accept(&self) -> bool {
        matches!(self, OpenDecision::Accept(_))
    }

    /// The `PassThruOpen` return code for a decision: [`OPEN_OK`] for accept, or `None` for a
    /// rejection — the only numeric return values RE'd from the proxy are [`OPEN_OK`] and
    /// [`OPEN_USER_CANCELED`], so the error code for a rejection is the `vcxtoolkit` FFI layer's
    /// choice (a J2534 device error), not invented here.
    #[must_use]
    pub fn return_code(&self) -> Option<i32> {
        match self {
            OpenDecision::Accept(_) => Some(OPEN_OK),
            OpenDecision::Reject => None,
        }
    }
}

/// What `PassThruClose` decides for a device id.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloseOutcome {
    /// The device was open and is now closed.
    Closed,
    /// No device with that id was open: `PassThruClose` returns an error.
    NotOpen,
}

/// The three strings `PassThruReadVersion` writes into its firmware, DLL and API buffers.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VersionInfo {
    /// The firmware version string (the VCX reports it).
    pub firmware: String,
    /// The DLL version string (the VCX reports it).
    pub dll: String,
    /// The API version — always [`PROXY_API_VERSION`].
    pub api: String,
}

impl VersionInfo {
    /// A version report for the VCX: firmware and DLL as given, API fixed to [`PROXY_API_VERSION`].
    ///
    /// # Errors
    /// Returns [`Error::Proxy`] when any string would not fit a [`VERSION_BUFFER_LEN`]-byte buffer
    /// with its trailing NUL.
    pub fn new(firmware: impl Into<String>, dll: impl Into<String>) -> Result<Self> {
        let info = Self {
            firmware: firmware.into(),
            dll: dll.into(),
            api: PROXY_API_VERSION.to_owned(),
        };
        info.check_fits()?;
        Ok(info)
    }

    /// Check that every string fits a [`VERSION_BUFFER_LEN`]-byte buffer with a trailing NUL.
    fn check_fits(&self) -> Result<()> {
        for (label, value) in [
            ("firmware", &self.firmware),
            ("dll", &self.dll),
            ("api", &self.api),
        ] {
            if value.len() >= VERSION_BUFFER_LEN {
                return Err(Error::proxy(format!(
                    "the {label} version is {} bytes; a PassThruReadVersion buffer holds {} with its NUL",
                    value.len(),
                    VERSION_BUFFER_LEN - 1
                )));
            }
        }
        Ok(())
    }
}

/// The registry registration that points Techline Connect at a proxy DLL.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProxyRegistration {
    /// The hive — [`PROXY_HIVE`].
    pub hive: String,
    /// The key — [`PROXY_KEY`].
    pub key: String,
    /// The value — [`PROXY_VALUE`].
    pub value: String,
    /// The DLL path written to the value.
    pub function_library: String,
}

/// The registration `vcxtoolkit`'s installer would write so Techline Connect loads a proxy DLL.
///
/// This builds the `(hive, key, value, data)` tuple only; writing it to the registry is
/// `vcxtoolkit`'s side (`docs/tool-boundary.md`), not this library's.
///
/// # Errors
/// Returns [`Error::Proxy`] when the DLL path is empty.
pub fn registration(dll_path: &str) -> Result<ProxyRegistration> {
    if dll_path.is_empty() {
        return Err(Error::proxy("the proxy FunctionLibrary path is empty"));
    }
    Ok(ProxyRegistration {
        hive: PROXY_HIVE.to_owned(),
        key: PROXY_KEY.to_owned(),
        value: PROXY_VALUE.to_owned(),
        function_library: dll_path.to_owned(),
    })
}

/// The GM J2534 proxy binding state: the allow and deny lists, and the devices currently open.
///
/// It models the device-management surface JNA sees — `PassThruOpen` / `PassThruClose` /
/// `PassThruReadVersion` — and nothing below it. The message path stays in `vcxtoolkit`.
#[derive(Debug, Clone)]
pub struct ProxyState {
    allow: Vec<FilterEntry>,
    deny: Vec<FilterEntry>,
    open_devices: BTreeSet<u32>,
}

impl ProxyState {
    /// A proxy state with the given allow and deny list strings.
    ///
    /// # Errors
    /// Returns [`Error::Proxy`] when either list is malformed (see [`parse_filter_list`]).
    pub fn new(allow_list: &str, deny_list: &str) -> Result<Self> {
        Ok(Self {
            allow: parse_filter_list(allow_list)?,
            deny: parse_filter_list(deny_list)?,
            open_devices: BTreeSet::new(),
        })
    }

    /// A proxy state with the GM defaults ([`DEFAULT_ALLOW_LIST`], [`DEFAULT_DENY_LIST`]).
    ///
    /// # Panics
    /// Never in practice: the default lists are well-formed constants, proven by the module tests.
    /// The `expect` guards against an edit that breaks one of those literals.
    #[must_use]
    pub fn with_default_lists() -> Self {
        // The default lists are constants parsed in the tests, so this cannot fail; build the
        // vectors directly rather than unwrap a `Result` in a `#[must_use]` constructor.
        Self::new(DEFAULT_ALLOW_LIST, DEFAULT_DENY_LIST)
            .expect("the default GM allow and deny lists are well-formed")
    }

    /// The allow list.
    #[must_use]
    pub fn allow(&self) -> &[FilterEntry] {
        &self.allow
    }

    /// The deny list.
    #[must_use]
    pub fn deny(&self) -> &[FilterEntry] {
        &self.deny
    }

    /// Whether a device is gated through: it matches an allow entry and matches no deny entry.
    #[must_use]
    pub fn accepts(&self, device: &DeviceDescriptor) -> bool {
        first_match(&self.allow, device).is_some() && first_match(&self.deny, device).is_none()
    }

    /// The 6-argument GM `PassThruOpen`, auto-accepting (no picker): a gated-through device is
    /// accepted with the VCX's assignment and recorded open; any other device is rejected.
    ///
    /// Calling it twice for the same accepted id is idempotent — the id is already in the open set.
    pub fn open(
        &mut self,
        device: &DeviceDescriptor,
        assignment: DeviceAssignment,
    ) -> OpenDecision {
        if self.accepts(device) {
            self.open_devices.insert(assignment.device_id);
            OpenDecision::Accept(assignment)
        } else {
            OpenDecision::Reject
        }
    }

    /// `PassThruClose`: close an open device id.
    pub fn close(&mut self, device_id: u32) -> CloseOutcome {
        if self.open_devices.remove(&device_id) {
            CloseOutcome::Closed
        } else {
            CloseOutcome::NotOpen
        }
    }

    /// Whether a device id is currently open.
    #[must_use]
    pub fn is_open(&self, device_id: u32) -> bool {
        self.open_devices.contains(&device_id)
    }

    /// `PassThruReadVersion`: the three version strings for an open device.
    ///
    /// # Errors
    /// Returns [`Error::Proxy`] when the device id is not open, or when a version string does not
    /// fit a [`VERSION_BUFFER_LEN`]-byte buffer.
    pub fn read_version(
        &self,
        device_id: u32,
        firmware: impl Into<String>,
        dll: impl Into<String>,
    ) -> Result<VersionInfo> {
        if !self.is_open(device_id) {
            return Err(Error::proxy(format!(
                "PassThruReadVersion on device {device_id}, which is not open"
            )));
        }
        VersionInfo::new(firmware, dll)
    }
}

impl Default for ProxyState {
    fn default() -> Self {
        Self::with_default_lists()
    }
}

/// GM-exact channel values the proxy carries for an SPS programming session.
///
/// RE'd 2026-11-22 from `tisvcsv4.dll` (the GM J2534 / ISO 15765 transport layer); see
/// `sae-j2534-api-contract.md` §9. These are baked GM constants and a runtime policy, not SAE
/// clauses — `vcxtoolkit`'s pass-through consumes them in its `SET_CONFIG` and its ISO 15765 timeout
/// handling. This library records them as the source of truth for the GM values; it does not push
/// them onto a bus.
pub mod gmlan {
    /// HS-GMLAN `DATA_RATE` for the programming channel: 500 000 bit/s (`0x7A120`), the flat
    /// high-speed CAN rate.
    pub const HS_GMLAN_DATA_RATE: u32 = 500_000;
    /// SW-CAN (single-wire GMLAN) idle rate: 33 333 bit/s (`0x8235`).
    pub const SW_CAN_DATA_RATE: u32 = 33_333;
    /// SW-CAN high-speed (programming) rate: 83 333 bit/s (`0x14585`). SW-CAN switches up from
    /// [`SW_CAN_DATA_RATE`] for programming.
    pub const SW_CAN_HS_DATA_RATE: u32 = 83_333;
    /// The STmin GM overrides to on an ISO 15765 ECU timeout: 1 ms (see [`timeout_adaptation`]).
    pub const TIMEOUT_STMIN_OVERRIDE_MS: u32 = 1;

    /// GM's ISO 15765 behavior when an ECU does not answer in time.
    ///
    /// The `tisvcsv4.dll` handler logs, on a timeout, that it overrides STmin to 1 ms, re-sends the
    /// flow control and invokes retry logic, and that it tolerates mixed single/multi-frame
    /// formatting. A pass-through that does not adapt this way can fail a marginal-ECU read GM's
    /// would recover.
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub struct TimeoutAdaptation {
        /// The STmin to override to, in milliseconds.
        pub override_stmin_ms: u32,
        /// Whether to re-send the flow control frame.
        pub resend_flow_control: bool,
        /// Whether to retry the exchange.
        pub retry: bool,
        /// Whether mixed single/multi-frame formatting is tolerated on the bus.
        pub mixed_format_frames: bool,
    }

    /// GM's ISO 15765 timeout adaptation (§9): override STmin to 1 ms, re-send flow control, retry,
    /// tolerate mixed-format frames.
    #[must_use]
    pub fn timeout_adaptation() -> TimeoutAdaptation {
        TimeoutAdaptation {
            override_stmin_ms: TIMEOUT_STMIN_OVERRIDE_MS,
            resend_flow_control: true,
            retry: true,
            mixed_format_frames: true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn vcx() -> DeviceDescriptor {
        // A VCX advertising its own name, no vendor match, 04.04 — it only matches the catch-all.
        DeviceDescriptor::new("VXDIAG VCX", "VXDIAG", "04.04")
    }

    #[test]
    fn the_default_allow_list_parses_to_four_entries_ending_in_the_catch_all() {
        let entries = parse_filter_list(DEFAULT_ALLOW_LIST).unwrap();
        assert_eq!(entries.len(), 4);
        let last = entries.last().unwrap();
        assert_eq!(last.name, Pattern::Any);
        assert_eq!(last.vendor, Pattern::Any);
        assert_eq!(last.api_version, Pattern::Any);
        assert_eq!(last.flag, 0);
        // The Bosch / M-VCI rows are flagged auto-select; the Ford and catch-all rows are not.
        assert!(!entries[0].auto_select());
        assert!(entries[1].auto_select());
        assert!(entries[2].auto_select());
        assert!(!entries[3].auto_select());
    }

    #[test]
    fn a_malformed_entry_or_flag_is_refused() {
        assert!(matches!(
            parse_filter_list("too:few:fields"),
            Err(Error::Proxy(_))
        ));
        assert!(matches!(parse_filter_list("*:*:*:2"), Err(Error::Proxy(_))));
    }

    #[test]
    fn the_catch_all_selects_any_vcx_through_the_default_lists() {
        let state = ProxyState::with_default_lists();
        assert!(state.accepts(&vcx()));
        // The matched entry is the trailing catch-all, not an earlier named row.
        let entry = first_match(state.allow(), &vcx()).unwrap();
        assert_eq!(entry, state.allow().last().unwrap());
    }

    #[test]
    fn a_deny_entry_blocks_an_otherwise_allowed_device() {
        let state = ProxyState::new(DEFAULT_ALLOW_LIST, "VXDIAG VCX:VXDIAG:*:0;").unwrap();
        assert!(!state.accepts(&vcx()));
    }

    #[test]
    fn open_auto_accepts_a_vcx_and_records_it_then_close_removes_it() {
        let mut state = ProxyState::with_default_lists();
        let assignment = DeviceAssignment {
            device_id: 7,
            serial_number: 12345,
        };
        let decision = state.open(&vcx(), assignment);
        assert_eq!(decision, OpenDecision::Accept(assignment));
        assert_eq!(decision.return_code(), Some(OPEN_OK));
        assert!(state.is_open(7));

        assert_eq!(state.close(7), CloseOutcome::Closed);
        assert!(!state.is_open(7));
        assert_eq!(state.close(7), CloseOutcome::NotOpen);
    }

    #[test]
    fn open_rejects_a_denied_device_and_does_not_record_it() {
        let mut state = ProxyState::new(DEFAULT_ALLOW_LIST, "VXDIAG VCX:VXDIAG:*:0;").unwrap();
        let decision = state.open(
            &vcx(),
            DeviceAssignment {
                device_id: 7,
                serial_number: 1,
            },
        );
        assert_eq!(decision, OpenDecision::Reject);
        assert_eq!(decision.return_code(), None);
        assert!(!state.is_open(7));
    }

    #[test]
    fn read_version_reports_04_04_only_for_an_open_device() {
        let mut state = ProxyState::with_default_lists();
        let err = state.read_version(7, "fw", "dll").unwrap_err();
        assert!(matches!(err, Error::Proxy(_)));

        state.open(
            &vcx(),
            DeviceAssignment {
                device_id: 7,
                serial_number: 1,
            },
        );
        let version = state.read_version(7, "VCX-FW-1.2", "VCX-DLL-3.4").unwrap();
        assert_eq!(version.api, "04.04");
        assert_eq!(version.firmware, "VCX-FW-1.2");
    }

    #[test]
    fn a_version_string_that_overflows_the_buffer_is_refused() {
        let long = "x".repeat(VERSION_BUFFER_LEN);
        assert!(matches!(
            VersionInfo::new(long, "dll"),
            Err(Error::Proxy(_))
        ));
        let fits = "x".repeat(VERSION_BUFFER_LEN - 1);
        assert!(VersionInfo::new(fits, "dll").is_ok());
    }

    #[test]
    fn registration_points_the_proxy_key_at_the_dll_and_refuses_an_empty_path() {
        let reg = registration(r"C:\VCX\j2534_proxy.dll").unwrap();
        assert_eq!(reg.hive, "HKEY_LOCAL_MACHINE");
        assert_eq!(reg.key, r"SOFTWARE\Wow6432Node\GM\J2534Proxy");
        assert_eq!(reg.value, "FunctionLibrary");
        assert_eq!(reg.function_library, r"C:\VCX\j2534_proxy.dll");
        assert!(matches!(registration(""), Err(Error::Proxy(_))));
    }

    #[test]
    fn the_gm_programming_values_are_the_re_d_constants() {
        assert_eq!(gmlan::HS_GMLAN_DATA_RATE, 500_000);
        assert_eq!(gmlan::SW_CAN_DATA_RATE, 33_333);
        assert_eq!(gmlan::SW_CAN_HS_DATA_RATE, 83_333);
        let adapt = gmlan::timeout_adaptation();
        assert_eq!(adapt.override_stmin_ms, 1);
        assert!(adapt.resend_flow_control && adapt.retry && adapt.mixed_format_frames);
    }
}
