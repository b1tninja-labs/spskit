# spskit

The GM SPS2 programming request, ported to Rust: the VIT1 `getProgrammingData` body and the GM J2534
wrapper connect string, built from a saved module read. This crate attaches a saved read as the VIT1
control-module block and returns the request body or the next screen. It opens no bus, posts nothing,
downloads no calibration, derives no security key, and speaks no SAE J2534 — the same scope boundary as
the Python package it replaces.

The decompiled `spsvcs` / `J2534Tool` paths the shapes follow are recorded in `docs/sources.md`. SAE
J2534 is not in `primarysource`; ISO 14229-1:2013 clause 15.4.4 names it as the link between the
application and the service-tool hardware and says the vehicle side uses manufacturer-proprietary
information, so this crate does not speak to a vehicle. The UDS/GMLAN service framing the format
decoders key on (the `$7F` negative-response marker, the `$1A` GMLAN ReadDataByIdentifier service id) is
read from the sibling `udskit` crate, so there is one Rust source of truth for it. The one rule the TDS
client `techlinekit` provides, VIN validation, is reproduced in `src/vin.rs` because there is no Rust
`techlinekit`.

Every `[ok]` row below names a Rust test that fails if the behaviour regresses.

## Programming data

A saved module read supplies the VIT1 control-module block from the fixture address lists: VIN `90` when
that request method reads a VIN, one decimal `partno` per plain part identifier, and `ssecuhn` from the
hardware identifier when the format is 0, the length is 4, and the start byte is 1. K17 keeps the
hardware string because its length is 0. K16 (`P;C0,C1,C2`, length 0) is refused. K73 request methods 520
and 566 (hardware `81`, format 2, length 3) stay unattached; method 601 remains the saved-read rule.

