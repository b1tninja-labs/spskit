//! Programming-data request for the method-128 reads on this VIN.
//!
//! A saved module read is attribute pairs. Those pairs become the VIT1 control-module block on the
//! controller. This module returns the request body; it does not post it, open a socket, or fill
//! part numbers. Every function here walks the catalog documents the caller supplies.
//!
//! The documents are JSON, modelled as [`serde_json::Value`]. Where a function reads one key off a
//! document it reads it the way Python's `dict.get` did after `json.loads`: a missing key and a JSON
//! `null` both read as absence. The two decimal/text decoders key on the `$7F` negative-response
//! marker and the `$1A` GMLAN ReadDataByIdentifier service; both come from the sibling `udskit`
//! catalog so there is one Rust source of truth for the service framing.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Map, Value, json};

use crate::error::{Error, Result};

/// The `$7F` negative-response marker, from the shared udskit service catalog.
const NEGATIVE_RESPONSE_SID: u8 = udskit::services::NEGATIVE_RESPONSE_SID;

/// The path `GetProgrammingDataTask` posts the [`programming_data_request`] body to.
pub const PROGRAMMING_DATA_PATH: &str = "/sps/legacy/cloud/getProgrammingData";
/// The path the [`vci_programming_data_request`] body is posted to.
pub const VCI_PROGRAMMING_DATA_PATH: &str = "/sps/legacy/cloud/getVciProgrammingData";
/// The path `SelectedControllerTask` posts the same programming-data body to.
pub const SELECTED_CONTROLLER_PATH: &str = "/sps/legacy/cloud/getSelectedController";
/// K17's device id.
pub const K17_DEVICE_ID: i64 = 40;
/// K17's request method id.
pub const K17_REQUEST_METHOD: i64 = 11228;
/// The ten plain part identifiers `$C1` through `$CA`.
pub const PART_DIDS: [&str; 10] = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA"];

const PART_START: usize = 1;
const PART_LENGTH: usize = 4;

/// An attribute pair: a name and its string value, as the VIT1 builder walks them.
pub type Attr = (String, String);

/// The hardware identifier a saved read carries: four format-0 bytes, or an opaque string.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Hardware {
    /// A format-0, length-4, start-1 slice, printed as a decimal (`hardware_decimal` rules).
    Decimal(Vec<u8>),
    /// The hardware string a length-0 read keeps verbatim (K17 and the other string rules).
    Text(String),
}

// ----------------------------------------------------------------------------------- the rule table

/// What one saved-read rule pulls from a module read (private; exposed through [`ReadShape`]).
struct ReadRule {
    code: &'static str,
    device_id: i64,
    request_method: i64,
    part_dids: &'static [&'static str],
    hardware_decimal: bool,
    cvn: bool,
    read_vin: bool,
    hardware_did: Option<&'static str>,
}

// GMLAN format 0, length 4, start 1 prints four bytes from the first data byte. K17's hardware
// length is 0, and that length does not print a decimal. cvn_in_vit1 is the character 1 or 0. The
// digits sit in partnum after a hyphen. A missing hardware DID means the request method does not
// read one. The first four rules are the Python direct `_ReadRule` constructions (read_vin true,
// hardware DID "CC" by default); the rest are the `_rule` helper (hardware_decimal = the DID is
// present, read_vin false unless named).
const RULES: &[ReadRule] = &[
    ReadRule {
        code: "K17",
        device_id: K17_DEVICE_ID,
        request_method: K17_REQUEST_METHOD,
        part_dids: &PART_DIDS,
        hardware_decimal: false,
        cvn: false,
        read_vin: true,
        hardware_did: Some("CC"),
    },
    ReadRule {
        code: "K33",
        device_id: 153,
        request_method: 11231,
        part_dids: &PART_DIDS,
        hardware_decimal: true,
        cvn: false,
        read_vin: true,
        hardware_did: Some("CC"),
    },
    ReadRule {
        code: "K20",
        device_id: 17,
        request_method: 11229,
        part_dids: &PART_DIDS,
        hardware_decimal: true,
        cvn: true,
        read_vin: true,
        hardware_did: Some("CC"),
    },
    ReadRule {
        code: "K9",
        device_id: 64,
        request_method: 410,
        part_dids: &[
            "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "41", "42", "43", "44",
            "45", "46", "47", "48", "49", "4A",
        ],
        hardware_decimal: true,
        cvn: false,
        read_vin: true,
        hardware_did: Some("CC"),
    },
    rule("A22", 102, 446, &["C1"], Some("CB"), false, false),
    rule(
        "A11",
        128,
        432,
        &["C1", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "73"],
        Some("CB"),
        false,
        false,
    ),
    rule("B218R", 91, 11243, &PART_DIDS, Some("CB"), false, false),
    rule("B218L", 185, 11239, &PART_DIDS, Some("CB"), false, false),
    rule("B233B", 210, 388, &["C1", "C2"], Some("CB"), false, false),
    rule(
        "K43",
        49,
        417,
        &["C1", "C2", "C3"],
        Some("CB"),
        false,
        false,
    ),
    rule(
        "K84",
        175,
        427,
        &["C1", "C2", "C3"],
        Some("CB"),
        false,
        false,
    ),
    rule("T3", 129, 434, &["C1", "CA"], Some("CB"), false, false),
    rule("K182", 187, 423, &["C1", "C2"], Some("CB"), false, false),
    rule("K109", 188, 428, &["C1", "C2"], Some("CB"), false, false),
    rule("K177", 43, 416, &["C1", "C2"], Some("CC"), false, false),
    rule(
        "K107A",
        29,
        531,
        &["C1", "C2", "C3"],
        Some("CB"),
        true,
        false,
    ),
    rule(
        "K107B",
        30,
        532,
        &["C1", "C2", "C3"],
        Some("CC"),
        true,
        false,
    ),
    rule("K118", 156, 530, &["C1", "C2"], None, false, false),
    rule(
        "P16",
        96,
        11242,
        &[
            "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "40", "42", "44", "67",
            "69", "71", "74", "76",
        ],
        Some("CB"),
        false,
        true,
    ),
    rule("K73", 151, 601, &[], Some("CB"), false, true),
    rule(
        "K124",
        108,
        396,
        &[
            "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "60", "62", "64", "66",
            "68", "6A",
        ],
        Some("CB"),
        false,
        false,
    ),
    rule(
        "K74",
        143,
        579,
        &["C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "71"],
        Some("C1"),
        false,
        false,
    ),
    rule("K114B", 203, 529, &["C1", "C2"], None, false, true),
    rule("K36", 88, 421, &["C1", "C2", "C3"], Some("C1"), false, true),
];

/// The `_rule` helper: `hardware_decimal` follows whether a hardware DID is present.
const fn rule(
    code: &'static str,
    device_id: i64,
    request_method: i64,
    part_dids: &'static [&'static str],
    hardware_did: Option<&'static str>,
    cvn: bool,
    read_vin: bool,
) -> ReadRule {
    ReadRule {
        code,
        device_id,
        request_method,
        part_dids,
        hardware_decimal: hardware_did.is_some(),
        cvn,
        read_vin,
        hardware_did,
    }
}

