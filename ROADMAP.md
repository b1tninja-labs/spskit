# Obligations and their evidence

Every obligation `spskit` has taken on, with an honest status against the code.

**The honesty rule:** a row reads `[ok]` only when the test named in its Evidence cell exists and would fail if the
behaviour regressed. `tests/test_roadmap_rows.py` resolves every `[ok]` row's test and every callable the matrix
names.

Legend: `[ok]` implemented and pinned by a named test — `[part]` partial, what is missing stated — `[ ]` not built —
`[no]` deliberate non-goal, with the reason.

`spskit` is the SPS2 programming request: the VIT1 `getProgrammingData` body and the GM J2534 wrapper connect
string. The TDS and Techline Connect client — sign-in, licensed downloads, SPS Info, the Techline Connect launch —
is `techlinekit`, and `spskit` imports the one piece it needs from it (`techlinekit.spsinfo.check_vin`,
`SpsInfoError`). The dongle is `vcxtoolkit`. The sources for the VIT1 and wrapper shapes are the decompiled
`spsvcs`/`J2534Tool` paths recorded in `docs/sources.md`. SAE J2534 is not in `primarysource`. ISO 14229-1:2013
clause 15.4.4 names it as the link between the application and the service-tool hardware and says the vehicle side
uses manufacturer-proprietary information, so this package does not speak to a vehicle.

## 1. Matrix

### Programming data

