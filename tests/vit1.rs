//! Port of `tests/test_vit1.py`: the programming-data request body and the screens after a response.

// These are faithful 1:1 ports of long Python test functions over fixed small fixtures: the row
// tables are deliberately explicit, the index casts are over known-small counts, and `&[x.clone()]`
// keeps each case readable. None of these pedantic lints flags a real problem in test code.
#![allow(
    clippy::too_many_lines,
    clippy::type_complexity,
    clippy::cast_possible_truncation,
    clippy::cloned_ref_to_slice_refs
)]

mod common;

use std::collections::BTreeMap;

use serde_json::{Value, json};
use spskit::Error;
use spskit::vit1::{
    Attr, Hardware, PROGRAMMING_DATA_PATH, SELECTED_CONTROLLER_PATH, VCI_PROGRAMMING_DATA_PATH,
    after_calibration_selection, after_programming_data, after_selected_controller, build_vit1,
    calibration_selection_needed, decimal_partno, format1_text, format2_copy, k17_attributes,
    module_attributes, needs_vit1, normal_programming_data_loop, pre_communication_messages,
    programming_data_request, programming_method_screen, sequence_reprogramming,
    sequences_after_programming_data, vci_programming_data_request,
};

use common::{
    CATALOG_PARTS, PART_DIDS, VIN, client, controller, controller_k17, dids_payloads, method128,
    no_catalog_parts, options, pairs, parts, payload, sps_vin,
};

fn body_for(controller: &Value, attributes: &[Attr]) -> Result<Value, Error> {
    programming_data_request(
        &client(),
        &sps_vin(),
        &method128(),
        controller,
        &options(),
        attributes,
    )
}

fn partnos(attrs: &[Value]) -> Vec<String> {
    attrs
        .iter()
        .filter(|a| a["key"] == "partno")
        .map(|a| a["value"].as_str().unwrap().to_owned())
        .collect()
}

fn range_strings(end: u32) -> Vec<String> {
    (1..=end).map(|i| i.to_string()).collect()
}

#[test]
fn a_saved_k17_read_is_the_vit1_block_on_the_request() {
    let attributes = k17_attributes(VIN, &parts(), "fixture-hw").unwrap();
    let fixture = controller_k17();
    let body = programming_data_request(
        &client(),
        &sps_vin(),
        &method128(),
        &fixture,
        &options(),
        &attributes,
    )
    .unwrap();
    assert_eq!(
        PROGRAMMING_DATA_PATH,
        "/sps/legacy/cloud/getProgrammingData"
    );
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
    assert!(!keys.contains(&"mcvm"));
    assert_eq!(body["method"], method128());
    assert_eq!(body["optionComposite"], options());
    let controller = &body["controller"];
    assert_eq!(controller["deviceId"], 40);
    assert_eq!(controller["requestMethod"]["reqMethodID"], 11228);
    assert!(fixture.get("vit1").is_none());
    let block = controller["vit1"]["cmbs"].as_array().unwrap();
    assert_eq!(block.len(), 1);
    let mut expected = vec![
        json!({ "key": "ssecuhn", "value": "fixture-hw" }),
        json!({ "key": "vin", "value": VIN }),
    ];
    for index in 1..=10 {
        expected.push(json!({ "key": "partno", "value": index.to_string() }));
    }
    assert_eq!(block[0]["vitAttrs"], Value::Array(expected));
    assert_eq!(controller["vit1"]["vitAttrs"], json!([]));
    assert_eq!(controller["vit1"]["freeOptions"], json!({ "vitAttrs": [] }));
    let encoded = serde_json::to_string(&body).unwrap();
    assert!(!encoded.contains("mcvm"));
    assert_eq!(body["spsVin"]["type"], "NAOVin");
    assert_eq!(body["optionComposite"]["type"], "ProductionOptionComposite");
    assert!(!encoded.contains("@type"));
    assert!(no_catalog_parts(&encoded));
    let source = std::fs::read_to_string("src/vit1.rs").unwrap();
    assert!(!source.contains("urlopen"));
    assert!(!source.contains("https://"));
    assert!(CATALOG_PARTS.iter().all(|part| !source.contains(part)));
}

#[test]
fn four_bytes_from_byte_1_are_a_decimal_partno() {
    assert_eq!(
        decimal_partno(&[0xff, 0x00, 0x00, 0x00, 0x2a]).unwrap(),
        "42"
    );
    let err = decimal_partno(&[0x00, 0x00, 0x00, 0x2a]).unwrap_err();
    assert!(err.to_string().contains("4 bytes from byte 1"));
}