fn by_code(code: &str) -> Option<&'static ReadRule> {
    RULES.iter().find(|r| r.code == code)
}

const HEADER: [&str; 8] = [
    "sps_id",
    "chksum",
    "table_len",
    "nav_info",
    "reserved",
    "numcms",
    "devicetype",
    "spsmode",
];
const BLOCK_START: [&str; 5] = ["ssecuhn", "blocklen", "disp_type", "protocol", "ecu_adr"];
const SECURITY: [&str; 4] = ["seed", "numseeds", "keycode", "msg_auth_sts"];

// ------------------------------------------------------------------------------- JSON accessors

type Obj = Map<String, Value>;

/// Python `dict.get(key)` after `json.loads`: an absent key and a JSON `null` both read as absence.
fn py_get<'a>(doc: &'a Obj, key: &str) -> Option<&'a Value> {
    match doc.get(key) {
        None | Some(Value::Null) => None,
        Some(v) => Some(v),
    }
}

/// The value as a Python `int` (not a `bool`, not a float).
fn as_int(v: &Value) -> Option<i64> {
    if v.is_i64() || v.is_u64() {
        v.as_i64()
    } else {
        None
    }
}

/// One field of a raw mapping input, with the `dict.get` null-is-absent reading.
fn field<'a>(value: &'a Value, key: &str) -> Option<&'a Value> {
    value.as_object().and_then(|m| py_get(m, key))
}

/// A field read as a Python `int`.
fn field_as_int(value: &Value, key: &str) -> Option<i64> {
    field(value, key).and_then(as_int)
}

/// `_document`: a deep copy that must be a JSON object, else an error labelled by `label`.
fn document(value: &Value, label: &str) -> Result<Obj> {
    match value {
        Value::Object(map) => Ok(map.clone()),
        _ => Err(Error::vit1(format!("{label} is not a document"))),
    }
}

// --------------------------------------------------------------------------------- read shapes

/// What one saved-read rule pulls from a module read.
///
/// These are the facts a caller needs to map a captured read onto [`module_attributes`] without
/// reaching into the private rule table. A numeric `hardware_did` with `hardware_decimal` is the
/// format-0, length-4, start-1 slice; K17's hardware length is 0, so its `ssecuhn` stays a string.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReadShape {
    /// The controller code.
    pub code: String,
    /// The device id.
    pub device_id: i64,
    /// The request method id.
    pub request_method: i64,
    /// The plain part identifiers the read pulls, in request-method order.
    pub part_dids: Vec<String>,
    /// The hardware identifier DID, or `None` when the request method reads none.
    pub hardware_did: Option<String>,
    /// Whether the hardware id is the format-0 decimal slice (else an opaque string).
    pub hardware_decimal: bool,
    /// Whether the request method reads a VIN.
    pub reads_vin: bool,
    /// Whether the request method reads a CVN (`cvn_in_vit1`).
    pub reads_cvn: bool,
}

/// The saved-read shape for one controller code.
///
/// # Errors
/// Returns [`Error::Vit1`] for a code with no saved-read rule, which includes the deliberately
/// refused controllers such as K16, and K73 request methods 520 and 566. K73 keeps method 601 as
/// its saved-read rule.
pub fn read_shape(code: &str) -> Result<ReadShape> {
    let rule =
        by_code(code).ok_or_else(|| Error::vit1("this controller is not a saved-read rule"))?;
    Ok(ReadShape {
        code: rule.code.to_owned(),
        device_id: rule.device_id,
        request_method: rule.request_method,
        part_dids: rule.part_dids.iter().map(|s| (*s).to_owned()).collect(),
        hardware_did: rule.hardware_did.map(str::to_owned),
        hardware_decimal: rule.hardware_decimal,
        reads_vin: rule.read_vin,
        reads_cvn: rule.cvn,
    })
}

/// Every controller code with a saved-read rule, in table order.
#[must_use]
pub fn read_codes() -> Vec<String> {
    RULES.iter().map(|r| r.code.to_owned()).collect()
}

// ------------------------------------------------------------------------------- the decoders

/// Four bytes from byte 1 of a DID payload, printed in base 10.
///
/// Byte 0 is the DID echo. The next four are an unsigned integer, first byte most significant —
/// the GMLAN format-0 slice for start byte 1 and length 4.
///
/// # Errors
/// Returns [`Error::Vit1`] when the payload has fewer than five bytes.
pub fn decimal_partno(payload: &[u8]) -> Result<String> {
    let end = PART_START + PART_LENGTH;
    if payload.len() < end {
        return Err(Error::vit1("a part DID needs 4 bytes from byte 1"));
    }
    Ok(be_uint(&payload[PART_START..end]).to_string())
}

/// The GMLAN format-0 integer from a service `$1A` response.
///
/// Response byte 2 is the service. `$7F` writes nothing. The start byte is added to 3, so start 1 is
/// response byte 4. Length is 1 to 4, read as an unsigned integer, first byte most significant.
///
/// # Errors
/// Returns [`Error::Vit1`] when the length is out of range, the response is a negative response, or
/// it is shorter than the slice.
pub fn format0_decimal(response: &[u8], start: i64, length: usize) -> Result<String> {
    if !(1..=4).contains(&length) {
        return Err(Error::vit1("format 0 length is 1 to 4"));
    }
    if response.len() < 3 || response[2] == NEGATIVE_RESPONSE_SID {
        return Err(Error::vit1("a negative response writes no number"));
    }
    let short = || Error::vit1("the response is shorter than the format-0 slice");
    let begin = usize::try_from(start + 3).map_err(|_| short())?;
    let end = begin + length;
    if response.len() < end {
        return Err(short());
    }
    Ok(be_uint(&response[begin..end]).to_string())
}

