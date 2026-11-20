# TLC Suite 2

`TLCSuite.exe` 26.8.31 is a WiX Burn bundle. The bundle id is
`{63b81cbe-3d84-44e2-aea3-54237e6dabc6}`, the display name is `TLC Suite 2`, and the publisher
is General Motors. The copy saved from the edge is
`SPS_DOWNLOAD_DIR/cache/25/26.8.31.0/TLCSuite.exe` (256,026,736 bytes).

The bundle chain is three MSI packages and nothing else:

| Package | Product code | Version | Display name | Files |
| --- | --- | --- | --- | --- |
| `tumLauncher.msi` | `{1EAA363F-CDEB-43A2-81FA-76DB9AB2AEC5}` | 26.4.23.0 | TUM Launchers | `TLCLauncher.exe`, `TLCLauncherAdmin.exe` |
| `tumJava.msi` | `{68750DD4-112A-4ACE-8DFD-6C214A230FA6}` | 1.0.0 | TUM Bundled Java | the JRE the launcher starts |
| `tumApp.msi` | `{6C1BA74B-B828-4A4F-AFB8-9F35500DC98E}` | 26.8.28.0 | Techline Update Manager | `Tum.exe` |

Those two launcher executables and `Tum.exe` are the same Launch4j stubs already described in
[tlc-binaries.md](tlc-binaries.md). The suite does not contain GDS2, MDI, Service Programming, or
the other catalog entries. Those are separate CDN objects. A full `spskit downloads --get` on
2026-11-19 saved the suite and received a cached NetStorage redirect for every other licensed file.

The Burn manifest and the three payloads were taken from the cabinets embedded in the executable
and left under `local/tlc/suite/`, which is gitignored with the rest of `local/`.
