//! Turn a captured voltkit clone-profile read into a VIT1 programming-data request.
//!
//! `voltkit profile ... --clone` writes a module read as `ecu`/`did`/`lid` text. This module maps
//! one controller's saved read onto the inputs [`crate::vit1`] expects and returns the VIT1
//! control-module block, or the whole `getProgrammingData` body when a request template carries the
//! catalog documents.
//!
//! It is an offline transform: a captured file and a VIN in, a request body out. It does not import
//! voltkit, open a socket, post to TDS, read a dongle, or program a vehicle. The deliberate gaps
//! stay: K16 and K73 request methods 520 and 566 have no saved-read rule, so [`crate::vit1::read_shape`]
//! refuses them; method 601 is K73's rule.

use std::collections::BTreeMap;

use serde_json::{Map, Value, json};

use crate::error::{Error, Result};
use crate::vit1::{
    Attr, Hardware, ReadShape, build_vit1, module_attributes, programming_data_request, read_shape,
    vci_programming_data_request,
};

const PRINTABLE: std::ops::Range<u8> = 0x20..0x7F;

/// One `ecu` block of a clone profile: its `$1A` lids and `$22` dids.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CloneBlock {
    /// The controller name on the `ecu` line.
    pub ecu: String,
    /// The `$1A` reads, keyed by identifier.
    pub lids: BTreeMap<String, Vec<u8>>,
    /// The `$22` reads, keyed by identifier.
    pub dids: BTreeMap<String, Vec<u8>>,
}

impl CloneBlock {
    fn new(ecu: &str) -> Self {
        Self {
            ecu: ecu.to_owned(),
            lids: BTreeMap::new(),
            dids: BTreeMap::new(),
        }
    }
}

/// Group the `did`/`lid` lines of a clone profile under their `ecu` block, in capture order.
///
/// Comment lines, the `s3` timing line, and reads printed before any `ecu` line are skipped. Each
/// value is the hex after the identifier, the data the module answered after the service byte and
/// the identifier.
///
/// # Errors
/// Returns [`Error::Handoff`] on a duplicate `ecu`, a repeated identifier with two values, or a
/// non-hex value.
pub fn parse_clone_profile(text: &str) -> Result<Vec<CloneBlock>> {
    let mut blocks: Vec<CloneBlock> = Vec::new();
    let mut current: Option<usize> = None;
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let parts: Vec<&str> = line.split_whitespace().collect();
        let tag = parts[0];
        if tag == "ecu" {
            current = Some(begin_block(&parts, &mut blocks)?);
            continue;
        }
        if tag != "lid" && tag != "did" {
            continue;
        }
        let Some(idx) = current else {
            continue;
        };
        let (ident, value) = read_line(&parts)?;
        let block = &mut blocks[idx];
        let table = if tag == "lid" {
            &mut block.lids
        } else {
            &mut block.dids
        };
        if let Some(existing) = table.get(&ident) {
            if existing != &value {
                return Err(Error::handoff(format!(
                    "the {} read gives {tag} {ident} two different values",
                    block.ecu
                )));
            }
        }
        table.insert(ident, value);
    }
    Ok(blocks)
}

fn begin_block(parts: &[&str], blocks: &mut Vec<CloneBlock>) -> Result<usize> {
    if parts.len() < 2 {
        return Err(Error::handoff("an ecu line names no controller"));
    }
    let name = parts[1];
    if blocks.iter().any(|b| b.ecu == name) {
        return Err(Error::handoff(format!(
            "the capture names ecu {name} twice"
        )));
    }
    blocks.push(CloneBlock::new(name));
    Ok(blocks.len() - 1)
}

fn read_line(parts: &[&str]) -> Result<(String, Vec<u8>)> {
    if parts.len() < 2 {
        return Err(Error::handoff(format!(
            "a {} line names no identifier",
            parts[0]
        )));
    }
    let ident = parts[1].to_uppercase();
    let token = if parts.len() >= 3 && !parts[2].starts_with('#') {
        parts[2]
    } else {
        ""
    };
    match hex_decode(token) {
        Some(bytes) => Ok((ident, bytes)),
        None => Err(Error::handoff(format!(
            "the {} {ident} line is not hex: {token:?}",
            parts[0]
        ))),
    }
}

fn hex_decode(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 || !s.is_ascii() {
        return None;
    }
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len() / 2);
    let mut i = 0;
    while i < bytes.len() {
        let hi = char::from(bytes[i]).to_digit(16)?;
        let lo = char::from(bytes[i + 1]).to_digit(16)?;
        out.push(u8::try_from(hi * 16 + lo).expect("two hex nibbles fit a byte"));
        i += 2;
    }
    Some(out)
}