/// Format 1: each selected byte becomes two characters.
///
/// Each nibble is added to `0x30`, so the characters run `0` through `9` and then `:` through `?`.
/// Length is 1 to 16, from the same start-plus-3 index as format 0.
///
/// # Errors
/// Returns [`Error::Vit1`] when the length is out of range, the response is negative, or it is short.
pub fn format1_text(response: &[u8], start: i64, length: usize) -> Result<String> {
    let mut text = String::new();
    for byte in response_slice(response, start, length, 16)? {
        text.push(char::from(0x30 + (byte >> 4)));
        text.push(char::from(0x30 + (byte & 0x0F)));
    }
    Ok(text)
}

/// Format 2: the selected bytes, copied as they are. Length is 1 to 16.
///
/// # Errors
/// Returns [`Error::Vit1`] when the length is out of range, the response is negative, or it is short.
pub fn format2_copy(response: &[u8], start: i64, length: usize) -> Result<Vec<u8>> {
    response_slice(response, start, length, 16)
}

fn response_slice(response: &[u8], start: i64, length: usize, limit: usize) -> Result<Vec<u8>> {
    if !(1..=limit).contains(&length) {
        return Err(Error::vit1(format!("this format length is 1 to {limit}")));
    }
    if response.len() < 3 || response[2] == NEGATIVE_RESPONSE_SID {
        return Err(Error::vit1("a negative response writes no number"));
    }
    let short = || Error::vit1("the response is shorter than the format slice");
    let begin = usize::try_from(start + 3).map_err(|_| short())?;
    let end = begin + length;
    if response.len() < end {
        return Err(short());
    }
    Ok(response[begin..end].to_vec())
}

/// An unsigned big-endian integer from 1 to 4 bytes.
fn be_uint(bytes: &[u8]) -> u64 {
    bytes.iter().fold(0u64, |acc, &b| (acc << 8) | u64::from(b))
}

// --------------------------------------------------------------------------- attribute pairing

/// Pair a K17 read: vin from DID `$90`, one partno per `$C1` through `$CA`, ssecuhn from `$CC`.
///
/// The four-byte slice is the part DIDs. Hardware length on this request method is 0, so `ssecuhn`
/// stays the string from the read.
///
/// # Errors
/// Returns [`Error::Vit1`] when the read does not match the K17 rule.
pub fn k17_attributes(
    vin: &str,
    parts: &BTreeMap<String, Vec<u8>>,
    ssecuhn: &str,
) -> Result<Vec<Attr>> {
    module_attributes(
        "K17",
        vin,
        parts,
        Some(Hardware::Text(ssecuhn.to_owned())),
        None,
        &[],
    )
}

/// Pair a saved read for one Normal request method on this VIN.
///
/// Parts are 4 bytes from byte 1, printed in base 10, in request-method order. A hardware DID of
/// format 0, length 4, start 1 is that same decimal. K17 keeps the hardware string. A request
/// method that does not read hardware or a VIN omits that pair. `cvn_in_vit1` is `1` or `0`; when it
/// is `1`, each `partnum` is the part string, a hyphen, and a decimal.
///
/// # Errors
/// Returns [`Error::Vit1`] when the code has no rule, the inputs do not match the rule, or a value
/// is malformed.
pub fn module_attributes(
    code: &str,
    vin: &str,
    parts: &BTreeMap<String, Vec<u8>>,
    hardware: Option<Hardware>,
    cvn: Option<&str>,
    partnums: &[String],
) -> Result<Vec<Attr>> {
    let rule =
        by_code(code).ok_or_else(|| Error::vit1("this controller is not a saved-read rule"))?;
    let mut pairs: Vec<Attr> = Vec::new();
    match rule.hardware_did {
        None => {
            if hardware.is_some() {
                return Err(Error::vit1(format!(
                    "{} does not read a hardware id",
                    rule.code
                )));
            }
        }
        Some(hw_did) if rule.hardware_decimal => {
            let Some(Hardware::Decimal(bytes)) = hardware else {
                return Err(Error::vit1(format!(
                    "{} hardware DID {hw_did} is 4 bytes from byte 1",
                    rule.code
                )));
            };
            pairs.push(("ssecuhn".to_owned(), decimal_partno(&bytes)?));
        }
        Some(_) => match hardware {
            Some(Hardware::Text(s)) if !s.is_empty() => {
                pairs.push(("ssecuhn".to_owned(), s));
            }
            _ => return Err(Error::vit1("ssecuhn is the hardware string from the read")),
        },
    }
    if rule.read_vin {
        pairs.push(("vin".to_owned(), vin_checked(vin)?));
    } else if !vin.is_empty() {
        return Err(Error::vit1(format!("{} does not read a VIN", rule.code)));
    }
    let part_set: BTreeSet<&str> = parts.keys().map(String::as_str).collect();
    let rule_set: BTreeSet<&str> = rule.part_dids.iter().copied().collect();
    if part_set != rule_set {
        return Err(Error::vit1(format!(
            "{} needs one part payload per part DID on its request method",
            rule.code
        )));
    }
    if rule.hardware_decimal {
        if let Some(hw_did) = rule.hardware_did {
            if rule.part_dids.contains(&hw_did) {
                let same = decimal_partno(&parts[hw_did])?;
                if pairs[0] != ("ssecuhn".to_owned(), same) {
                    return Err(Error::vit1(format!(
                        "{} hardware DID {hw_did} is that part's read",
                        rule.code
                    )));
                }
            }
        }
    }
    for did in rule.part_dids {
        pairs.push(("partno".to_owned(), decimal_partno(&parts[*did])?));
    }
    pairs.extend(cvn_tail(rule, cvn, partnums)?);
    Ok(pairs)
}

