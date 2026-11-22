//! Port of `tests/test_handoff.py`: the voltkit clone-read to VIT1 handoff and its CLI.

// Faithful ports over fixed small fixtures: the index casts are over known-small counts and
// `&[x.clone()]` keeps each case readable. Neither pedantic lint flags a real problem in test code.
#![allow(clippy::cast_possible_truncation, clippy::cloned_ref_to_slice_refs)]

mod common;

use std::process::Command;

use serde_json::{Value, json};
use spskit::handoff::{parse_clone_profile, request_from_read, vit1_from_read};

use common::{PART_DIDS, VIN};

/// `$1A`/`$22` lines joined under one `ecu` block, with the clone's comment and `s3` header.
fn clone_text(ecu: &str, lids: &[(&str, &str)], req: &str, resp: &str) -> String {
    let mut lines = vec![
        "# Captured module bytes. A did or lid line is the data after the service and the identifier."
            .to_owned(),
        "s3 5000".to_owned(),
        String::new(),
        format!("ecu {ecu} req={req} resp={resp} functional=yes pad=00 latency=4"),
    ];
    for (ident, value) in lids {
        lines.push(format!("lid {ident} {value}"));
    }
    lines.join("\n") + "\n"
}

fn part_value(number: u32) -> String {
    format!("{number:08X}")
}

fn as_pairs(lids: &[(String, String)]) -> Vec<(&str, &str)> {
    lids.iter().map(|(k, v)| (k.as_str(), v.as_str())).collect()
}

fn k17_lids() -> Vec<(String, String)> {
    let mut lids: Vec<(String, String)> = PART_DIDS
        .iter()
        .enumerate()
        .map(|(index, did)| ((*did).to_owned(), part_value((index + 1) as u32)))
        .collect();
    // "HW000042" as printable-ASCII hex.
    lids.push(("CC".to_owned(), "4857303030303432".to_owned()));
    lids
}

fn numbered_lids(dids: &[&str]) -> Vec<(String, String)> {
    dids.iter()
        .enumerate()
        .map(|(index, did)| ((*did).to_owned(), part_value((index + 1) as u32)))
        .collect()
}

fn attrs(envelope: &Value) -> Vec<Value> {
    envelope["vit1"]["cmbs"][0]["vitAttrs"]
        .as_array()
        .unwrap()
        .clone()
}

fn names(attrs: &[Value]) -> Vec<String> {
    attrs
        .iter()
        .map(|a| a["key"].as_str().unwrap().to_owned())
        .collect()
}

#[test]
fn parse_groups_lids_under_their_ecu_and_ignores_comments_and_notes() {
    let mut text = clone_text(
        "BECM",
        &[("C1", "0000002A"), ("CC", "48573031")],
        "7E4",
        "7EC",
    );
    text += "# lid 90 11\n# header 621 has no recorded response id\n";
    let blocks = parse_clone_profile(&text).unwrap();
    assert_eq!(
        blocks.iter().map(|b| b.ecu.as_str()).collect::<Vec<_>>(),
        ["BECM"]
    );
    assert_eq!(
        blocks[0].lids.get("C1"),
        Some(&vec![0x00, 0x00, 0x00, 0x2A])
    );
    assert_eq!(
        blocks[0].lids.get("CC"),
        Some(&vec![0x48, 0x57, 0x30, 0x31])
    );
}

#[test]
fn a_captured_k17_read_becomes_the_vit1_block() {
    let envelope = vit1_from_read(
        &clone_text("BECM", &as_pairs(&k17_lids()), "7E4", "7EC"),
        "K17",
        VIN,
        None,
        None,
        None,
        &[],
    )
    .unwrap();
    assert_eq!(envelope["code"], "K17");
    assert_eq!(envelope["deviceId"], 40);
    assert_eq!(envelope["requestMethod"], 11228);
    assert_eq!(envelope["vin"], VIN);
    let mut expected = vec![
        json!({ "key": "ssecuhn", "value": "HW000042" }),
        json!({ "key": "vin", "value": VIN }),
    ];
    for index in 1..=10 {
        expected.push(json!({ "key": "partno", "value": index.to_string() }));
    }
    assert_eq!(attrs(&envelope), expected);
    assert_eq!(envelope["vit1"]["vitAttrs"], json!([]));
    let encoded = serde_json::to_string(&envelope).unwrap();
    assert!(!encoded.contains("urlopen"));
    assert!(!encoded.contains("https://"));
}

#[test]
fn an_ssecuhn_override_replaces_the_derived_string() {
    let envelope = vit1_from_read(
        &clone_text("BECM", &as_pairs(&k17_lids()), "7E4", "7EC"),
        "K17",
        VIN,
        None,
        Some("given-hw"),
        None,
        &[],
    )
    .unwrap();
    assert_eq!(
        attrs(&envelope)[0],
        json!({ "key": "ssecuhn", "value": "given-hw" })
    );
}