#[test]
fn a_second_ssecuhn_starts_another_block() {
    let vit1 = build_vit1(&pairs(&[
        ("ssecuhn", "one"),
        ("partno", "1"),
        ("ssecuhn", "two"),
        ("partno", "2"),
    ]));
    assert_eq!(
        vit1["cmbs"],
        json!([
            { "vitAttrs": [{ "key": "ssecuhn", "value": "one" }, { "key": "partno", "value": "1" }] },
            { "vitAttrs": [{ "key": "ssecuhn", "value": "two" }, { "key": "partno", "value": "2" }] },
        ])
    );
}

#[test]
fn a_header_stays_off_the_block_and_an_option_becomes_a_free_pair() {
    let vit1 = build_vit1(&pairs(&[
        ("sps_id", "7"),
        ("option", "left;right"),
        ("ssecuhn", "hw"),
    ]));
    assert_eq!(vit1["vitAttrs"], json!([{ "key": "sps_id", "value": "7" }]));
    assert_eq!(
        vit1["freeOptions"],
        json!({ "vitAttrs": [{ "key": "left", "value": "right" }] })
    );
    assert_eq!(
        vit1["cmbs"],
        json!([{ "vitAttrs": [{ "key": "ssecuhn", "value": "hw" }] }])
    );
}

#[test]
fn a_request_without_the_k17_read_is_refused() {
    let err = body_for(&controller_k17(), &[]).unwrap_err();
    assert!(err.to_string().contains("one vin, ten part numbers"));
    let mut radio = controller_k17();
    radio["deviceId"] = json!(128);
    let err = body_for(
        &radio,
        &k17_attributes(VIN, &parts(), "fixture-hw").unwrap(),
    )
    .unwrap_err();
    assert!(err.to_string().contains("not a saved-read rule"));
}

#[test]
fn k33_k20_and_k9_reads_attach_as_vit1_blocks() {
    let k33_parts = parts();
    let k33 = body_for(
        &controller("K33", 153, 11231, &PART_DIDS.join(","), 0),
        &module_attributes(
            "K33",
            VIN,
            &k33_parts,
            Some(Hardware::Decimal(payload(42))),
            None,
            &[],
        )
        .unwrap(),
    )
    .unwrap();
    let k33_attrs = k33["controller"]["vit1"]["cmbs"][0]["vitAttrs"]
        .as_array()
        .unwrap();
    assert_eq!(k33["controller"]["deviceId"], 153);
    assert_eq!(k33["controller"]["requestMethod"]["reqMethodID"], 11231);
    assert_eq!(k33_attrs[0], json!({ "key": "ssecuhn", "value": "42" }));
    assert_eq!(partnos(k33_attrs), range_strings(10));
    assert!(
        !serde_json::to_string(k33_attrs)
            .unwrap()
            .contains("cvn_in_vit1")
    );

    let k9_dids = [
        "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "41", "42", "43", "44", "45",
        "46", "47", "48", "49", "4A",
    ];
    let k9_parts = dids_payloads(&k9_dids);
    let k9 = body_for(
        &controller("K9", 64, 410, &k9_dids.join(","), 0),
        &module_attributes(
            "K9",
            VIN,
            &k9_parts,
            Some(Hardware::Decimal(payload(7))),
            None,
            &[],
        )
        .unwrap(),
    )
    .unwrap();
    let k9_attrs = k9["controller"]["vit1"]["cmbs"][0]["vitAttrs"]
        .as_array()
        .unwrap();
    assert_eq!(k9["controller"]["requestMethod"]["reqMethodID"], 410);
    assert_eq!(partnos(k9_attrs), range_strings(20));

    let k20 = body_for(
        &controller("K20", 17, 11229, &PART_DIDS.join(","), 1),
        &module_attributes(
            "K20",
            VIN,
            &k33_parts,
            Some(Hardware::Decimal(payload(3))),
            Some("1"),
            &["cell-15".to_owned()],
        )
        .unwrap(),
    )
    .unwrap();
    let k20_attrs = k20["controller"]["vit1"]["cmbs"][0]["vitAttrs"]
        .as_array()
        .unwrap();
    assert_eq!(k20["controller"]["deviceId"], 17);
    assert_eq!(
        k20_attrs[k20_attrs.len() - 2],
        json!({ "key": "partnum", "value": "cell-15" })
    );
    assert_eq!(
        k20_attrs[k20_attrs.len() - 1],
        json!({ "key": "cvn_in_vit1", "value": "1" })
    );
    let encoded = serde_json::to_string(&k20).unwrap();
    assert!(no_catalog_parts(&encoded));
    assert!(!encoded.contains("0000A407"));

    let quiet = module_attributes(
        "K20",
        VIN,
        &k33_parts,
        Some(Hardware::Decimal(payload(3))),
        Some("0"),
        &[],
    )
    .unwrap();
    assert_eq!(
        quiet[quiet.len() - 1],
        ("cvn_in_vit1".to_owned(), "0".to_owned())
    );
    assert_eq!(quiet[0], ("ssecuhn".to_owned(), "3".to_owned()));
    let err = module_attributes(
        "K20",
        VIN,
        &k33_parts,
        Some(Hardware::Decimal(payload(3))),
        Some("fixture-cvn"),
        &[],
    )
    .unwrap_err();
    assert!(err.to_string().contains("1 or 0"));
    let err = module_attributes(
        "K33",
        VIN,
        &k33_parts,
        Some(Hardware::Decimal(payload(42))),
        Some("1"),
        &["cell-15".to_owned()],
    )
    .unwrap_err();
    assert!(err.to_string().contains("CVN stays off"));
}