fn cvn_tail(rule: &ReadRule, cvn: Option<&str>, partnums: &[String]) -> Result<Vec<Attr>> {
    if !rule.cvn {
        if cvn.is_some() || !partnums.is_empty() {
            return Err(Error::vit1("CVN stays off this request"));
        }
        return Ok(Vec::new());
    }
    if cvn != Some("0") && cvn != Some("1") {
        return Err(Error::vit1("cvn_in_vit1 is 1 or 0"));
    }
    if cvn == Some("0") {
        if !partnums.is_empty() {
            return Err(Error::vit1("partnum belongs with cvn_in_vit1 1"));
        }
        return Ok(vec![("cvn_in_vit1".to_owned(), "0".to_owned())]);
    }
    if partnums.is_empty() {
        return Err(Error::vit1("cvn_in_vit1 1 carries at least one partnum"));
    }
    for value in partnums {
        check_partnum(value)?;
    }
    let mut out: Vec<Attr> = partnums
        .iter()
        .map(|v| ("partnum".to_owned(), v.clone()))
        .collect();
    out.push(("cvn_in_vit1".to_owned(), "1".to_owned()));
    Ok(out)
}

fn check_partnum(value: &str) -> Result<()> {
    let pieces: Vec<&str> = value.split('-').collect();
    if pieces.len() != 2 || pieces[0].is_empty() || !is_decimal(pieces[1]) {
        return Err(Error::vit1(
            "partnum is the part string, a hyphen, and a decimal",
        ));
    }
    Ok(())
}

/// A non-empty run of ASCII digits with no leading zero (unless it is the single digit `0`).
fn is_decimal(s: &str) -> bool {
    !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()) && !(s.len() > 1 && s.starts_with('0'))
}

fn vin_checked(vin: &str) -> Result<String> {
    crate::vin::check_vin(vin)
        .map(str::to_owned)
        .map_err(|e| Error::vit1(e.to_string()))
}

// ------------------------------------------------------------------------------- build_vit1

/// Walk attribute pairs the way `VIT1BuilderImpl` does.
///
/// Header names stay on the VIT1. An option value that contains `;` is split into one free-option
/// pair. A block-start name that is already on the current block opens the next control-module
/// block. The current block is appended when the list ends.
#[must_use]
pub fn build_vit1(attributes: &[Attr]) -> Value {
    let mut header: Vec<Attr> = Vec::new();
    let mut free: Vec<Attr> = Vec::new();
    let mut blocks: Vec<Vec<Attr>> = Vec::new();
    let mut current: Vec<Attr> = Vec::new();
    if attributes.is_empty() {
        return vit1_value(&header, &blocks, &free);
    }
    for (name, value) in attributes {
        if BLOCK_START.contains(&name.as_str()) && current.iter().any(|(k, _)| k == name) {
            blocks.push(std::mem::take(&mut current));
        }
        if name == "option" {
            if let Some(option) = free_option(value) {
                free.push(option);
            }
            continue;
        }
        if HEADER.contains(&name.as_str()) {
            header.push((name.clone(), value.clone()));
            continue;
        }
        current.push((name.clone(), value.clone()));
    }
    blocks.push(current);
    vit1_value(&header, &blocks, &free)
}

fn free_option(value: &str) -> Option<Attr> {
    let mut parts: Vec<&str> = value.split(';').collect();
    while parts.last() == Some(&"") {
        parts.pop();
    }
    let pieces: Vec<String> = parts.iter().map(|p| trim_vit(p)).collect();
    if pieces.len() <= 1 {
        return None;
    }
    Some((pieces[0].clone(), pieces[1].clone()))
}

/// Strip leading tabs and spaces, then trailing tabs, matching `_trim_vit` codepoint for codepoint.
fn trim_vit(value: &str) -> String {
    let mut chars: Vec<char> = value.chars().collect();
    while matches!(chars.first(), Some('\t' | ' ')) {
        chars.remove(0);
    }
    while chars.last() == Some(&'\t') || chars.first() == Some(&' ') {
        chars.pop();
    }
    chars.into_iter().collect()
}

fn attrs_value(pairs: &[Attr]) -> Value {
    Value::Array(
        pairs
            .iter()
            .map(|(key, value)| json!({ "key": key, "value": value }))
            .collect(),
    )
}

fn vit1_value(header: &[Attr], blocks: &[Vec<Attr>], free: &[Attr]) -> Value {
    json!({
        "vitAttrs": attrs_value(header),
        "cmbs": Value::Array(
            blocks
                .iter()
                .map(|block| json!({ "vitAttrs": attrs_value(block) }))
                .collect(),
        ),
        "freeOptions": json!({ "vitAttrs": attrs_value(free) }),
    })
}

// --------------------------------------------------------------------- the request bodies

/// The body of `POST /sps/legacy/cloud/getProgrammingData` for one saved read.
///
/// `controller` is the programming sequence; the saved read is attached as its `vit1`. The caller
/// supplies the catalog documents. This function does not read a VIN catalog, open a socket, or
/// fill part numbers.
///
/// # Errors
/// Returns [`Error::Vit1`] when the method is not 1 or 128, or the read does not attach.
pub fn programming_data_request(
    client_state: &Value,
    sps_vin: &Value,
    method: &Value,
    controller: &Value,
    option_composite: &Value,
    attributes: &[Attr],
) -> Result<Value> {
    if !matches!(field_as_int(method, "methodId"), Some(1 | 128)) {
        return Err(Error::vit1(
            "this body is the getProgrammingData request, method 1 or 128",
        ));
    }
    let sequence = controller_with_read(controller, attributes)?;
    // SpsGson does not call serializeNulls(), so a null mcvm is omitted.
    let mut body = Map::new();
    body.insert(
        "clientState".to_owned(),
        Value::Object(document(client_state, "clientState")?),
    );
    body.insert(
        "spsVin".to_owned(),
        Value::Object(document(sps_vin, "spsVin")?),
    );
    body.insert(
        "method".to_owned(),
        Value::Object(document(method, "method")?),
    );
    body.insert("controller".to_owned(), sequence);
    body.insert(
        "optionComposite".to_owned(),
        Value::Object(document(option_composite, "optionComposite")?),
    );
    Ok(Value::Object(body))
}