| Status | Obligation | Anchor | Test |
|---|---|---|---|
| [ok] | `vit1::programming_data_request` attaches a saved K17 module read as VIT1 control-module blocks on the controller | saved module read; the traced post with no vit1 is `VIT_NO_VALID_CMB` | `tests/vit1.rs` `a_saved_k17_read_is_the_vit1_block_on_the_request` |
| [ok] | `vit1::module_attributes` pairs a saved read for K33, K20, and K9, and `programming_data_request` attaches it | fixture request methods from the VIN catalog | `tests/vit1.rs` `k33_k20_and_k9_reads_attach_as_vit1_blocks` |
| [ok] | `vit1::format0_decimal` reads the GMLAN format-0 integer from a service `$1A` response, keying `$7F` off the udskit catalog | spsvcs FUN_10015d80; udskit `services::NEGATIVE_RESPONSE_SID` | `tests/wrapper.rs` `a_positive_gmlan_response_is_the_format0_decimal`, `a_negative_response_writes_no_number` |
| [ok] | `wrapper::parse_init` classifies the connect string and loads nothing | J2534Tool.init and CSpsVcsImpl::Init | `tests/wrapper.rs` `the_percent_form_names_the_version_and_the_tool`, `a_wrapper_form_without_a_name_is_refused` |
| [ok] | `vit1::module_attributes` pairs the other method-128 reads whose parts and hardware are format 0, length 4, start 1 | fixture-fresh.json supportedControllers | `tests/vit1.rs` `the_other_method_128_reads_attach` |
| [ok] | `vit1::programming_data_request` accepts method 1, the same body as method 128, for K124, K74, K114B, and K36 | GetProgrammingDataTask and ProgrammingMethod.isProgrammingByVCI | `tests/vit1.rs` `method_1_reads_use_the_same_programming_data_body` |
| [ok] | `vit1::vci_programming_data_request` builds the method 2 and 256 body and copies the caller's step lists | ProgrammingDataVCIRequest | `tests/vit1.rs` `method_2_is_the_vci_body_and_does_not_invent_steps` |
| [ok] | `vit1::after_selected_controller` replaces the root with one response controller and does not copy vit1 | SelectedControllerTask and handleAfterSelectedControllerResponse | `tests/vit1.rs` `one_selected_controller_replaces_the_root_and_drops_vit1` |
| [ok] | `vit1::after_programming_data` errors on a failed body and otherwise keeps only the response controller | GetProgrammingDataTask and validateAndReturnResponse | `tests/vit1.rs` `a_failed_programming_data_response_leaves_the_posted_root` |
| [ok] | `vit1::sequences_after_programming_data` lists the sequences checked for programmingData and errors when one has none | buildPSList and handleNextScreenAfterProgrammingDataRetrieval | `tests/vit1.rs` `a_sequence_without_programming_data_stops_before_a_security_screen` |
| [ok] | `vit1::normal_programming_data_loop` errors for unauthored id 10 and for an empty module list that still has a partno | handleNormalAfterProgrammingData | `tests/vit1.rs` `an_empty_module_list_with_a_partno_stops_before_a_security_screen` |
| [ok] | `vit1::programming_method_screen` continues the ten programming methods and refuses file and reconfigure | ProgrammingMethodId and handleNormalAfterProgrammingData | `tests/vit1.rs` `file_and_reconfigure_stop_and_the_vin_methods_continue` |
| [ok] | `vit1::after_calibration_selection` chooses the summary, the instruction screen, or names reprogramming without downloading | handleNextScreenAfterCalibrationSelection | `tests/vit1.rs` `normal_methods_summarize_when_parts_are_displayable` |
| [ok] | `vit1::calibration_selection_needed` is true for VCI data when a part list is empty and modules are not | calSelectionNeeded | `tests/vit1.rs` `vci_with_an_empty_part_list_needs_calibration_selection` |
| [ok] | `vit1::sequence_reprogramming` names the next task and does not download or reprogram | handleSequenceReprogramming | `tests/vit1.rs` `reprogramming_names_the_task_and_does_not_download` |
| [ok] | `vit1::needs_vit1` reads a device other than 252 when the header vitAttrs is empty, and blocks on cmbs do not count | needsVIT1 and VIT.isEmpty | `tests/vit1.rs` `a_headerless_vit1_still_needs_the_read` |
| [ok] | `vit1::pre_communication_messages` returns the root list that opens the pre-communication screen | preCommunicationInstructionsNeeded | `tests/vit1.rs` `a_pre_communication_list_opens_that_screen` |
| [ok] | `vit1::format1_text` and `vit1::format2_copy` read the other two GMLAN formats | spsvcs FUN_10015d80 | `tests/vit1.rs` `format1_is_two_characters_per_byte_and_format2_is_the_slice` |
| [ok] | `vit1::build_vit1` keeps headers off the block, splits an option into a free pair, and opens a new block on a repeated block-start name | VIT1BuilderImpl | `tests/vit1.rs` `a_second_ssecuhn_starts_another_block`, `a_header_stays_off_the_block_and_an_option_becomes_a_free_pair` |
| [ok] | `vit1::decimal_partno` prints four bytes from byte 1 of a part DID in base 10 | GMLAN format 0, start 1, length 4 | `tests/vit1.rs` `four_bytes_from_byte_1_are_a_decimal_partno` |
| [ok] | `vin::check_vin` accepts a 17-character VIN and refuses I, O and Q, standing in for techlinekit | techlinekit.spsinfo.check_vin | `src/vin.rs` `a_17_character_vin_without_ioq_is_returned`, `a_short_or_illegal_vin_is_refused` |
| [ok] | `vit1::module_attributes` refuses K16 | fixture `partAddresses` `P;C0,C1,C2`, length 0 | `tests/vit1.rs` `method_1_reads_use_the_same_programming_data_body` |
| [ok] | `vit1::programming_data_request` refuses K73 request method 520 | fixture hardware `81`, format 2, length 3; method 601 stays the saved-read rule | `tests/vit1.rs` `the_other_method_128_reads_attach` |
| [ok] | security access and other `$27` attributes stay off the request | owner decision | `tests/vit1.rs` `security_access_attributes_stay_off_the_request` |

## The clone-read handoff and CLI

`spskit-vit1` turns a captured `voltkit profile --clone` file into a VIT1 request offline. It supersedes
the Python handoff on PR #4, which this port replaces. The deliberate gaps carry over: `read_shape`
refuses K16 and K73 request methods 520 and 566; K73 builds via method 601.

| Status | Obligation | Anchor | Test |
|---|---|---|---|
| [ok] | `vit1::read_shape` / `read_codes` expose a saved-read rule's shape and refuse the codes with no rule (K16, K73 520/566) | the `ReadRule` table | `tests/handoff.rs` `k16_and_the_refused_k73_methods_have_no_rule` |
| [ok] | `handoff::parse_clone_profile` groups `did`/`lid` lines under their `ecu` block and skips comments and the `s3` line | voltkit `src/capture.rs::clone_profile` | `tests/handoff.rs` `parse_groups_lids_under_their_ecu_and_ignores_comments_and_notes` |
| [ok] | `handoff::vit1_from_read` maps a captured read onto its rule and returns the VIT1 block with its attributes | voltkit clone format + the saved-read rules | `tests/handoff.rs` `a_captured_k17_read_becomes_the_vit1_block`, `a_decimal_hardware_read_is_the_format0_slice` |
| [ok] | `handoff::request_from_read` attaches the read to a catalog template and prints the whole request body | getProgrammingData / getVciProgrammingData bodies | `tests/handoff.rs` `the_template_body_carries_the_attached_read`, `the_vci_template_copies_the_step_lists` |
| [ok] | the `spskit-vit1` binary reads a clone file and writes the VIT1 JSON offline, and reports a refused controller | the handoff CLI interface vcxtoolkit `collect` references | `tests/handoff.rs` `the_cli_writes_the_vit1_json`, `the_cli_reports_a_refused_controller` |

