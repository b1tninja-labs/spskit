# spskit: plan

`spskit` is the GM SPS2 programming-request layer, a **Rust crate**: the VIT1 `getProgrammingData` body
and the GM J2534 wrapper connect string, as a library plus the offline `spskit-vit1` CLI. Registered
2026-11-19, ported Python → Rust 2026-11-21, untiered and unsequenced. It sits beside the `volt` research
notes and the sibling Rust crates (`udskit`, `isotpkit`, `vcxtoolkit`). The TDS and Techline Connect
client (sign-in, licensed downloads, SPS Info, the Techline Connect launch) is `techlinekit`; the one rule
`spskit` needs from it, VIN validation, is reproduced in `src/vin.rs`. The dongle is `vcxtoolkit`.

## 1. What this slice does

- `wrapper::parse_init` classifies the GM wrapper connect string and loads nothing. `vit1::format0_decimal`,
  `format1_text`, and `format2_copy` read a service `$1A` response, keying the `$7F` negative-response
  marker and the `$1A` service id off the sibling `udskit` catalog. A dongle send belongs to `vcxtoolkit`.
- `vit1::programming_data_request` builds `POST /sps/legacy/cloud/getProgrammingData` for K17 (device 40,
  request method 11228), K33 (153, 11231), K20 (17, 11229), and K9 (64, 410). A saved module read is
  attached as the VIT1 control-module block: `vin` from DID `$90`, one decimal `partno` per part DID
  (4 bytes from byte 1). K33, K20, and K9 store `ssecuhn` from DID `$CC` with that same slice. K17's
  hardware length is 0, so its `ssecuhn` stays the string from the read. K9 adds part DIDs `$41` through
  `$4A`. K20 carries `cvn_in_vit1` as `1` or `0`; a `1` also carries `partnum` values, each a part string,
  a hyphen, and a decimal. serde writes `type`, not a Jackson `@type`, on the VIN and the option composite.
- The method-128 reads whose parts are a plain DID list and whose hardware is format 0, length 4, start 1
  are paired. Method 1 posts that same body. Method 2 and method 256 use `vci_programming_data_request`,
  which copies the caller's step lists and does not invent one. `after_selected_controller` is the
  one-controller replacement. `after_programming_data` errors on a failed body, including
  `VIT_NO_VALID_CMB`. `sequences_after_programming_data` is the list checked for `programmingData`; a
  sequence with none errors `NO_CALIBRATIONS_SUPPORTED`. `normal_programming_data_loop` then errors for
  programming-data id 10 and for an empty module list whose first block has a `partno`, and does not read
  `keycode`. `programming_method_screen` is the switch under that loop. `after_calibration_selection` is
  the later switch, and names reprogramming without downloading. `calibration_selection_needed` is true for
  `type` `VCI` when a part list is empty and `listOfModules` is not. `sequence_reprogramming` names the
  next task and does not start it. `needs_vit1` is the read gate. `pre_communication_messages` returns the
  root list that opens the pre-communication screen. K73's format-2 hardware is not paired, and neither is
  K16's `P;C0,C1,C2` part text.
- `vin::check_vin` validates a VIN (17 characters, no I/O/Q), standing in for `techlinekit.spsinfo.check_vin`.
- `spskit-vit1` (`src/main.rs`, `handoff` module) turns a captured `voltkit profile --clone` file plus a
  VIN and a controller code into the VIT1 request body. It is an offline transform; it imports nothing from
  voltkit, opens no socket, and posts nothing. It supersedes the Python handoff on PR #4.

## 2. What it does not do

- It is not the client. Sign-in, the password posts, the licensed-download list, the SPS Info catalog, and
  the Techline Connect launcher live in `techlinekit`. `spskit` has no client CLI and no `.env` (the one
  binary, `spskit-vit1`, is an offline request transform with no secrets).
- It does not talk to a vehicle. The dongle, the serial frame, and a `PassThruSupport.04.04` registry
  record belong to `vcxtoolkit`. This crate opens no COM port and writes no key. If a native client must
  look like `spsvcs`, the GM wrapper contract (`SOFTWARE\GM\J2534Wrapper` and its four exports) is the piece
  this crate would own, and it is not built. The split is `docs/tool-boundary.md`. SAE J2534 is not in
  `primarysource`, so this crate does not invent a pass-through.
- It does not implement security access or a calibration transfer. The programming-data body stays in the
  process. Service `$27` and a calibration download stay out of this crate.

## 3. Using it

`spskit` is a library crate plus the `spskit-vit1` binary. `udskit` must be beside this checkout (the path
dependency `../udskit`). Build a request with `spskit::vit1::programming_data_request`, classify a wrapper
string with `spskit::wrapper::parse_init`, or run `spskit-vit1 --read <clone.txt> --code <CODE> --vin <VIN>`
for the offline clone-read handoff.