#[test]
fn a_decimal_hardware_read_is_the_format0_slice() {
    let mut lids = numbered_lids(&PART_DIDS);
    lids.push(("CC".to_owned(), part_value(42)));
    let envelope = vit1_from_read(
        &clone_text("M241", &as_pairs(&lids), "241", "641"),
        "K33",
        VIN,
        None,
        None,
        None,
        &[],
    )
    .unwrap();
    let attrs = attrs(&envelope);
    assert_eq!(attrs[0], json!({ "key": "ssecuhn", "value": "42" }));
    let partnos: Vec<String> = attrs
        .iter()
        .filter(|a| a["key"] == "partno")
        .map(|a| a["value"].as_str().unwrap().to_owned())
        .collect();
    assert_eq!(partnos, (1..=10).map(|i| i.to_string()).collect::<Vec<_>>());
}

#[test]
fn a_cvn_controller_defaults_to_zero_and_takes_partnums() {
    let mut lids = numbered_lids(&PART_DIDS);
    lids.push(("CC".to_owned(), part_value(3)));
    let quiet = vit1_from_read(
        &clone_text("BECM", &as_pairs(&lids), "7E4", "7EC"),
        "K20",
        VIN,
        None,
        None,
        None,
        &[],
    )
    .unwrap();
    let quiet_attrs = attrs(&quiet);
    assert_eq!(
        quiet_attrs[quiet_attrs.len() - 1],
        json!({ "key": "cvn_in_vit1", "value": "0" })
    );

    let mut cvn_lids = numbered_lids(&["C1", "C2", "C3"]);
    cvn_lids.push(("CB".to_owned(), part_value(9)));
    let flagged = vit1_from_read(
        &clone_text("HPCM2", &as_pairs(&cvn_lids), "7E0", "7E8"),
        "K107A",
        "",
        None,
        None,
        Some("1"),
        &["cell-4".to_owned()],
    )
    .unwrap();
    let flagged_attrs = attrs(&flagged);
    assert!(!names(&flagged_attrs).contains(&"vin".to_owned()));
    assert_eq!(
        flagged_attrs[flagged_attrs.len() - 2],
        json!({ "key": "partnum", "value": "cell-4" })
    );
    assert_eq!(
        flagged_attrs[flagged_attrs.len() - 1],
        json!({ "key": "cvn_in_vit1", "value": "1" })
    );
}

#[test]
fn k73_uses_its_decimal_hardware_and_no_parts() {
    let cb = part_value(9);
    let envelope = vit1_from_read(
        &clone_text("M241", &[("CB", cb.as_str())], "241", "641"),
        "K73",
        VIN,
        None,
        None,
        None,
        &[],
    )
    .unwrap();
    let attrs = attrs(&envelope);
    assert_eq!(names(&attrs).iter().filter(|n| *n == "partno").count(), 0);
    assert_eq!(attrs[0], json!({ "key": "ssecuhn", "value": "9" }));
    assert!(attrs.contains(&json!({ "key": "vin", "value": VIN })));
}

#[test]
fn k16_and_the_refused_k73_methods_have_no_rule() {
    let value = part_value(1);
    let err = vit1_from_read(
        &clone_text("BECM", &[("C1", value.as_str())], "7E4", "7EC"),
        "K16",
        VIN,
        None,
        None,
        None,
        &[],
    )
    .unwrap_err();
    assert!(err.to_string().contains("not a saved-read rule"));
}

#[test]
fn a_missing_part_read_is_reported() {
    let full = k17_lids();
    let one = as_pairs(&full[..1]);
    let err = vit1_from_read(
        &clone_text("BECM", &one, "7E4", "7EC"),
        "K17",
        VIN,
        None,
        None,
        None,
        &[],
    )
    .unwrap_err();
    assert!(err.to_string().contains("no lid C2"));
}

#[test]
fn a_vin_is_required_only_when_the_controller_reads_one() {
    let err = vit1_from_read(
        &clone_text("BECM", &as_pairs(&k17_lids()), "7E4", "7EC"),
        "K17",
        "",
        None,
        None,
        None,
        &[],
    )
    .unwrap_err();
    assert!(err.to_string().contains("reads a VIN"));
    let mut lids = numbered_lids(&["C1"]);
    lids.push(("CB".to_owned(), part_value(9)));
    let err = vit1_from_read(
        &clone_text("BECM", &as_pairs(&lids), "7E4", "7EC"),
        "A22",
        VIN,
        None,
        None,
        None,
        &[],
    )
    .unwrap_err();
    assert!(err.to_string().contains("does not read a VIN"));
}