/// Pair one controller's captured read into the attributes `build_vit1` walks.
///
/// # Errors
/// Returns an error when a part read is missing, the hardware flag and the capture disagree, or the
/// read does not match the rule.
pub fn attributes_for(
    block: &CloneBlock,
    shape: &ReadShape,
    vin: &str,
    ssecuhn: Option<&str>,
    cvn: Option<&str>,
    partnums: &[String],
) -> Result<Vec<Attr>> {
    let mut parts: BTreeMap<String, Vec<u8>> = BTreeMap::new();
    for did in &shape.part_dids {
        parts.insert(did.clone(), part_payload(block, did)?);
    }
    let hardware = hardware(block, shape, ssecuhn)?;
    let (cvn_value, partnum_values) = cvn_for(shape, cvn, partnums)?;
    module_attributes(
        &shape.code,
        vin,
        &parts,
        hardware,
        cvn_value.as_deref(),
        &partnum_values,
    )
}

/// The VIT1 control-module block a captured read becomes, with its attributes.
///
/// The result is self-describing: the controller code, its device and request method, the resolved
/// VIN, the attribute pairs, and the `vit1` document `build_vit1` produces.
///
/// # Errors
/// Returns an error when the code has no rule, the capture does not supply a required read, or the
/// VIN is wrong for the controller.
pub fn vit1_from_read(
    text: &str,
    code: &str,
    vin: &str,
    ecu: Option<&str>,
    ssecuhn: Option<&str>,
    cvn: Option<&str>,
    partnums: &[String],
) -> Result<Value> {
    let shape = read_shape(code)?;
    let blocks = parse_clone_profile(text)?;
    let block = select_block(&blocks, ecu)?;
    let resolved_vin = vin_for(&shape, vin)?;
    let attributes = attributes_for(block, &shape, resolved_vin, ssecuhn, cvn, partnums)?;
    let mut envelope = Map::new();
    envelope.insert("code".to_owned(), Value::String(shape.code.clone()));
    envelope.insert("deviceId".to_owned(), Value::from(shape.device_id));
    envelope.insert(
        "requestMethod".to_owned(),
        Value::from(shape.request_method),
    );
    envelope.insert("ecu".to_owned(), Value::String(block.ecu.clone()));
    if shape.reads_vin {
        envelope.insert("vin".to_owned(), Value::String(resolved_vin.to_owned()));
    }
    envelope.insert(
        "attributes".to_owned(),
        Value::Array(
            attributes
                .iter()
                .map(|(name, value)| json!([name, value]))
                .collect(),
        ),
    );
    envelope.insert("vit1".to_owned(), build_vit1(&attributes));
    Ok(Value::Object(envelope))
}

/// The whole getProgrammingData body for a captured read and a catalog template.
///
/// `template` carries the documents the catalog supplies. The captured read is attached as the
/// controller's `vit1`. Method 2 and 256 take the VCI body and copy the template's step lists.
///
/// # Errors
/// Returns an error when the template is not an object, a required document is missing, or the
/// method is not 1, 2, 128, or 256.
#[allow(clippy::too_many_arguments)]
pub fn request_from_read(
    text: &str,
    template: &Value,
    code: &str,
    vin: &str,
    ecu: Option<&str>,
    ssecuhn: Option<&str>,
    cvn: Option<&str>,
    partnums: &[String],
) -> Result<Value> {
    let shape = read_shape(code)?;
    let blocks = parse_clone_profile(text)?;
    let block = select_block(&blocks, ecu)?;
    let resolved_vin = vin_for(&shape, vin)?;
    let attributes = attributes_for(block, &shape, resolved_vin, ssecuhn, cvn, partnums)?;
    let Some(obj) = template.as_object() else {
        return Err(Error::handoff("the request template is not an object"));
    };
    let method = template_object(obj, "method")?;
    let method_id = method
        .as_object()
        .and_then(|m| m.get("methodId"))
        .and_then(Value::as_i64);
    let client_state = template_object(obj, "clientState")?;
    let sps_vin = template_object(obj, "spsVin")?;
    let controller = template_object(obj, "controller")?;
    match method_id {
        Some(1 | 128) => {
            let option_composite = template_object(obj, "optionComposite")?;
            programming_data_request(
                client_state,
                sps_vin,
                method,
                controller,
                option_composite,
                &attributes,
            )
        }
        Some(2 | 256) => {
            let function_steps = step_values(obj.get("functionSteps"))?;
            let vci_steps = step_values(obj.get("vciVOList"))?;
            vci_programming_data_request(
                client_state,
                sps_vin,
                method,
                controller,
                &attributes,
                function_steps.as_deref(),
                vci_steps.as_deref(),
            )
        }
        _ => Err(Error::handoff(
            "the template method is not 1, 2, 128, or 256",
        )),
    }
}

fn template_object<'a>(obj: &'a Map<String, Value>, key: &str) -> Result<&'a Value> {
    match obj.get(key) {
        Some(v) if v.is_object() => Ok(v),
        _ => Err(Error::handoff(format!(
            "the request template has no {key} object"
        ))),
    }
}

