# spskit: plan

An open-source replacement for the Java Techline Connect / SPS2 client, which is built for a bundled
Java 11 and does not run well on current Java. Registered 2026-11-19, untiered and unsequenced.
It sits beside `obd-bridge` and the `volt` research notes. It is a downloader for modules the person's
own ACDelco TDS subscription is licensed for.

## 1. What this slice does

- Reads ACDelco / GM TDS settings from `.env`. `.env.example` ships with empty secrets. `.env` is gitignored.
- Lists the versions of one resource the permissions call returns, and does not keep the account id.
- Asks the gateway for a download grant and writes the file under `SPS_DOWNLOAD_DIR`, which must be an absolute path.
- `spskit downloads` lists every licensed file version the gateway returns: the Techline Connect
  installer, TUM, runnable decimal resources, prelaunch resources, and the update-manager search.
  `spskit downloads --get` writes each version under `SPS_DOWNLOAD_DIR/cache/{id}/{version}/` and
  leaves a file that is already there. `--refresh` fetches it again.
- `spskit sps --vin` reads the SPS Info catalog for that one VIN and writes it to `SPS_DOWNLOAD_DIR/spsinfo.sqlite`.
  Running it again replaces that VIN. The file holds module names and part numbers.
- `vit1.programming_data_request()` builds `POST /sps/legacy/cloud/getProgrammingData` for K17
  (device 40, request method 11228), K33 (153, 11231), K20 (17, 11229), and K9 (64, 410). A saved
  module read is attached as the VIT1 control-module block: `vin` from DID `$90`, one decimal
  `partno` per part DID (4 bytes from byte 1). K33, K20, and K9 store `ssecuhn` from DID `$CC`
  with that same slice. K17's hardware length is 0, so its `ssecuhn` stays the string from the
  read. K9 adds part DIDs `$41` through `$4A`. K20 carries `cvn_in_vit1` as `1` or `0`. A `1`
  also carries `partnum` values, each a part string, a hyphen, and a decimal. The function returns
  the body. Gson writes `type`, not a Jackson `@type`, on the VIN and the option composite.
- `wrapper.parse_init()` classifies the GM wrapper connect string and does not load a library.
  `vit1.format0_decimal()`, `format1_text()`, and `format2_copy()` read a service `$1A` response.
  A dongle send belongs to `vcxtoolkit`. The method-128 reads whose parts are a plain DID list
  and whose hardware is format 0, length 4, start 1 are paired. Method 1 posts that same
  body. Method 2 and method 256 use `vci_programming_data_request()`, which copies the
  caller's step lists and does not invent one. `after_selected_controller()` is the
  one-controller replacement: the response controller becomes the root and the previous
  `vit1` is not copied. `after_programming_data()` raises on a failed body, including
  `VIT_NO_VALID_CMB`, and on success keeps only the response controller.
  `sequences_after_programming_data()` is the list checked for `programmingData` before
  a security screen. A sequence with none raises `NO_CALIBRATIONS_SUPPORTED`.
  `normal_programming_data_loop()` then raises for programming-data id 10 and for an empty
  module list whose first block has a `partno`. It does not read `keycode`.
  `programming_method_screen()` is the switch under that loop. Methods 1, 2, 128, and 256
  continue. File and reconfigure stop. `after_calibration_selection()` is the later
  switch: methods 1 and 128 open the summary when a module list and a displayable part
  list are both filled, and otherwise stop at instructions or name reprogramming
  without downloading. `calibration_selection_needed()` is true for `type` `VCI` when a
  part list is empty and `listOfModules` is not. `sequence_reprogramming()` names the
  next task, including a calibration download, and does not start it.
  `needs_vit1()` is the read gate: a device other than 252 is read when `vit1` is
  missing or its header `vitAttrs` is empty. Blocks on `cmbs` do not count.
  `pre_communication_messages()` returns the root list that opens the
  pre-communication screen. An empty list does not. K73's format-2
  hardware is not paired,
  and neither is K16's `P;C0,C1,C2` part text.
- `spskit login` posts the password and asks the host to email a code. It writes the challenge to the
  session file and does not write the code. `spskit code` reads that challenge, waits for the code, and
  writes the access token from the redirect. A dropped connection retries, and `spskit code` can be
  repeated without another email.
- `spskit session` prompts for an access token the person already holds and writes it to
  `SPS_DOWNLOAD_DIR/session.json`, or to `TDS_TOKEN_FILE` when that absolute path is set. Later commands
  load it when `TDS_ACCESS_TOKEN` is empty.
- A gateway 401 is reported as a refused gateway session. The command does not invent a code to send.
  Gateway ACL calls send the `SPS-INFO_ACCESS_TOKEN` cookie from the SPOREF handoff as `Authorization`.
  They do not send the EEID access token.

## 2. What it does not do

- The sign-in password is posted as `passwd`. A separate captured reset, not used by `spskit login`,
  sends `newPassword`. Neither value is sent to the token endpoint.
- It does not talk to a vehicle. The dongle, the serial frame, and a `PassThruSupport.04.04` registry
  record belong to `vcxtoolkit`. This package does not open a COM port or write that key. If a native
  client must look like `spsvcs`, the GM wrapper contract (`SOFTWARE\GM\J2534Wrapper` and its four
  exports) is the piece this package would own, and it is not built. `j2534bridge.dll` is not assigned
  to either package. The split is `docs/tool-boundary.md`. SAE J2534 is not in `primarysource`, so this
  package does not invent a pass-through.
- It does not implement security access or a calibration transfer. `spskit sps --vin` does not download a calibration file.
- The K17 programming-data body stays in the process. Sending it waits for a module read saved
  outside the repository. Service `$27` and a calibration download stay out of this package.

## 3. Commands

From this directory:

    copy .env.example .env
    python -m spskit modules --id 25
    python -m spskit download --id 25
    python -m spskit downloads
    python -m spskit downloads --get
    python -m spskit sps --vin <VIN>
    python -m spskit login
    python -m spskit code
    python -m spskit session
    python -m spskit verify < challenge.json
    python -m spskit token --redirect "https://www.acdelcotds.com/#code=..."

`verify` reads the challenge the sign-in host returned and prompts for the code. Fill in `.env` on this machine.
Do not commit it.
