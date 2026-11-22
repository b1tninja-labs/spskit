# spskit

Build the GM SPS2 **programming request** in Rust: the VIT1 `getProgrammingData` body and the GM J2534
wrapper connect string. This crate is a library, not a client — it does not sign in, download, open a
port, or talk to a vehicle. It is a behaviour-for-behaviour port of the Python package it replaces.

```rust
use spskit::vit1::programming_data_request;
use spskit::wrapper::parse_init;
```

`vit1::programming_data_request` builds the `POST /sps/legacy/cloud/getProgrammingData` body for the
method-1 and method-128 reads on a VIN from a saved module read: the VIT1 control-module block, with
`vin` from DID `$90`, one decimal `partno` per part DID, and `ssecuhn` from the hardware identifier.
`vit1::format0_decimal`, `format1_text`, and `format2_copy` read a service `$1A` response.
`wrapper::parse_init` classifies the GM J2534 wrapper connect string (`SOFTWARE\GM\J2534Wrapper` and its
four exports) and loads nothing. The screen functions (`after_selected_controller`,
`after_programming_data`, `sequences_after_programming_data`, `programming_method_screen`,
`after_calibration_selection`, `sequence_reprogramming`, `needs_vit1`, `pre_communication_messages`)
return the body or the next screen. They do not post, and they do not download a calibration.

## The `spskit-vit1` CLI

An offline transform: a captured `voltkit profile --clone` file and a VIN in, a request body out.

```text
spskit-vit1 --read <clone.txt> --code <K17> --vin <VIN> \
  [--ecu NAME] [--ssecuhn S] [--cvn 0|1] [--partnum P ...] [--template body.json] [--out FILE]
```

Default output is a self-describing JSON envelope (controller code, device, request method, ecu, VIN,
the attribute pairs, and the `vit1` document). With `--template` (a `getProgrammingData` body the catalog
supplies) it attaches the read and prints the full request body. It imports nothing from voltkit, opens no
socket, posts nothing, and reads no dongle.

## What this crate links and what lives elsewhere

- **[udskit](../udskit)** — the shared UDS (ISO 14229-1) / GMLAN model. `spskit` reads its service catalog
  for the `$7F` negative-response marker and the `$1A` GMLAN ReadDataByIdentifier service id its format
  decoders key on, so there is one Rust source of truth for the service framing. Path dependency on the
  sibling repo; no bus, no key material, no write service crosses this boundary.
- **techlinekit** — the ACDelco TDS and Techline Connect client (sign-in, licensed downloads, SPS Info,
  the Techline Connect launcher). It is a separate Python repository. The one rule `spskit` needs from it,
  VIN validation, is reproduced in `src/vin.rs` because there is no Rust `techlinekit`.
- **vcxtoolkit** — the dongle: the serial frame, the licence, `PassThruSupport.04.04`. The split is
  `docs/tool-boundary.md`.

This crate does not program a vehicle. Service `$27`, a calibration transfer, and SAE J2534 pass-through
stay out of it. Edition 2024, MSRV 1.85, `unsafe` forbidden. Apache-2.0.
