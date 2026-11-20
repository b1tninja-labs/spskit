# Who talks to the tool

`spskit` and `vcxtoolkit` (`D:\code\vcxtoolkit`) split the native stack. This package does not open the dongle. The same split is in that crate's `docs/tool-boundary.md`.

## This package

`spskit` builds the SPS request. A saved module read becomes the VIT1 block on `getProgrammingData`. It does not open a COM port, load `VCX.dll`, or write `HKLM\SOFTWARE\PassThruSupport.04.04`.

If a native client must look like `spsvcs`, this package is the one that would speak the GM wrapper. That is the init string `%04.04%J2534,<tool name>` when no connection name is already set, the key `HKLM\SOFTWARE\GM\J2534Wrapper`, and the four exports `GetDefaultDeviceInfo`, `ClearDefaultDeviceInfo`, `GetConnectedDeviceInfo`, and `GetDeviceStatus`. That wrapper is not implemented here. `j2534bridge.dll`, which would turn those exports into `PassThruOpen`, is not in this tree and is not assigned to either package.

## vcxtoolkit

`vcxtoolkit` owns the dongle: the serial frame, `GetInfo`, the license, and the firmware catalog. A later vehicle read is that crate's `docs/reads.md`, the `VCX_PRO_*` commands, not the fifteen `PassThru*` exports. If real Techline Connect must see a device, that crate is the one that would write `PassThruSupport.04.04` with `FunctionLibrary` pointing at a pass-through DLL. The existing installer already does that. This package does not.

`VCX_SetEventCallback` is a device-SDK export. It stays on that side. `nativeInstallCallback` is an SPS progress hook after a tool is already selected, and it is not how a device registers.