/// The body of `POST /sps/legacy/cloud/getVciProgrammingData` for method 2 and 256.
///
/// A missing step list is the empty list the constructor stores. The documents inside the lists are
/// the caller's. This function does not invent a VCI step, and it does not post.
///
/// # Errors
/// Returns [`Error::Vit1`] when the method is not 2 or 256, or the read does not attach.
pub fn vci_programming_data_request(
    client_state: &Value,
    sps_vin: &Value,
    method: &Value,
    controller: &Value,
    attributes: &[Attr],
    function_steps: Option<&[Value]>,
    vci_steps: Option<&[Value]>,
) -> Result<Value> {
    if !matches!(field_as_int(method, "methodId"), Some(2 | 256)) {
        return Err(Error::vit1(
            "this body is the getVciProgrammingData request, method 2 or 256",
        ));
    }
    let sequence = controller_with_read(controller, attributes)?;
    let mut body = Map::new();
    body.insert(
        "clientState".to_owned(),
        Value::Object(document(client_state, "clientState")?),
    );
    body.insert(
        "spsVin".to_owned(),
        Value::Object(document(sps_vin, "spsVin")?),
    );
    body.insert(
        "method".to_owned(),
        Value::Object(document(method, "method")?),
    );
    body.insert("controller".to_owned(), sequence);
    body.insert(
        "functionSteps".to_owned(),
        step_list(function_steps, "functionSteps")?,
    );
    body.insert("vciVOList".to_owned(), step_list(vci_steps, "vciVOList")?);
    Ok(Value::Object(body))
}

fn step_list(steps: Option<&[Value]>, label: &str) -> Result<Value> {
    let items: Vec<Value> = steps
        .unwrap_or(&[])
        .iter()
        .map(|item| document(item, label).map(Value::Object))
        .collect::<Result<_>>()?;
    Ok(Value::Array(items))
}

fn controller_with_read(controller: &Value, pairs: &[Attr]) -> Result<Value> {
    let rule = rule_for(controller)?;
    let count = |target: &str| pairs.iter().filter(|(name, _)| name == target).count();
    let cvn_count = usize::from(rule.cvn);
    let vin_count = usize::from(rule.read_vin);
    let hardware_count = usize::from(rule.hardware_did.is_some());
    if count("vin") != vin_count
        || count("ssecuhn") != hardware_count
        || count("partno") != rule.part_dids.len()
    {
        if rule.code == "K17" {
            return Err(Error::vit1(
                "a K17 read is one vin, ten part numbers, and one ssecuhn",
            ));
        }
        return Err(Error::vit1(format!(
            "a {} read does not match its request method",
            rule.code
        )));
    }
    if count("cvn_in_vit1") != cvn_count {
        if rule.cvn {
            return Err(Error::vit1(format!(
                "{} stores cvn_in_vit1 as 1 or 0",
                rule.code
            )));
        }
        return Err(Error::vit1("CVN stays off this request"));
    }
    let cvn_values: Vec<&str> = pairs
        .iter()
        .filter(|(name, _)| name == "cvn_in_vit1")
        .map(|(_, value)| value.as_str())
        .collect();
    let cvn_is_one = cvn_values.len() == 1 && cvn_values[0] == "1";
    let partnum_count = count("partnum");
    if cvn_is_one && partnum_count == 0 {
        return Err(Error::vit1("cvn_in_vit1 1 carries at least one partnum"));
    }
    if !cvn_is_one && partnum_count > 0 {
        return Err(Error::vit1("partnum belongs with cvn_in_vit1 1"));
    }
    if pairs
        .iter()
        .any(|(name, _)| SECURITY.contains(&name.as_str()))
    {
        return Err(Error::vit1("security access stays off this request"));
    }
    for (name, value) in pairs {
        match name.as_str() {
            "vin" => {
                vin_checked(value)?;
            }
            "partno" if !is_decimal(value) => {
                return Err(Error::vit1(
                    "a partno is the decimal from 4 bytes of the part DID",
                ));
            }
            "ssecuhn" if value.is_empty() => {
                return Err(Error::vit1("ssecuhn is the hardware id from the read"));
            }
            "cvn_in_vit1" if value != "0" && value != "1" => {
                return Err(Error::vit1("cvn_in_vit1 is 1 or 0"));
            }
            "partnum" => {
                check_partnum(value)?;
            }
            "controller_supported" if value == "0" => {
                return Err(Error::vit1(
                    "the module read says the controller is unsupported",
                ));
            }
            _ => {}
        }
    }
    let vit1 = build_vit1(pairs);
    if !has_control_module_block(&vit1) {
        return Err(Error::vit1(
            "the module read did not produce a control-module block",
        ));
    }
    let mut sequence = document(controller, "controller")?;
    sequence.insert("vit1".to_owned(), vit1);
    Ok(Value::Object(sequence))
}

fn has_control_module_block(vit1: &Value) -> bool {
    let Some(blocks) = vit1.get("cmbs").and_then(Value::as_array) else {
        return false;
    };
    let Some(first) = blocks.first().and_then(Value::as_object) else {
        return false;
    };
    matches!(first.get("vitAttrs"), Some(Value::Array(a)) if !a.is_empty())
}

fn rule_for(controller: &Value) -> Result<&'static ReadRule> {
    let device_id = field_as_int(controller, "deviceId");
    let method_id = field(controller, "requestMethod")
        .and_then(Value::as_object)
        .and_then(|rm| py_get(rm, "reqMethodID"))
        .and_then(as_int);
    RULES
        .iter()
        .find(|rule| device_id == Some(rule.device_id) && method_id == Some(rule.request_method))
        .ok_or_else(|| Error::vit1("this controller is not a saved-read rule"))
}

// ------------------------------------------------------------------ the screens after a response

/// Whether `needsVIT1` reads this sequence before the programming-data post.
///
/// Device 252 is not read itself; each value of `mapOfControllers` is. Any other device is read
/// when `vit1` is missing or its header `vitAttrs` is empty. Blocks on `cmbs` do not count.
///
/// # Errors
/// Returns [`Error::Vit1`] on a malformed document (a non-integer device id, a missing map).
pub fn needs_vit1(controller: &Value) -> Result<bool> {
    needs_vit1_doc(&document(controller, "controller")?)
}

