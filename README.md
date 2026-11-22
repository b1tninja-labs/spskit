# spskit

Build the GM SPS2 **programming request**: the VIT1 `getProgrammingData` body and the GM J2534 wrapper
connect string. This package is a library, not a client — it does not sign in, download, or talk to a
vehicle.

```python
from spskit.vit1 import programming_data_request
from spskit.wrapper import parse_init
```

`vit1.programming_data_request()` builds the `POST /sps/legacy/cloud/getProgrammingData` body for the
method-128 reads on a VIN from a saved module read: the VIT1 control-module block, with `vin` from DID
`$90`, one decimal `partno` per part DID, and `ssecuhn` from the hardware identifier. `vit1.format0_decimal()`,
`format1_text()`, and `format2_copy()` read a service `$1A` response. `wrapper.parse_init()` classifies the GM
J2534 wrapper connect string (`SOFTWARE\GM\J2534Wrapper` and its four exports) and does not load a library.
The screen functions (`after_selected_controller()`, `after_programming_data()`,
`sequences_after_programming_data()`, `programming_method_screen()`, `after_calibration_selection()`,
`sequence_reprogramming()`, `needs_vit1()`, `pre_communication_messages()`) return the body or the next
screen. They do not post, and they do not download a calibration.

## Where the rest lives

- **[techlinekit](../techlinekit)** — the ACDelco TDS and Techline Connect client: sign-in, licensed
  downloads, SPS Info, and the Techline Connect launcher. `spskit` imports just
  `techlinekit.spsinfo.check_vin` and `SpsInfoError` from it. techlinekit is a workspace sibling on the
  import path (see `pyproject.toml` `pythonpath` / `mypy_path`), not yet a published dependency.
- **vcxtoolkit** — the dongle: the serial frame, the licence, `PassThruSupport.04.04`. The split is
  `docs/tool-boundary.md`.

This package does not program a vehicle. Service `$27`, a calibration transfer, and SAE J2534 pass-through
stay out of it. Standard library only. Apache-2.0.