#[test]
fn the_other_method_128_reads_attach() {
    let rows: Vec<(&str, i64, i64, Vec<&str>, Option<&str>, bool, &str)> = vec![
        ("A22", 102, 446, vec!["C1"], Some("CB"), false, ""),
        (
            "A11",
            128,
            432,
            vec!["C1", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "73"],
            Some("CB"),
            false,
            "",
        ),
        (
            "B218R",
            91,
            11243,
            PART_DIDS.to_vec(),
            Some("CB"),
            false,
            "",
        ),
        (
            "B218L",
            185,
            11239,
            PART_DIDS.to_vec(),
            Some("CB"),
            false,
            "",
        ),
        ("B233B", 210, 388, vec!["C1", "C2"], Some("CB"), false, ""),
        (
            "K43",
            49,
            417,
            vec!["C1", "C2", "C3"],
            Some("CB"),
            false,
            "",
        ),
        (
            "K84",
            175,
            427,
            vec!["C1", "C2", "C3"],
            Some("CB"),
            false,
            "",
        ),
        ("T3", 129, 434, vec!["C1", "CA"], Some("CB"), false, ""),
        ("K182", 187, 423, vec!["C1", "C2"], Some("CB"), false, ""),
        ("K109", 188, 428, vec!["C1", "C2"], Some("CB"), false, ""),
        ("K177", 43, 416, vec!["C1", "C2"], Some("CC"), false, ""),
        (
            "K107A",
            29,
            531,
            vec!["C1", "C2", "C3"],
            Some("CB"),
            true,
            "",
        ),
        (
            "K107B",
            30,
            532,
            vec!["C1", "C2", "C3"],
            Some("CC"),
            true,
            "",
        ),
        ("K118", 156, 530, vec!["C1", "C2"], None, false, ""),
        (
            "P16",
            96,
            11242,
            vec![
                "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "40", "42", "44", "67",
                "69", "71", "74", "76",
            ],
            Some("CB"),
            false,
            VIN,
        ),
        ("K73", 151, 601, vec![], Some("CB"), false, VIN),
    ];
    for (code, device, method, dids, hardware_did, cvn, vin) in rows {
        let module_parts = dids_payloads(&dids);
        let hardware = hardware_did.map(|_| Hardware::Decimal(payload(9)));
        let attributes = module_attributes(
            code,
            vin,
            &module_parts,
            hardware,
            if cvn { Some("0") } else { None },
            &[],
        )
        .unwrap();
        let body = body_for(
            &controller(code, device, method, &dids.join(","), i64::from(cvn)),
            &attributes,
        )
        .unwrap();
        let attrs = body["controller"]["vit1"]["cmbs"][0]["vitAttrs"]
            .as_array()
            .unwrap();
        let names: Vec<&str> = attrs.iter().map(|a| a["key"].as_str().unwrap()).collect();
        assert_eq!(body["controller"]["deviceId"], device);
        assert_eq!(body["controller"]["requestMethod"]["reqMethodID"], method);
        assert_eq!(names.iter().filter(|n| **n == "partno").count(), dids.len());
        assert_eq!(names.contains(&"ssecuhn"), hardware_did.is_some());
        assert_eq!(names.contains(&"vin"), !vin.is_empty());
        assert_eq!(names.contains(&"cvn_in_vit1"), cvn);
        assert!(no_catalog_parts(&serde_json::to_string(&body).unwrap()));
    }
    let flagged = module_attributes(
        "K107A",
        "",
        &dids_payloads(&["C1", "C2", "C3"]),
        Some(Hardware::Decimal(payload(9))),
        Some("1"),
        &["cell-4".to_owned()],
    )
    .unwrap();
    assert_eq!(
        flagged[flagged.len() - 1],
        ("cvn_in_vit1".to_owned(), "1".to_owned())
    );
    let err = module_attributes(
        "A22",
        VIN,
        &dids_payloads(&["C1"]),
        Some(Hardware::Decimal(payload(9))),
        None,
        &[],
    )
    .unwrap_err();
    assert!(err.to_string().contains("does not read a VIN"));
    let missing = controller("K73", 151, 520, "C7", 0);
    let err = body_for(&missing, &pairs(&[("ssecuhn", "1"), ("partno", "1")])).unwrap_err();
    assert!(err.to_string().contains("not a saved-read rule"));
}