fn needs_vit1_doc(document: &Obj) -> Result<bool> {
    let device = py_get(document, "deviceId")
        .and_then(as_int)
        .ok_or_else(|| Error::vit1("controller deviceId is not an integer"))?;
    if device != 252 && header_empty(py_get(document, "vit1"))? {
        return Ok(true);
    }
    let Some(children) = py_get(document, "mapOfControllers") else {
        return Err(Error::vit1("mapOfControllers is null"));
    };
    let Some(map) = children.as_object() else {
        return Err(Error::vit1("mapOfControllers is not a map"));
    };
    for child in map.values() {
        let Some(child_obj) = child.as_object() else {
            return Err(Error::vit1("mapOfControllers value is not a controller"));
        };
        if needs_vit1_doc(child_obj)? {
            return Ok(true);
        }
    }
    Ok(false)
}

fn header_empty(vit1: Option<&Value>) -> Result<bool> {
    let Some(vit1) = vit1 else {
        return Ok(true);
    };
    let Some(obj) = vit1.as_object() else {
        return Err(Error::vit1("vit1 is not a document"));
    };
    match py_get(obj, "vitAttrs") {
        Some(Value::Array(a)) => Ok(a.is_empty()),
        _ => Err(Error::vit1("vitAttrs is null")),
    }
}

/// The root messages that open the pre-communication screen.
///
/// `preCommunicationMessages` is this list on the root. A missing, null, or empty list returns
/// `None`. A non-empty list is what opens `PRE_PROGRAMMING_INSTRUCTIONS`.
///
/// # Errors
/// Returns [`Error::Vit1`] when the key is present but not a list.
pub fn pre_communication_messages(controller: &Value) -> Result<Option<Vec<Value>>> {
    let document = document(controller, "controller")?;
    match py_get(&document, "preCommunicationMessages") {
        None => Ok(None),
        Some(Value::Array(a)) if a.is_empty() => Ok(None),
        Some(Value::Array(a)) => Ok(Some(a.clone())),
        Some(_) => Err(Error::vit1("preCommunicationMessages is not a list")),
    }
}

/// The root after a non-GSPAS `/getSelectedController` response.
///
/// One controller replaces the root; a `vit1` on `current` is not copied onto it. More than one
/// controller with a populated option composite stops on the options screen (`None`). More than one
/// with an empty composite keeps `current`.
///
/// # Errors
/// Returns [`Error::Vit1`] when there is no controller, or a document is malformed.
pub fn after_selected_controller(
    current: &Value,
    controllers: &[Value],
    composite_populated: bool,
) -> Result<Option<Value>> {
    if controllers.is_empty() {
        return Err(Error::vit1(
            "the selected-controller response has no controller",
        ));
    }
    if controllers.len() > 1 && composite_populated {
        return Ok(None);
    }
    if controllers.len() == 1 {
        return Ok(Some(Value::Object(document(
            &controllers[0],
            "controller",
        )?)));
    }
    Ok(Some(Value::Object(document(current, "controller")?)))
}

/// The root after `/getProgrammingData` returns.
///
/// A failed body, including `VIT_NO_VALID_CMB`, errors here and the posted controller stays. A
/// success returns the response `controller` alone.
///
/// # Errors
/// Returns [`Error::Vit1`] with the error code when `success` is not `true`, or there is no
/// controller.
pub fn after_programming_data(response: &Value) -> Result<Value> {
    let doc = document(response, "response")?;
    if py_get(&doc, "success") != Some(&Value::Bool(true)) {
        if let Some(Value::String(code)) = py_get(&doc, "errorCode") {
            if !code.is_empty() {
                return Err(Error::vit1(code.clone()));
            }
        }
        return Err(Error::vit1("the programming-data response failed"));
    }
    match py_get(&doc, "controller") {
        Some(v) if v.is_object() => Ok(Value::Object(document(v, "controller")?)),
        _ => Err(Error::vit1(
            "the programming-data response has no controller",
        )),
    }
}

/// The sequences checked for `programmingData` before a security screen.
///
/// Device 252 is a container; each value of `mapOfControllers` is walked. Any other device is one
/// sequence when that map is missing or empty and `skipSameCalibration` is not true.
///
/// # Errors
/// Returns [`Error::Vit1`] (`NO_CALIBRATIONS_SUPPORTED`) when a sequence has no `programmingData`,
/// or on a malformed document.
pub fn sequences_after_programming_data(controller: &Value) -> Result<Vec<Value>> {
    let found = programming_sequences(&document(controller, "controller")?)?;
    for seq in &found {
        if py_get(seq, "programmingData").is_none() {
            return Err(Error::vit1("NO_CALIBRATIONS_SUPPORTED"));
        }
    }
    Ok(found.into_iter().map(Value::Object).collect())
}

fn programming_sequences(document: &Obj) -> Result<Vec<Obj>> {
    let device = py_get(document, "deviceId")
        .and_then(as_int)
        .ok_or_else(|| Error::vit1("controller deviceId is not an integer"))?;
    let children = py_get(document, "mapOfControllers");
    let empty = match children {
        None => true,
        Some(v) => match v.as_object() {
            Some(m) => m.is_empty(),
            None => return Err(Error::vit1("mapOfControllers is not a map")),
        },
    };
    if device != 252 {
        let skip = match document.get("skipSameCalibration") {
            None => false,
            Some(Value::Bool(b)) => *b,
            Some(_) => return Err(Error::vit1("skipSameCalibration is not a boolean")),
        };
        if empty && !skip {
            return Ok(vec![document.clone()]);
        }
        return Ok(Vec::new());
    }
    if empty {
        return Ok(Vec::new());
    }
    let Some(map) = children.and_then(Value::as_object) else {
        return Ok(Vec::new());
    };
    let mut found: Vec<Obj> = Vec::new();
    for child in map.values() {
        let Some(child_obj) = child.as_object() else {
            return Err(Error::vit1("mapOfControllers value is not a controller"));
        };
        found.extend(programming_sequences(child_obj)?);
    }
    Ok(found)
}