## The GM J2534 proxy binding

Techline Connect does not load a vendor J2534 DLL directly. `com.gm.sps.tool.jni.J2534DeviceImpl`
reads `HKLM\SOFTWARE\Wow6432Node\GM\J2534Proxy` value `FunctionLibrary` and JNA-loads that GM proxy
DLL as `J2534Wrapper_proxy`, whose `PassThruOpen` is a non-standard six-argument form gated by an
allow list and a deny list (RE'd from `sps-nativelibs.jar`; see `docs/sources.md`). `proxy` holds
that binding contract as safe logic — the device gate, the auto-accept open/close bookkeeping, the
version report, the registry registration tuple, and the GM-exact programming constants — without
exporting a C ABI, loading a DLL, or writing the registry. Building the native `cdylib` and the
message path is `vcxtoolkit`'s, per `docs/tool-boundary.md`; this crate forbids `unsafe`.

| Status | Obligation | Anchor | Test |
|---|---|---|---|
| [ok] | `proxy::parse_filter_list` parses the `name:vendor:api:flag` allow/deny grammar and refuses a bad entry or flag | `J2534Wrapper` `ALLOW_LIST`; sae-j2534-api-contract.md §8 | `src/proxy.rs` `a_malformed_entry_or_flag_is_refused`, `the_default_allow_list_parses_to_four_entries_ending_in_the_catch_all` |
| [ok] | `proxy::ProxyState::accepts` gates a device through the default lists' `*:*:*:0` catch-all and a deny entry blocks it | `J2534DeviceImpl.openJ2534Device` allow/deny lists | `tests/proxy.rs` `the_default_allow_list_catch_all_selects_any_vcx`, `a_deny_entry_rejects_an_otherwise_allowed_device` |
| [ok] | `proxy::ProxyState::open` is the six-arg GM `PassThruOpen` auto-accepting without a picker: `OPEN_OK` + recorded id, and `close` threads it | sae-j2534-api-contract.md §8 (6-arg PassThruOpen, 0/9999) | `tests/proxy.rs` `open_auto_accepts_without_a_picker_and_threads_the_device_id_through_close` |
| [ok] | `proxy::ProxyState::read_version` reports API `04.04` only for an open device and refuses an oversize 256-byte buffer string | `J2534Wrapper.PassThruReadVersion` (256-byte buffers) | `tests/proxy.rs` `read_version_reports_04_04_only_once_a_device_is_open`, `a_version_string_longer_than_the_buffer_is_refused` |
| [ok] | `proxy::registration` builds the `HKLM\SOFTWARE\Wow6432Node\GM\J2534Proxy` `FunctionLibrary` tuple and refuses an empty path | `J2534DeviceImpl.loadLibrary` registry read | `tests/proxy.rs` `registration_points_the_proxy_key_at_the_dll` |
| [ok] | `proxy::gmlan` records the GM-exact programming constants (HS-GMLAN 500000, SW-CAN 33333/83333) and the ISO15765 timeout→STMIN=1ms adaptation | `tisvcsv4.dll`; sae-j2534-api-contract.md §9 | `tests/proxy.rs` `the_gm_programming_channel_values_match_the_re_d_constants` |

## Not this slice

| Status | Obligation | Anchor | Test |
|---|---|---|---|
| [no] | sign-in, licensed downloads, SPS Info, and the Techline Connect launcher live in `techlinekit`, not here; this crate reproduces only VIN validation | project split | none: `docs/tool-boundary.md` |
| [no] | do not program a controller, calculate a seed or key, or speak SAE J2534; the dongle and PassThruSupport.04.04 belong to vcxtoolkit | ISO 14229-1:2013 clause 15.4.4 | none: `docs/tool-boundary.md` |
| [no] | the native proxy `cdylib` (the `extern "C"` exports, writing the registry, loading and delegating the message path to the VCX pass-through) is `vcxtoolkit`'s; this crate forbids `unsafe` and only holds the contract | unsafe FFI boundary; sae-j2534-api-contract.md §8 Division Suggestion | none: `docs/tool-boundary.md` |
| [no] | security access and transfer of a calibration stay out of this crate | owner decision | none: same boundary as the volt research notes |