fn step_values(value: Option<&Value>) -> Result<Option<Vec<Value>>> {
    let value = match value {
        None | Some(Value::Null) => return Ok(None),
        Some(v) => v,
    };
    let Some(arr) = value.as_array() else {
        return Err(Error::handoff("a template step list is a list of objects"));
    };
    let mut steps = Vec::with_capacity(arr.len());
    for item in arr {
        if !item.is_object() {
            return Err(Error::handoff("a template step is not an object"));
        }
        steps.push(item.clone());
    }
    Ok(Some(steps))
}

fn block_names(blocks: &[CloneBlock]) -> String {
    blocks
        .iter()
        .map(|b| b.ecu.as_str())
        .collect::<Vec<_>>()
        .join(", ")
}

fn select_block<'a>(blocks: &'a [CloneBlock], ecu: Option<&str>) -> Result<&'a CloneBlock> {
    if blocks.is_empty() {
        return Err(Error::handoff(
            "the capture has no ecu block with a module read",
        ));
    }
    if let Some(name) = ecu {
        return blocks.iter().find(|b| b.ecu == name).ok_or_else(|| {
            Error::handoff(format!(
                "the capture has no ecu {name}; it has {}",
                block_names(blocks)
            ))
        });
    }
    if blocks.len() > 1 {
        return Err(Error::handoff(format!(
            "the capture has more than one ecu; choose one with --ecu from {}",
            block_names(blocks)
        )));
    }
    Ok(&blocks[0])
}

fn part_payload(block: &CloneBlock, did: &str) -> Result<Vec<u8>> {
    let Some(value) = block.lids.get(&did.to_uppercase()) else {
        return Err(Error::handoff(format!(
            "the {} read has no lid {did} for a part number",
            block.ecu
        )));
    };
    let mut payload = vec![did_byte(did)?];
    payload.extend_from_slice(value);
    Ok(payload)
}

fn hardware(
    block: &CloneBlock,
    shape: &ReadShape,
    ssecuhn: Option<&str>,
) -> Result<Option<Hardware>> {
    let Some(hw_did) = shape.hardware_did.as_deref() else {
        if ssecuhn.is_some() {
            return Err(Error::handoff(format!(
                "{} does not read a hardware id",
                shape.code
            )));
        }
        return Ok(None);
    };
    if shape.hardware_decimal {
        if ssecuhn.is_some() {
            return Err(Error::handoff(format!(
                "{} reads a numeric hardware id, not a string; drop --ssecuhn",
                shape.code
            )));
        }
        let Some(value) = block.lids.get(&hw_did.to_uppercase()) else {
            return Err(Error::handoff(format!(
                "the {} read has no lid {hw_did} for the hardware id",
                block.ecu
            )));
        };
        let mut payload = vec![did_byte(hw_did)?];
        payload.extend_from_slice(value);
        return Ok(Some(Hardware::Decimal(payload)));
    }
    if let Some(given) = ssecuhn {
        return Ok(Some(Hardware::Text(given.to_owned())));
    }
    let Some(value) = block.lids.get(&hw_did.to_uppercase()) else {
        return Err(Error::handoff(format!(
            "the {} read has no lid {hw_did} for the hardware id; pass --ssecuhn",
            block.ecu
        )));
    };
    Ok(Some(Hardware::Text(ssecuhn_text(value))))
}

/// The hardware string for a length-0 read: the printable ASCII, else the hex.
fn ssecuhn_text(value: &[u8]) -> String {
    if !value.is_empty() && value.iter().all(|b| PRINTABLE.contains(b)) {
        value.iter().map(|&b| char::from(b)).collect()
    } else {
        use std::fmt::Write;
        value.iter().fold(String::new(), |mut acc, b| {
            let _ = write!(acc, "{b:02X}");
            acc
        })
    }
}

fn vin_for<'a>(shape: &ReadShape, vin: &'a str) -> Result<&'a str> {
    if shape.reads_vin {
        if vin.is_empty() {
            return Err(Error::handoff(format!(
                "{} reads a VIN; pass --vin",
                shape.code
            )));
        }
        return Ok(vin);
    }
    if !vin.is_empty() {
        return Err(Error::handoff(format!(
            "{} does not read a VIN; drop --vin",
            shape.code
        )));
    }
    Ok("")
}

fn cvn_for(
    shape: &ReadShape,
    cvn: Option<&str>,
    partnums: &[String],
) -> Result<(Option<String>, Vec<String>)> {
    if shape.reads_cvn {
        let value = cvn.unwrap_or("0").to_owned();
        return Ok((Some(value), partnums.to_vec()));
    }
    if cvn.is_some() || !partnums.is_empty() {
        return Err(Error::handoff(format!(
            "{} does not carry a CVN",
            shape.code
        )));
    }
    Ok((None, Vec::new()))
}

fn did_byte(did: &str) -> Result<u8> {
    u8::from_str_radix(did, 16)
        .map_err(|_| Error::handoff(format!("the identifier {did} is not a hex byte")))
}