The body of `POST /sps/legacy/cloud/getProgrammingData`, and the screens that follow a response.
A saved module read supplies the VIT1 control-module block from the fixture address lists: VIN
`90` when that request method reads a VIN, one decimal `partno` per plain part identifier, and
`ssecuhn` from the hardware identifier when the format is 0, the length is 4, and the start byte
is 1. K17 keeps the hardware string because its length is 0. These functions return that body or
the next screen. They do not post, and they do not download a calibration. Hardware selection
stays undecided because `VCI.isValid` is not decompiled. K16 (`P;C0,C1,C2`, length 0) is refused.
K73 request methods 520 and 566 (hardware `81`, format 2, length 3) stay unattached; method 601
remains the saved-read rule. A live post waits until a real read is on disk. Request-method seed
flags stay unread.

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.vit1.request` | `vit1.programming_data_request()` attaches a saved K17 module read as VIT1 control-module blocks on the controller | saved module read; the traced post with no vit1 is `VIT_NO_VALID_CMB` | `[ok]` | `tests/test_vit1.py::test_a_saved_k17_read_is_the_vit1_block_on_the_request` |
| `sk.vit1.siblings` | `vit1.module_attributes()` pairs a saved read for K33, K20, and K9, and `vit1.programming_data_request()` attaches it | fixture request methods from the VIN catalog | `[ok]` | `tests/test_vit1.py::test_k33_k20_and_k9_reads_attach_as_vit1_blocks` |
| `sk.vit1.format0` | `vit1.format0_decimal()` reads the GMLAN format-0 integer from a service $1A response | spsvcs FUN_10015d80 | `[ok]` | `tests/test_wrapper.py::test_a_positive_gmlan_response_is_the_format0_decimal` |
| `sk.wrapper.init` | `wrapper.parse_init()` classifies the connect string and does not load a library | J2534Tool.init and CSpsVcsImpl::Init | `[ok]` | `tests/test_wrapper.py::test_the_percent_form_names_the_version_and_the_tool` |
| `sk.vit1.rest` | `vit1.module_attributes()` pairs the other method-128 reads whose parts and hardware are format 0, length 4, start 1 | fixture-fresh.json supportedControllers | `[ok]` | `tests/test_vit1.py::test_the_other_method_128_reads_attach` |
| `sk.vit1.normal` | `vit1.programming_data_request()` accepts method 1, the same body as method 128, for K124, K74, K114B, and K36 | GetProgrammingDataTask and ProgrammingMethod.isProgrammingByVCI | `[ok]` | `tests/test_vit1.py::test_method_1_reads_use_the_same_programming_data_body` |
| `sk.vit1.vci` | `vit1.vci_programming_data_request()` builds the method 2 and 256 body and copies the caller's step lists | ProgrammingDataVCIRequest | `[ok]` | `tests/test_vit1.py::test_method_2_is_the_vci_body_and_does_not_invent_steps` |
| `sk.vit1.selected` | `vit1.after_selected_controller()` replaces the root with one response controller and does not copy vit1 | SelectedControllerTask and handleAfterSelectedControllerResponse | `[ok]` | `tests/test_vit1.py::test_one_selected_controller_replaces_the_root_and_drops_vit1` |
| `sk.vit1.progdata` | `vit1.after_programming_data()` raises on a failed body and otherwise keeps only the response controller | GetProgrammingDataTask and validateAndReturnResponse | `[ok]` | `tests/test_vit1.py::test_a_failed_programming_data_response_leaves_the_posted_root` |
| `sk.vit1.sequences` | `vit1.sequences_after_programming_data()` lists the sequences checked for programmingData and raises when one has none | buildPSList and handleNextScreenAfterProgrammingDataRetrieval | `[ok]` | `tests/test_vit1.py::test_a_sequence_without_programming_data_stops_before_a_security_screen` |
| `sk.vit1.modules` | `vit1.normal_programming_data_loop()` raises for unauthored id 10 and for an empty module list that still has a partno | handleNormalAfterProgrammingData | `[ok]` | `tests/test_vit1.py::test_an_empty_module_list_with_a_partno_stops_before_a_security_screen` |
| `sk.vit1.method` | `vit1.programming_method_screen()` continues the ten programming methods and refuses file and reconfigure | ProgrammingMethodId and handleNormalAfterProgrammingData | `[ok]` | `tests/test_vit1.py::test_file_and_reconfigure_stop_and_the_vin_methods_continue` |
| `sk.vit1.summary` | `vit1.after_calibration_selection()` chooses the summary, the instruction screen, or names reprogramming without downloading | handleNextScreenAfterCalibrationSelection | `[ok]` | `tests/test_vit1.py::test_normal_methods_summarize_when_parts_are_displayable` |
| `sk.vit1.calselect` | `vit1.calibration_selection_needed()` is true for VCI data when a part list is empty and modules are not | calSelectionNeeded | `[ok]` | `tests/test_vit1.py::test_vci_with_an_empty_part_list_needs_calibration_selection` |
| `sk.vit1.reprogram` | `vit1.sequence_reprogramming()` names the next task and does not download or reprogram | handleSequenceReprogramming | `[ok]` | `tests/test_vit1.py::test_reprogramming_names_the_task_and_does_not_download` |
| `sk.vit1.needs` | `vit1.needs_vit1()` reads a device other than 252 when the header vitAttrs is empty, and blocks on cmbs do not count | needsVIT1 and VIT.isEmpty | `[ok]` | `tests/test_vit1.py::test_a_headerless_vit1_still_needs_the_read` |
| `sk.vit1.precom` | `vit1.pre_communication_messages()` returns the root list that opens the pre-communication screen | preCommunicationInstructionsNeeded | `[ok]` | `tests/test_vit1.py::test_a_pre_communication_list_opens_that_screen` |
| `sk.vit1.format12` | `vit1.format1_text()` and `vit1.format2_copy()` read the other two GMLAN formats | spsvcs FUN_10015d80 | `[ok]` | `tests/test_vit1.py::test_format1_is_two_characters_per_byte_and_format2_is_the_slice` |
| `sk.vit1.k16` | `vit1.module_attributes()` refuses K16 | fixture `partAddresses` `P;C0,C1,C2`, length 0 | `[ok]` | `tests/test_vit1.py::test_method_1_reads_use_the_same_programming_data_body` |
| `sk.vit1.k73` | `vit1.programming_data_request()` refuses K73 request method 520 | fixture hardware `81`, format 2, length 3; method 601 stays the saved-read rule | `[ok]` | `tests/test_vit1.py::test_the_other_method_128_reads_attach` |

### Not this slice

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.no.client` | sign-in, licensed downloads, SPS Info, and the Techline Connect launcher live in `techlinekit`, not here. `spskit` imports `techlinekit.spsinfo.check_vin` and `SpsInfoError` and nothing else | project split | `[no]` | `docs/tool-boundary.md` |
| `sk.no.vehicle` | do not program a controller, calculate a seed or key, or speak SAE J2534 until that document is imported into primarysource. The dongle and PassThruSupport.04.04 belong to vcxtoolkit | ISO 14229-1:2013 clause 15.4.4 | `[no]` | `docs/tool-boundary.md` |
| `sk.no.security-access` | security access and transfer of a calibration stay out of this package | owner decision | `[no]` | same boundary as the volt research notes |
