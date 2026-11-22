//! Shared fixtures for the integration tests.
//!
//! The payloads and part numbers here are synthetic. The catalog part numbers the real brake
//! sequence would suggest are listed in [`CATALOG_PARTS`] only so each test can assert they never
//! leak into a request body; no fixture is built from them.

#![allow(dead_code)]

use std::collections::BTreeMap;

use serde_json::{Value, json};
use spskit::vit1::Attr;

/// A synthetic VIN that passes `check_vin`.
pub const VIN: &str = "1G1TE5TVN00000001";

/// The ten plain part identifiers.
pub const PART_DIDS: [&str; 10] = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA"];

/// Catalog suggestions for the brake sequence. No fixture may use them; tests assert their absence.
pub const CATALOG_PARTS: [&str; 8] = [
    "23394159", "23394161", "84131365", "23394158", "23394157", "23394136", "23394154", "23394155",
];

/// `[0xFF]` (the DID echo) followed by `number` as four big-endian bytes.
#[must_use]
pub fn payload(number: u32) -> Vec<u8> {
    let mut bytes = vec![0xFF];
    bytes.extend_from_slice(&number.to_be_bytes());
    bytes
}

/// One payload per part DID, numbered 1..=10.
#[must_use]
pub fn parts() -> BTreeMap<String, Vec<u8>> {
    dids_payloads(&PART_DIDS)
}

/// One payload per given DID, numbered 1..=n in order.
#[must_use]
pub fn dids_payloads(dids: &[&str]) -> BTreeMap<String, Vec<u8>> {
    dids.iter()
        .enumerate()
        .map(|(index, did)| ((*did).to_owned(), payload((index + 1) as u32)))
        .collect()
}

/// Attribute pairs from string literals.
#[must_use]
pub fn pairs(items: &[(&str, &str)]) -> Vec<Attr> {
    items
        .iter()
        .map(|(key, value)| ((*key).to_owned(), (*value).to_owned()))
        .collect()
}

#[must_use]
pub fn client() -> Value {
    json!({ "sessionID": "", "vin": VIN, "isTLC": true })
}

#[must_use]
pub fn sps_vin() -> Value {
    json!({ "type": "NAOVin", "vin": VIN })
}

#[must_use]
pub fn method128() -> Value {
    json!({ "methodId": 128, "description": "Normal", "blockSameCal": true })
}

#[must_use]
pub fn options() -> Value {
    json!({
        "type": "ProductionOptionComposite",
        "currentSelectionIdx": 0,
        "selectedCodes": [],
        "options": [],
    })
}

/// The K17 controller fixture.
#[must_use]
pub fn controller_k17() -> Value {
    json!({
        "deviceId": 40,
        "displayName": {
            "controllerCode": "K17",
            "controllerLabel": "Electronic Brake Control Module",
            "displayOrder": 0,
        },
        "requestMethod": {
            "reqMethodID": 11228,
            "deviceID": 40,
            "vinAddresses": "90",
            "partAddresses": "C1,C2,C3,C4,C5,C6,C7,C8,C9,CA",
            "partLength": "4",
            "partStartByte": "1",
            "hardwareIdAddresses": "CC",
            "hardwareIdLength": 0,
            "hardwareIdStartByte": 0,
            "readVIN": 1,
            "readParts": 1,
            "readHardwareId": 1,
            "readCvn": 0,
            "readSecuritySeed": 1,
        },
        "secCodeRequired": true,
    })
}

/// A controller fixture for a sibling code/request method (`_controller` in the Python tests).
#[must_use]
pub fn controller(
    code: &str,
    device_id: i64,
    request_method: i64,
    part_addresses: &str,
    read_cvn: i64,
) -> Value {
    json!({
        "deviceId": device_id,
        "displayName": { "controllerCode": code, "controllerLabel": code, "displayOrder": 0 },
        "requestMethod": {
            "reqMethodID": request_method,
            "deviceID": device_id,
            "vinAddresses": "90",
            "partAddresses": part_addresses,
            "partLength": "4",
            "partStartByte": "1",
            "hardwareIdAddresses": "CC",
            "readVIN": 1,
            "readParts": 1,
            "readHardwareId": 1,
            "readCvn": read_cvn,
            "readSecuritySeed": 1,
        },
        "secCodeRequired": true,
    })
}

/// Whether `encoded` contains none of the catalog part numbers.
#[must_use]
pub fn no_catalog_parts(encoded: &str) -> bool {
    CATALOG_PARTS.iter().all(|part| !encoded.contains(part))
}
