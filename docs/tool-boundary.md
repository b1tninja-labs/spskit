# Who talks to the tool

`spskit` and `vcxtoolkit` (`D:\code\vcxtoolkit`) split the native stack. This package does not open the dongle. The same split is in that crate's `docs/tool-boundary.md`.

## This package

`spskit` builds the SPS request. A saved module read becomes the VIT1 block on `getProgrammingData`. It does not open a COM port, load `VCX.dll`, or write `HKLM\SOFTWARE\PassThruSupport.04.04`.

`wrapper.parse_init()` classifies the connect string. An empty string asks for the default device. `%04.04%J2534,<tool name>` is the wrapper form. `AUTO` and `COM<port>,<baud>` are the two forms native Init special-cases. Any other text is a connection name Techline already selected. The key is `SOFTWARE\GM\J2534Wrapper`, value `FunctionLibrary`, and the four names are `GetDefaultDeviceInfo`, `ClearDefaultDeviceInfo`, `GetConnectedDeviceInfo`, and `GetDeviceStatus`. The function does not load a library. `j2534bridge.dll` was not found on this machine. `spsvcs.dll` exports those four names as its own API and also resolves them on the missing wrapper.

`vit1.format0_decimal()` reads a service `$1A` response. Byte 2 must not be `0x7F`. Start byte 1 and length 4 are response bytes 4 through 7. This package does not build the request a dongle would send.

`proxy` holds the GM J2534 proxy binding contract Techline Connect loads: `J2534DeviceImpl.loadLibrary()` reads `HKLM\SOFTWARE\Wow6432Node\GM\J2534Proxy` value `FunctionLibrary` and JNA-loads it as `J2534Wrapper_proxy`, whose `PassThruOpen` is a six-argument form gated by an allow and a deny list. The module decides — the allow/deny gate, the auto-accept open/close, the `04.04` version report, the registry *tuple*, the GM-exact programming constants — the way `wrapper` classifies the connect string. It does not export a C ABI, load a DLL, open the dongle, write the registry, or speak the `PassThruConnect`/`ReadMsgs`/`WriteMsgs`/`Ioctl`/`StartMsgFilter` message path. A `cdylib` cannot live here: this crate forbids `unsafe`, and FFI over the raw `char*`/`unsigned long*` buffers needs it.

## vcxtoolkit

`vcxtoolkit` owns the dongle: the serial frame, `GetInfo`, the license, and the firmware catalog. A later vehicle read is that crate's `docs/reads.md`, the `VCX_PRO_*` commands, not the fifteen `PassThru*` exports. If real Techline Connect must see a device, that crate is the one that would write `PassThruSupport.04.04` with `FunctionLibrary` pointing at a pass-through DLL. The existing installer already does that. This package does not.

`VCX_SetEventCallback` is a device-SDK export. It stays on that side. `nativeInstallCallback` is an SPS progress hook after a tool is already selected, and it is not how a device registers.

The native GM J2534 proxy `cdylib` is vcxtoolkit's too. It exports the `extern "C"` `PassThruOpen`/`PassThruClose`/`PassThruReadVersion` (the GM six-arg forms) plus the 04.04 message path, writes `HKLM\SOFTWARE\Wow6432Node\GM\J2534Proxy` `FunctionLibrary` at install, and delegates `PassThruConnect`/`ReadMsgs`/`WriteMsgs`/`Ioctl`/`StartMsgFilter` to its own 04.04 pass-through. It depends on `spskit::proxy` for the gate, the open/close/version decisions, the registry tuple, and the GM constants — the contract, decided in safe Rust, with the unsafe FFI and the bus kept on this side. The RE that pins the ABI is `sae-j2534-api-contract.md` §8–§9.
