# spskit: plan

`spskit` is the GM SPS2 programming-request layer: the VIT1 `getProgrammingData` body and the GM J2534
wrapper connect string, as a library. Registered 2026-11-19, untiered and unsequenced. It sits beside the
`volt` research notes. The TDS and Techline Connect client (sign-in, licensed downloads, SPS Info, the
Techline Connect launch) was split out into `techlinekit`; `spskit` imports only
`techlinekit.spsinfo.check_vin` and `SpsInfoError` from it. The dongle is `vcxtoolkit`.

## 1. What this slice does

- `wrapper.parse_init()` classifies the GM wrapper connect string and does not load a library.
  `vit1.format0_decimal()`, `format1_text()`, and `format2_copy()` read a service `$1A` response.
  A dongle send belongs to `vcxtoolkit`.
- `vit1.programming_data_request()` builds `POST /sps/legacy/cloud/getProgrammingData` for K17
  (device 40, request method 11228), K33 (153, 11231), K20 (17, 11229), and K9 (64, 410). A saved
  module read is attached as the VIT1 control-module block: `vin` from DID `$90`, one decimal
  `partno` per part DID (4 bytes from byte 1). K33, K20, and K9 store `ssecuhn` from DID `$CC`
  with that same slice. K17's hardware length is 0, so its `ssecuhn` stays the string from the
  read. K9 adds part DIDs `$41` through `$4A`. K20 carries `cvn_in_vit1` as `1` or `0`. A `1`
  also carries `partnum` values, each a part string, a hyphen, and a decimal. The function returns
  the body. Gson writes `type`, not a Jackson `@type`, on the VIN and the option composite.
- The method-128 reads whose parts are a plain DID list and whose hardware is format 0, length 4,
  start 1 are paired. Method 1 posts that same body. Method 2 and method 256 use
  `vci_programming_data_request()`, which copies the caller's step lists and does not invent one.
  `after_selected_controller()` is the one-controller replacement: the response controller becomes
  the root and the previous `vit1` is not copied. `after_programming_data()` raises on a failed
  body, including `VIT_NO_VALID_CMB`, and on success keeps only the response controller.
  `sequences_after_programming_data()` is the list checked for `programmingData` before a security
  screen. A sequence with none raises `NO_CALIBRATIONS_SUPPORTED`. `normal_programming_data_loop()`
  then raises for programming-data id 10 and for an empty module list whose first block has a
  `partno`. It does not read `keycode`. `programming_method_screen()` is the switch under that loop.
  Methods 1, 2, 128, and 256 continue. File and reconfigure stop. `after_calibration_selection()`
  is the later switch: methods 1 and 128 open the summary when a module list and a displayable part
  list are both filled, and otherwise stop at instructions or name reprogramming without
  downloading. `calibration_selection_needed()` is true for `type` `VCI` when a part list is empty
  and `listOfModules` is not. `sequence_reprogramming()` names the next task, including a
  calibration download, and does not start it. `needs_vit1()` is the read gate: a device other than
  252 is read when `vit1` is missing or its header `vitAttrs` is empty. Blocks on `cmbs` do not
  count. `pre_communication_messages()` returns the root list that opens the pre-communication
  screen. An empty list does not. K73's format-2 hardware is not paired, and neither is K16's
  `P;C0,C1,C2` part text.
- `spskit-vit1` (`handoff.py`, console script) is the offline voltkit→spskit handoff, the one place
  `spskit` is run rather than imported. It reads one `ecu` block of a `voltkit profile --clone` file
  (`ecu`/`did`/`lid` text), takes a VIN and a controller code, and maps the captured `lid` reads onto
  `vit1.module_attributes()`, then prints the VIT1 control-module block from `vit1.build_vit1()`. With
  `--template` it attaches that read to a `getProgrammingData` body the catalog supplies, through
  `vit1.programming_data_request()` or `vci_programming_data_request()`. It does not import voltkit,
  open a socket, post to TDS, or program a vehicle. K16 and K73 request methods 520 and 566 have no
  saved-read rule, so the new public `vit1.read_shape()` refuses them; K73 method 601 stays the rule.
- `check_vin()` and `SpsInfoError` come from `techlinekit.spsinfo`; `spskit` does not keep its own copy.

## 2. What it does not do

- It is not the client. Sign-in, the password posts, the licensed-download list, the SPS Info catalog,
  and the Techline Connect launcher live in `techlinekit`. `spskit` has no `.env` and no network command;
  its only console script, `spskit-vit1`, is the offline capture-to-VIT1 transform above.
- It does not talk to a vehicle. The dongle, the serial frame, and a `PassThruSupport.04.04` registry
  record belong to `vcxtoolkit`. This package does not open a COM port or write that key. If a native
  client must look like `spsvcs`, the GM wrapper contract (`SOFTWARE\GM\J2534Wrapper` and its four
  exports) is the piece this package would own, and it is not built. The split is `docs/tool-boundary.md`.
  SAE J2534 is not in `primarysource`, so this package does not invent a pass-through.
- It does not implement security access or a calibration transfer. The programming-data body stays in
  the process. Sending it waits for a module read saved outside the repository. Service `$27` and a
  calibration download stay out of this package.

## 3. Using it

`spskit` is mostly imported, not run. `techlinekit` must be on the import path (it is a workspace sibling;
`pyproject.toml` puts it on `pythonpath`/`mypy_path`). Build a request with
`spskit.vit1.programming_data_request()` and classify a wrapper string with `spskit.wrapper.parse_init()`.
The one command is the offline handoff:

    spskit-vit1 --read <voltkit-clone.txt> --code K17 --vin <VIN>
    python -m spskit.handoff --read <voltkit-clone.txt> --code K17 --vin <VIN>