#[test]
fn method_1_reads_use_the_same_programming_data_body() {
    let normal = json!({ "methodId": 1, "description": "Normal", "blockSameCal": false });
    let rows: Vec<(&str, i64, i64, Vec<&str>, Option<&str>, &str)> = vec![
        (
            "K124",
            108,
            396,
            vec![
                "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "60", "62", "64", "66",
                "68", "6A",
            ],
            Some("CB"),
            "",
        ),
        (
            "K74",
            143,
            579,
            vec!["C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "CA", "71"],
            Some("C1"),
            "",
        ),
        ("K114B", 203, 529, vec!["C1", "C2"], None, VIN),
        ("K36", 88, 421, vec!["C1", "C2", "C3"], Some("C1"), VIN),
    ];
    for (code, device, request_method, dids, hardware_did, vin) in rows {
        let module_parts = dids_payloads(&dids);
        let hardware = hardware_did.map(|hd| {
            Hardware::Decimal(module_parts.get(hd).cloned().unwrap_or_else(|| payload(9)))
        });
        let attributes = module_attributes(code, vin, &module_parts, hardware, None, &[]).unwrap();
        let body = programming_data_request(
            &client(),
            &sps_vin(),
            &normal,
            &controller(code, device, request_method, &dids.join(","), 0),
            &options(),
            &attributes,
        )
        .unwrap();
        assert_eq!(body["method"]["methodId"], 1);
        assert_eq!(body["controller"]["deviceId"], device);
        let attrs = body["controller"]["vit1"]["cmbs"][0]["vitAttrs"]
            .as_array()
            .unwrap();
        assert_eq!(
            attrs.iter().filter(|a| a["key"] == "partno").count(),
            dids.len()
        );
    }
    let vci = json!({ "methodId": 2, "description": "VCI", "blockSameCal": false });
    let mut k36_parts = BTreeMap::new();
    k36_parts.insert("C1".to_owned(), payload(1));
    k36_parts.insert("C2".to_owned(), payload(2));
    k36_parts.insert("C3".to_owned(), payload(3));
    let err = programming_data_request(
        &client(),
        &sps_vin(),
        &vci,
        &controller("K36", 88, 421, "C1,C2,C3", 0),
        &options(),
        &module_attributes(
            "K36",
            VIN,
            &k36_parts,
            Some(Hardware::Decimal(payload(1))),
            None,
            &[],
        )
        .unwrap(),
    )
    .unwrap_err();
    assert!(err.to_string().contains("method 1 or 128"));
    let err = module_attributes(
        "K36",
        VIN,
        &k36_parts,
        Some(Hardware::Decimal(payload(4))),
        None,
        &[],
    )
    .unwrap_err();
    assert!(err.to_string().contains("that part's read"));
    let err = module_attributes("K16", VIN, &BTreeMap::new(), None, None, &[]).unwrap_err();
    assert!(err.to_string().contains("not a saved-read rule"));
}

#[test]
fn one_selected_controller_replaces_the_root_and_drops_vit1() {
    let mut current = controller_k17();
    current["vit1"] = json!({
        "vitAttrs": [],
        "cmbs": [{ "vitAttrs": [{ "key": "ssecuhn", "value": "fixture-hw" }] }],
    });
    let replacement = json!({ "deviceId": 40, "requestMethod": { "reqMethodID": 11228 } });
    let chosen = after_selected_controller(&current, &[replacement.clone()], false).unwrap();
    assert_eq!(
        SELECTED_CONTROLLER_PATH,
        "/sps/legacy/cloud/getSelectedController"
    );
    assert_eq!(chosen, Some(replacement.clone()));
    assert!(chosen.unwrap().get("vit1").is_none());
    let other = json!({ "deviceId": 17 });
    assert_eq!(
        after_selected_controller(&current, &[replacement.clone(), other.clone()], true).unwrap(),
        None
    );
    let kept = after_selected_controller(&current, &[replacement, other], false)
        .unwrap()
        .unwrap();
    assert_eq!(
        kept["vit1"]["cmbs"][0]["vitAttrs"][0]["value"],
        "fixture-hw"
    );
    let err = after_selected_controller(&current, &[], false).unwrap_err();
    assert!(err.to_string().contains("no controller"));
}

#[test]
fn a_failed_programming_data_response_leaves_the_posted_root() {
    let mut posted = controller_k17();
    posted["vit1"] = json!({
        "vitAttrs": [],
        "cmbs": [{ "vitAttrs": [{ "key": "ssecuhn", "value": "fixture-hw" }] }],
    });
    let failed = json!({
        "success": false,
        "errorCode": "VIT_NO_VALID_CMB",
        "controller": { "deviceId": 1 },
    });
    let err = after_programming_data(&failed).unwrap_err();
    assert!(err.to_string().contains("VIT_NO_VALID_CMB"));
    assert_eq!(
        posted["vit1"]["cmbs"][0]["vitAttrs"][0]["value"],
        "fixture-hw"
    );
    let err = after_programming_data(&json!({ "success": false })).unwrap_err();
    assert!(err.to_string().contains("failed"));
    let returned = json!({ "deviceId": 40, "programmingData": { "id": 3 } });
    assert_eq!(
        after_programming_data(&json!({ "success": true, "controller": returned.clone() }))
            .unwrap(),
        returned
    );
    let err = after_programming_data(&json!({ "success": true })).unwrap_err();
    assert!(err.to_string().contains("no controller"));
}

#[test]
fn a_sequence_without_programming_data_stops_before_a_security_screen() {
    let data = json!({ "id": 3, "listOfModules": [] });
    let brake = json!({
        "deviceId": 40,
        "skipSameCalibration": false,
        "secCodeRequired": true,
        "programmingData": data.clone(),
    });
    let found = sequences_after_programming_data(&brake).unwrap();
    let device_ids: Vec<Value> = found.iter().map(|c| c["deviceId"].clone()).collect();
    assert_eq!(device_ids, vec![json!(40)]);
    assert_eq!(found[0]["programmingData"], data);
    let err = sequences_after_programming_data(&json!({ "deviceId": 40 })).unwrap_err();
    assert!(err.to_string().contains("NO_CALIBRATIONS_SUPPORTED"));
    assert_eq!(
        sequences_after_programming_data(&json!({ "deviceId": 40, "skipSameCalibration": true }))
            .unwrap(),
        Vec::<Value>::new()
    );
    assert_eq!(
        sequences_after_programming_data(&json!({
            "deviceId": 40,
            "mapOfControllers": { "child": { "deviceId": 17 } },
            "programmingData": null,
        }))
        .unwrap(),
        Vec::<Value>::new()
    );
    let child = json!({ "deviceId": 17, "programmingData": data.clone() });
    let container = sequences_after_programming_data(
        &json!({ "deviceId": 252, "mapOfControllers": { "K20": child } }),
    )
    .unwrap();
    let container_ids: Vec<Value> = container.iter().map(|c| c["deviceId"].clone()).collect();
    assert_eq!(container_ids, vec![json!(17)]);
    let err = sequences_after_programming_data(
        &json!({ "deviceId": 252, "mapOfControllers": { "K20": { "deviceId": 17 } } }),
    )
    .unwrap_err();
    assert!(err.to_string().contains("NO_CALIBRATIONS_SUPPORTED"));
}

#[test]
fn an_empty_module_list_with_a_partno_stops_before_a_security_screen() {
    let data = json!({ "id": 3, "listOfModules": [] });
    let block = json!({
        "vitAttrs": [{ "key": "partno", "value": "100" }, { "key": "keycode", "value": "unread" }],
    });
    let sequence = json!({
        "deviceId": 40,
        "programmingData": data.clone(),
        "vit1": { "vitAttrs": [], "cmbs": [block] },
    });
    let root = json!({ "deviceId": 40, "preProgrammingInstructions": [] });
    let err = normal_programming_data_loop(&[sequence.clone()], &root, None).unwrap_err();
    assert!(err.to_string().contains("No modules found"));
    let noted = json!({ "deviceId": 40, "preProgrammingInstructions": ["setup is required"] });
    normal_programming_data_loop(&[sequence.clone()], &noted, None).unwrap();
    normal_programming_data_loop(&[sequence], &root, Some(&noted)).unwrap();
    let vin_only = json!({
        "vitAttrs": [],
        "cmbs": [{ "vitAttrs": [{ "key": "vin", "value": "1" }] }],
    });
    normal_programming_data_loop(
        &[json!({ "deviceId": 40, "programmingData": data.clone(), "vit1": vin_only.clone() })],
        &root,
        None,
    )
    .unwrap();
    normal_programming_data_loop(
        &[json!({ "deviceId": 40, "programmingData": data.clone(), "vit1": { "vitAttrs": [], "cmbs": [null] } })],
        &root,
        None,
    )
    .unwrap();
    let err = normal_programming_data_loop(
        &[json!({ "deviceId": 40, "programmingData": data.clone() })],
        &noted,
        None,
    )
    .unwrap_err();
    assert!(err.to_string().contains("null vit1"));
    let type4 = json!({ "deviceId": 253, "programmingData": data.clone() });
    let err = normal_programming_data_loop(&[type4], &root, None).unwrap_err();
    assert!(err.to_string().contains("No modules found"));
    let unauthored = json!({
        "deviceId": 40,
        "programmingData": { "id": 10, "listOfModules": [{ "name": "blob" }] },
        "vit1": vin_only,
    });
    let err = normal_programming_data_loop(&[unauthored.clone()], &root, None).unwrap_err();
    assert!(err.to_string().contains("not authored"));
    normal_programming_data_loop(&[unauthored], &noted, None).unwrap();
    let mut held = json!({
        "deviceId": 40,
        "programmingData": data,
        "vit1": { "vitAttrs": [], "cmbs": [{ "vitAttrs": [{ "key": "partno", "value": "100" }, { "key": "keycode", "value": "unread" }] }] },
    });
    held["mcvmProgramming"] = json!({ "caller": "step" });
    normal_programming_data_loop(&[held], &root, None).unwrap();
}

#[test]
fn file_and_reconfigure_stop_and_the_vin_methods_continue() {
    for method_id in [1, 2, 16, 32, 64, 128, 256, 2048, 4096, 8192] {
        assert_eq!(programming_method_screen(method_id), None);
    }
    assert_eq!(programming_method_screen(4), Some("file.is.not.supported"));
    assert_eq!(
        programming_method_screen(512),
        Some("file.is.not.supported")
    );
    assert_eq!(
        programming_method_screen(8),
        Some("reconfiguration.is.not.supported.yet")
    );
    assert_eq!(
        programming_method_screen(1024),
        Some("reconfiguration.is.not.supported.yet")
    );
    assert_eq!(
        programming_method_screen(0),
        Some("no.valid.programming.method.found")
    );
}

#[test]
fn normal_methods_summarize_when_parts_are_displayable() {
    let modules = json!({
        "programmingData": { "listOfModules": [{ "id": "1" }] },
        "displayablePartsToInstall": ["shown"],
    });
    assert_eq!(
        after_calibration_selection(1, false, &[modules.clone()], None, None).unwrap(),
        "CALIBRATION_SUMMARY"
    );
    assert_eq!(
        after_calibration_selection(128, false, &[modules], None, None).unwrap(),
        "CALIBRATION_SUMMARY"
    );
    let empty =
        json!({ "programmingData": { "listOfModules": [] }, "displayablePartsToInstall": [] });
    assert_eq!(
        after_calibration_selection(128, false, &[empty.clone()], None, None).unwrap(),
        "handleSequenceReprogramming"
    );
    let noted = json!({ "preProgrammingInstructions": ["setup is required"] });
    assert_eq!(
        after_calibration_selection(1, false, &[empty.clone()], None, Some(&noted)).unwrap(),
        "PRE_PROGRAMMING_INSTRUCTIONS"
    );
    assert_eq!(
        after_calibration_selection(128, true, &[empty], None, None).unwrap(),
        "sps.exception.no-valid-cop"
    );
    assert_eq!(
        after_calibration_selection(2, false, &[], None, None).unwrap(),
        "CALIBRATION_SUMMARY"
    );
    assert_eq!(
        after_calibration_selection(16, false, &[], None, None).unwrap(),
        "LOAD_USB_DRIVES_TASK"
    );
    assert_eq!(
        after_calibration_selection(64, false, &[], None, None).unwrap(),
        "mcvm.is.not.supported"
    );
    assert_eq!(
        after_calibration_selection(4, false, &[], None, None).unwrap(),
        "file.is.not.supported"
    );
    assert_eq!(
        after_calibration_selection(512, false, &[], None, None).unwrap(),
        "file.bsc.is.not.supported"
    );
    assert_eq!(
        after_calibration_selection(8, false, &[], None, None).unwrap(),
        "reconfiguration.is.not.supported.yet"
    );
    assert_eq!(
        after_calibration_selection(1024, false, &[], None, None).unwrap(),
        "reconfiguration.bsc.is.not.supported.yet"
    );
    assert_eq!(
        after_calibration_selection(0, false, &[], None, None).unwrap(),
        "no.method.found"
    );
}

#[test]
fn vci_with_an_empty_part_list_needs_calibration_selection() {
    let ready = json!({
        "deviceId": 40,
        "programmingData": { "type": "VCI", "listOfModules": [{ "id": "1" }] },
        "partsToInstall": [],
        "displayablePartsToInstall": ["shown"],
    });
    assert!(calibration_selection_needed(&[ready.clone()], false).unwrap());
    let mut filled = ready.clone();
    filled["partsToInstall"] = json!(["installed"]);
    filled["displayablePartsToInstall"] = json!(["shown"]);
    assert!(!calibration_selection_needed(&[filled], false).unwrap());
    assert!(!calibration_selection_needed(&[ready.clone()], true).unwrap());
    assert!(!calibration_selection_needed(&[], false).unwrap());
    assert!(!calibration_selection_needed(&[json!({ "deviceId": 253 })], false).unwrap());
    let mut archive = ready;
    archive["programmingData"] = json!({ "type": "Archive", "listOfModules": [{ "id": "1" }] });
    let err = calibration_selection_needed(&[archive], false).unwrap_err();
    assert!(err.to_string().contains("not VCI"));
}

#[test]
fn reprogramming_names_the_task_and_does_not_download() {
    let root = json!({ "deviceId": 40 });
    let waiting = json!({
        "programmingDataUnits": [],
        "partsToInstall": ["caller-part"],
        "programmingData": { "listOfModules": [] },
    });
    assert_eq!(
        sequence_reprogramming(&[waiting.clone()], true, Some(&root)).unwrap(),
        "DOWNLOAD_PROG_FILES_TASK"
    );
    let mut skipped = waiting.clone();
    skipped["skipped"] = json!(true);
    assert_eq!(
        sequence_reprogramming(&[skipped], true, Some(&root)).unwrap(),
        "REPROGRAM_VEHICLE_TASK"
    );
    let pure = json!({ "mcvmProgramming": { "caller": "step" }, "programmingData": { "listOfModules": [] } });
    assert_eq!(
        sequence_reprogramming(&[pure], true, Some(&root)).unwrap(),
        "CHARACTERIZE_DATA_TASK"
    );
    assert_eq!(
        sequence_reprogramming(&[], true, Some(&root)).unwrap(),
        "WARRANTY_CLAIM_TASK"
    );
    assert_eq!(
        sequence_reprogramming(&[], false, None).unwrap(),
        "ToolLock.unlock"
    );
    let err = sequence_reprogramming(
        &[json!({ "partsToInstall": ["caller-part"] })],
        true,
        Some(&root),
    )
    .unwrap_err();
    assert!(err.to_string().contains("programmingDataUnits is null"));
}

#[test]
fn a_headerless_vit1_still_needs_the_read() {
    assert!(needs_vit1(&json!({ "deviceId": 40 })).unwrap());
    let blocks_only = json!({
        "deviceId": 40,
        "vit1": { "vitAttrs": [], "cmbs": [{ "vitAttrs": [{ "key": "partno", "value": "100" }] }] },
    });
    assert!(needs_vit1(&blocks_only).unwrap());
    let held = json!({
        "deviceId": 40,
        "vit1": { "vitAttrs": [{ "key": "vin", "value": "1" }], "cmbs": [] },
        "mapOfControllers": {},
    });
    assert!(!needs_vit1(&held).unwrap());
    let err = needs_vit1(
        &json!({ "deviceId": 40, "vit1": { "vitAttrs": [{ "key": "vin", "value": "1" }] } }),
    )
    .unwrap_err();
    assert!(err.to_string().contains("mapOfControllers is null"));
    let child = json!({ "deviceId": 17 });
    assert!(needs_vit1(&json!({ "deviceId": 252, "mapOfControllers": { "K20": child } })).unwrap());
    assert!(!needs_vit1(&json!({ "deviceId": 252, "mapOfControllers": {} })).unwrap());
}

#[test]
fn a_pre_communication_list_opens_that_screen() {
    assert_eq!(
        pre_communication_messages(&json!({ "deviceId": 40 })).unwrap(),
        None
    );
    assert_eq!(
        pre_communication_messages(&json!({ "deviceId": 40, "preCommunicationMessages": [] }))
            .unwrap(),
        None
    );
    let messages = pre_communication_messages(&json!({
        "deviceId": 203,
        "secCodeRequired": true,
        "preCommunicationMessages": ["close the hood"],
    }))
    .unwrap();
    assert_eq!(messages, Some(vec![json!("close the hood")]));
    let err = pre_communication_messages(&json!({ "preCommunicationMessages": "close the hood" }))
        .unwrap_err();
    assert!(err.to_string().contains("not a list"));
}

#[test]
fn method_2_is_the_vci_body_and_does_not_invent_steps() {
    let mut k114b_parts = BTreeMap::new();
    k114b_parts.insert("C1".to_owned(), payload(1));
    k114b_parts.insert("C2".to_owned(), payload(2));
    let attributes = module_attributes("K114B", VIN, &k114b_parts, None, None, &[]).unwrap();
    let steps = [json!({ "caller": "step" })];
    let body = vci_programming_data_request(
        &client(),
        &sps_vin(),
        &json!({ "methodId": 2, "description": "VCI", "blockSameCal": false }),
        &controller("K114B", 203, 529, "C1,C2", 0),
        &attributes,
        None,
        Some(&steps),
    )
    .unwrap();
    assert_eq!(
        VCI_PROGRAMMING_DATA_PATH,
        "/sps/legacy/cloud/getVciProgrammingData"
    );
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
            "functionSteps",
            "vciVOList"
        ]
    );
    assert_eq!(body["functionSteps"], json!([]));
    assert_eq!(body["vciVOList"], json!([{ "caller": "step" }]));
    assert_eq!(
        body["controller"]["vit1"]["cmbs"][0]["vitAttrs"][0]["key"],
        "vin"
    );
    assert!(!body.as_object().unwrap().contains_key("optionComposite"));
    assert!(!body.as_object().unwrap().contains_key("mcvm"));
    let err = vci_programming_data_request(
        &client(),
        &sps_vin(),
        &method128(),
        &controller("K114B", 203, 529, "C1,C2", 0),
        &attributes,
        None,
        None,
    )
    .unwrap_err();
    assert!(err.to_string().contains("method 2 or 256"));
}

#[test]
fn format1_is_two_characters_per_byte_and_format2_is_the_slice() {
    let response = [0x00, 0x00, 0x5A, 0x81, 0x2A, 0x00, 0x01];
    assert_eq!(format1_text(&response, 1, 1).unwrap(), "2:");
    assert_eq!(
        format2_copy(&response, 1, 3).unwrap(),
        vec![0x2A, 0x00, 0x01]
    );
}

#[test]
fn security_access_attributes_stay_off_the_request() {
    let mut attributes = k17_attributes(VIN, &parts(), "fixture-hw").unwrap();
    attributes.push(("seed".to_owned(), "aabb".to_owned()));
    let err = body_for(&controller_k17(), &attributes).unwrap_err();
    assert!(err.to_string().contains("security access"));
}