/// The loop in `handleNormalAfterProgrammingData` before any security screen.
///
/// A null `vit1` on a device other than 253 is read before the later tests. Pre-programming
/// instructions on the root or the current sequence suppress the two errors below. An `id` of 10
/// errors as unauthored data. An empty `listOfModules` with a first block that carries a `partno`
/// errors.
///
/// # Errors
/// Returns [`Error::Vit1`] for the null-vit1, unauthored-id, or no-modules conditions.
pub fn normal_programming_data_loop(
    sequences: &[Value],
    root: &Value,
    current: Option<&Value>,
) -> Result<()> {
    let root_document = document(root, "controller")?;
    let current_document = current.map(|c| document(c, "controller")).transpose()?;
    let suppressed = has_pre_programming_instructions(&root_document)?
        || match &current_document {
            Some(d) => has_pre_programming_instructions(d)?,
            None => false,
        };
    for seq in sequences {
        let doc = document(seq, "controller")?;
        if py_get(&doc, "vit1").is_none() && py_get(&doc, "deviceId").and_then(as_int) != Some(253)
        {
            return Err(Error::vit1("a null vit1 is read before the module test"));
        }
        if suppressed {
            continue;
        }
        let data = py_get(&doc, "programmingData").and_then(Value::as_object);
        if let Some(obj) = data {
            if py_get(obj, "id").and_then(as_int) == Some(10) {
                return Err(Error::vit1(
                    "VCI id of 10 indicates that the data is not authored, and is only for testing purposes",
                ));
            }
        }
        if py_get(&doc, "mcvmProgramming").is_some() {
            continue;
        }
        let Some(data_obj) = data else {
            continue;
        };
        if !modules_empty(data_obj)? || !empty_modules_are_unsupported(py_get(&doc, "vit1"))? {
            continue;
        }
        return Err(Error::vit1("No modules found in programming data"));
    }
    Ok(())
}

fn modules_empty(data: &Obj) -> Result<bool> {
    match py_get(data, "listOfModules") {
        None => Ok(true),
        Some(Value::Array(a)) => Ok(a.is_empty()),
        Some(_) => Err(Error::vit1("listOfModules is not a list")),
    }
}

fn empty_modules_are_unsupported(vit1: Option<&Value>) -> Result<bool> {
    let Some(vit1) = vit1 else {
        return Ok(true);
    };
    let Some(obj) = vit1.as_object() else {
        return Err(Error::vit1("vit1 is not a document"));
    };
    let Some(Value::Array(blocks)) = py_get(obj, "cmbs") else {
        return Err(Error::vit1("vit1 cmbs is not a list"));
    };
    if blocks.is_empty() {
        return Ok(true);
    }
    if matches!(blocks[0], Value::Null) {
        return Ok(false);
    }
    let Some(first) = blocks[0].as_object() else {
        return Err(Error::vit1("control module block is not a document"));
    };
    let Some(Value::Array(pairs)) = py_get(first, "vitAttrs") else {
        return Err(Error::vit1("vitAttrs is not a list"));
    };
    for pair in pairs {
        let Some(p) = pair.as_object() else {
            return Err(Error::vit1("vit attribute is not a pair"));
        };
        if py_get(p, "key") == Some(&Value::String("partno".to_owned())) {
            return Ok(true);
        }
    }
    Ok(false)
}

const PROGRAMMING_METHOD_CONTINUES: [i64; 10] = [1, 2, 16, 32, 64, 128, 256, 2048, 4096, 8192];
const PROGRAMMING_METHOD_FILE: [i64; 2] = [4, 512];
const PROGRAMMING_METHOD_RECONFIGURE: [i64; 2] = [8, 1024];

/// The method switch at the end of `handleNormalAfterProgrammingData`.
///
/// `None` is the ten continuing methods. File ids 4 and 512 share `file.is.not.supported`.
/// Reconfigure ids 8 and 1024 share `reconfiguration.is.not.supported.yet`. Anything else is
/// `no.valid.programming.method.found`.
#[must_use]
pub fn programming_method_screen(method_id: i64) -> Option<&'static str> {
    if PROGRAMMING_METHOD_CONTINUES.contains(&method_id) {
        None
    } else if PROGRAMMING_METHOD_FILE.contains(&method_id) {
        Some("file.is.not.supported")
    } else if PROGRAMMING_METHOD_RECONFIGURE.contains(&method_id) {
        Some("reconfiguration.is.not.supported.yet")
    } else {
        Some("no.valid.programming.method.found")
    }
}

/// The switch in `handleNextScreenAfterCalibrationSelection`.
///
/// Reached when hardware selection and calibration selection were not opened. No calibration is
/// downloaded; the function names the next screen or task.
///
/// # Errors
/// Returns [`Error::Vit1`] on a malformed sequence or instruction document.
pub fn after_calibration_selection(
    method_id: i64,
    unauthored: bool,
    sequences: &[Value],
    current: Option<&Value>,
    root: Option<&Value>,
) -> Result<String> {
    let known = PROGRAMMING_METHOD_CONTINUES.contains(&method_id)
        || PROGRAMMING_METHOD_FILE.contains(&method_id)
        || PROGRAMMING_METHOD_RECONFIGURE.contains(&method_id);
    if !known {
        return Ok("no.method.found".to_owned());
    }
    if [2, 256].contains(&method_id) {
        return Ok("CALIBRATION_SUMMARY".to_owned());
    }
    if [16, 32, 2048, 4096].contains(&method_id) {
        if !unauthored {
            return Ok("LOAD_USB_DRIVES_TASK".to_owned());
        }
        return instruction_screen(current, root, true);
    }
    if [64, 8192].contains(&method_id) {
        return Ok("mcvm.is.not.supported".to_owned());
    }
    if [1, 128].contains(&method_id) {
        if calibration_summary_needed(sequences)? {
            return Ok("CALIBRATION_SUMMARY".to_owned());
        }
        return instruction_screen(current, root, unauthored);
    }
    Ok(match method_id {
        4 => "file.is.not.supported",
        512 => "file.bsc.is.not.supported",
        8 => "reconfiguration.is.not.supported.yet",
        _ => "reconfiguration.bsc.is.not.supported.yet",
    }
    .to_owned())
}