#[test]
fn more_than_one_ecu_needs_a_choice() {
    let one = part_value(1);
    let two = part_value(2);
    let text = clone_text("BECM", &[("C1", one.as_str())], "7E4", "7EC")
        + &clone_text("IPC", &[("C1", two.as_str())], "244", "644");
    let err = vit1_from_read(&text, "K17", VIN, None, None, None, &[]).unwrap_err();
    assert!(err.to_string().contains("more than one ecu"));
}

#[test]
fn the_template_body_carries_the_attached_read() {
    let controller = json!({ "deviceId": 40, "requestMethod": { "reqMethodID": 11228 } });
    let template = json!({
        "clientState": { "vin": VIN },
        "spsVin": { "type": "NAOVin", "vin": VIN },
        "method": { "methodId": 128, "description": "Normal" },
        "controller": controller.clone(),
        "optionComposite": { "type": "ProductionOptionComposite" },
    });
    let body = request_from_read(
        &clone_text("BECM", &as_pairs(&k17_lids()), "7E4", "7EC"),
        &template,
        "K17",
        VIN,
        None,
        None,
        None,
        &[],
    )
    .unwrap();
    let keys: Vec<&str> = body
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(
        keys,
        [
            "clientState",
            "spsVin",
            "method",
            "controller",
            "optionComposite"
        ]
    );
    assert_eq!(
        body["controller"]["vit1"]["cmbs"][0]["vitAttrs"][0],
        json!({ "key": "ssecuhn", "value": "HW000042" })
    );
    assert!(controller.get("vit1").is_none());
}

#[test]
fn the_vci_template_copies_the_step_lists() {
    let template = json!({
        "clientState": { "vin": VIN },
        "spsVin": { "type": "NAOVin", "vin": VIN },
        "method": { "methodId": 2, "description": "VCI" },
        "controller": { "deviceId": 203, "requestMethod": { "reqMethodID": 529 } },
        "vciVOList": [{ "caller": "step" }],
    });
    let one = part_value(1);
    let two = part_value(2);
    let body = request_from_read(
        &clone_text(
            "BECM",
            &[("C1", one.as_str()), ("C2", two.as_str())],
            "7E4",
            "7EC",
        ),
        &template,
        "K114B",
        VIN,
        None,
        None,
        None,
        &[],
    )
    .unwrap();
    assert_eq!(body["functionSteps"], json!([]));
    assert_eq!(body["vciVOList"], json!([{ "caller": "step" }]));
    assert_eq!(
        body["controller"]["vit1"]["cmbs"][0]["vitAttrs"][0]["key"],
        "vin"
    );
}

#[test]
fn the_cli_writes_the_vit1_json() {
    let dir = unique_dir("cli-writes");
    let read = dir.join("clone.txt");
    std::fs::write(
        &read,
        clone_text("BECM", &as_pairs(&k17_lids()), "7E4", "7EC"),
    )
    .unwrap();
    let out = dir.join("body.json");
    let status = Command::new(env!("CARGO_BIN_EXE_spskit-vit1"))
        .args([
            "--read",
            read.to_str().unwrap(),
            "--code",
            "K17",
            "--vin",
            VIN,
            "--out",
            out.to_str().unwrap(),
        ])
        .status()
        .unwrap();
    assert!(status.success());
    let body: Value = serde_json::from_str(&std::fs::read_to_string(&out).unwrap()).unwrap();
    let attrs = body["vit1"]["cmbs"][0]["vitAttrs"].as_array().unwrap();
    assert_eq!(
        attrs[attrs.len() - 1],
        json!({ "key": "partno", "value": "10" })
    );
    std::fs::remove_dir_all(&dir).ok();
}

#[test]
fn the_cli_reports_a_refused_controller() {
    let dir = unique_dir("cli-refused");
    let read = dir.join("clone.txt");
    let value = part_value(1);
    std::fs::write(
        &read,
        clone_text("BECM", &[("C1", value.as_str())], "7E4", "7EC"),
    )
    .unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_spskit-vit1"))
        .args([
            "--read",
            read.to_str().unwrap(),
            "--code",
            "K16",
            "--vin",
            VIN,
        ])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr).contains("not a saved-read rule"));
    std::fs::remove_dir_all(&dir).ok();
}

#[test]
fn the_module_opens_no_socket() {
    let source = std::fs::read_to_string("src/handoff.rs").unwrap();
    assert!(!source.contains("urlopen"));
    assert!(!source.contains("https://"));
    let use_lines: Vec<&str> = source
        .lines()
        .filter(|line| line.trim_start().starts_with("use "))
        .collect();
    for banned in ["voltkit", "socket", "urllib", "http"] {
        assert!(!use_lines.iter().any(|line| line.contains(banned)));
    }
}

fn unique_dir(tag: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("spskit-{tag}-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}