fn instruction_screen(
    current: Option<&Value>,
    root: Option<&Value>,
    unauthored: bool,
) -> Result<String> {
    let current_document = current.map(|c| document(c, "controller")).transpose()?;
    let root_document = root.map(|r| document(r, "controller")).transpose()?;
    if let Some(d) = &current_document {
        if has_pre_programming_instructions(d)? {
            return Ok("PRE_PROGRAMMING_INSTRUCTIONS".to_owned());
        }
    }
    if let Some(d) = &root_document {
        if has_pre_programming_instructions(d)? {
            return Ok("PRE_PROGRAMMING_INSTRUCTIONS".to_owned());
        }
    }
    if unauthored {
        return Ok("sps.exception.no-valid-cop".to_owned());
    }
    Ok("handleSequenceReprogramming".to_owned())
}

fn calibration_summary_needed(sequences: &[Value]) -> Result<bool> {
    for seq in sequences {
        let doc = document(seq, "controller")?;
        let Some(data) = py_get(&doc, "programmingData").and_then(Value::as_object) else {
            return Err(Error::vit1("the sequence has no programmingData"));
        };
        if filled(py_get(data, "listOfModules"), "listOfModules")?
            && filled(
                py_get(&doc, "displayablePartsToInstall"),
                "displayablePartsToInstall",
            )?
        {
            return Ok(true);
        }
    }
    Ok(false)
}

fn filled(value: Option<&Value>, label: &str) -> Result<bool> {
    match value {
        None => Ok(false),
        Some(Value::Array(a)) => Ok(!a.is_empty()),
        Some(_) => Err(Error::vit1(format!("{label} is not a list"))),
    }
}

fn has_pre_programming_instructions(document: &Obj) -> Result<bool> {
    match py_get(document, "preProgrammingInstructions") {
        None => Ok(false),
        Some(Value::Array(a)) => Ok(!a.is_empty()),
        Some(_) => Err(Error::vit1("preProgrammingInstructions is not a list")),
    }
}

/// `calSelectionNeeded` for programming data whose `type` is `VCI`.
///
/// A GME adapter returns false, as do an empty list and a list whose devices are all 253. A VCI
/// sequence returns true when the part lists are missing or empty and `listOfModules` is non-empty.
///
/// # Errors
/// Returns [`Error::Vit1`] when the programming-data type is not `VCI`, or a list is malformed.
pub fn calibration_selection_needed(sequences: &[Value], gme: bool) -> Result<bool> {
    if gme {
        return Ok(false);
    }
    let documents: Vec<Obj> = sequences
        .iter()
        .map(|s| document(s, "controller"))
        .collect::<Result<_>>()?;
    if all_device_253(&documents)? {
        return Ok(false);
    }
    for doc in &documents {
        let Some(data_obj) = py_get(doc, "programmingData")
            .and_then(Value::as_object)
            .filter(|d| py_get(d, "type") == Some(&Value::String("VCI".to_owned())))
        else {
            return Err(Error::vit1("programmingData type is not VCI"));
        };
        if filled(py_get(doc, "partsToInstall"), "partsToInstall")?
            && filled(
                py_get(doc, "displayablePartsToInstall"),
                "displayablePartsToInstall",
            )?
        {
            continue;
        }
        match py_get(data_obj, "listOfModules") {
            Some(Value::Array(a)) => {
                if !a.is_empty() {
                    return Ok(true);
                }
            }
            _ => return Err(Error::vit1("listOfModules is null")),
        }
    }
    Ok(false)
}

fn all_device_253(documents: &[Obj]) -> Result<bool> {
    if documents.is_empty() {
        return Ok(true);
    }
    for d in documents {
        if py_get(d, "deviceId").and_then(as_int).is_none() {
            return Err(Error::vit1("controller deviceId is not an integer"));
        }
    }
    Ok(documents
        .iter()
        .all(|d| py_get(d, "deviceId").and_then(as_int) == Some(253)))
}

/// The task `handleSequenceReprogramming` would start.
///
/// The function returns that task's name and does not download a calibration or reprogram a
/// controller.
///
/// # Errors
/// Returns [`Error::Vit1`] on a null `programmingDataUnits`/`partsToInstall`, or a null root when a
/// method is present.
pub fn sequence_reprogramming(
    sequences: &[Value],
    method_present: bool,
    root: Option<&Value>,
) -> Result<String> {
    let documents: Vec<Obj> = sequences
        .iter()
        .map(|s| document(s, "controller"))
        .collect::<Result<_>>()?;
    if !documents.is_empty() && !pure_mcvm(&documents[0])? {
        for doc in &documents {
            if is_skipped(doc)? {
                continue;
            }
            let Some(Value::Array(units)) = py_get(doc, "programmingDataUnits") else {
                return Err(Error::vit1("programmingDataUnits is null"));
            };
            let Some(Value::Array(parts)) = py_get(doc, "partsToInstall") else {
                return Err(Error::vit1("partsToInstall is null"));
            };
            if units.is_empty() && !parts.is_empty() {
                return Ok("DOWNLOAD_PROG_FILES_TASK".to_owned());
            }
        }
        return Ok("REPROGRAM_VEHICLE_TASK".to_owned());
    }
    if method_present && root.is_none() {
        return Err(Error::vit1("the root is null"));
    }
    let root_document = root.map(|r| document(r, "controller")).transpose()?;
    let root_mcvm = root_document
        .as_ref()
        .is_some_and(|d| py_get(d, "mcvmProgramming").is_some());
    if (method_present && root_mcvm) || (!documents.is_empty() && pure_mcvm(&documents[0])?) {
        return Ok("CHARACTERIZE_DATA_TASK".to_owned());
    }
    if method_present {
        return Ok("WARRANTY_CLAIM_TASK".to_owned());
    }
    Ok("ToolLock.unlock".to_owned())
}

fn pure_mcvm(document: &Obj) -> Result<bool> {
    if py_get(document, "mcvmProgramming").is_none() {
        return Ok(false);
    }
    let Some(data) = py_get(document, "programmingData").and_then(Value::as_object) else {
        return Err(Error::vit1("the sequence has no programmingData"));
    };
    match py_get(data, "listOfModules") {
        None => Ok(true),
        Some(Value::Array(a)) => Ok(a.is_empty()),
        Some(_) => Err(Error::vit1("listOfModules is not a list")),
    }
}

fn is_skipped(document: &Obj) -> Result<bool> {
    match document.get("skipped") {
        None => Ok(false),
        Some(Value::Bool(b)) => Ok(*b),
        Some(_) => Err(Error::vit1("skipped is not a boolean")),
    }
}
