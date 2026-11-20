# SPS2 tool and calibration download

`SPS2.msi` 26.10.27 (`sps2.jar`, 67,250,464 bytes) is the service-programming application inside Techline
Connect. After a vehicle is selected, the landing page asks for a diagnostic tool and a programming
process (`select.diagnostic.tool`, `please.select.process.tool`). This note names those choices and the
request that fetches a calibration file. It does not describe a write to a controller.

## Diagnostic tool

`com.gm.sps.model.client.ToolType` has four values:

| Enum | Shown as |
| --- | --- |
| `PT_J2534` | J2534 Pass Through (`j2534.pass.through`) |
| `PT_LEGACY` | legacy pass-through; the field-action copy calls this Legacy Programming |
| `T2_REMOTE` | remote |
| `TEST_DRIVER` | the test tool (`testing.tool`) |

The same list is repeated on `com.gm.cca.shared.data.sps.ToolType`. The English bundle also has
`using.mdi.2` ("Using MDI 2") and `change.mdi.warning`, which says the selected vehicle needs an MDI-2
or an equivalent communication tool. `config.not.needed` says a non-J2534 tool skips configuration.
`auto.detect.tool` and `manually.select.tool` are the two ways the page fills that list.

This build does not contain the string `VHCI`. The vehicle-communication choice it does contain is
`VCI`.

## Programming process

`com.gm.sps.model.vehcontroller.references.ProgrammingMethod` names these types, and the English
bundle gives the first two a label:

| Type | Label |
| --- | --- |
| `VCI` | Programming by VCI (`sps.programming-type.vci`, `vci.selection`) |
| `USB_COPY_BY_VCI` | USB Copy by VCI |
| `VCI_BSC` | |
| `USB_COPY_BY_VCI_BSC` | |
| `USB_COPY` | |
| `USB_COPY_BSC` | |

The VIN catalog stores the same split. For `1G1RD6S58HU102764` the method ids are Normal (`1`),
VCI (`2`), and the block-same-cal forms of those two (`128`, `256`). USB Copy is in this build and
is not one of those rows. The request, the cache, and the USB-copy package are in
[calibration-downloads.md](calibration-downloads.md).

`standard.user.input` is the label "Standard User Input". It sits with `invalid.user.input` and is the
form prompt, not a second programming interface. `com.gm.sps.model.client.ProgrammingMode` is a
different list again: information, reprogram, replace and reprogram, IVCS tool test, module update
check, OnStar, infotainment, and no selection.

## Calibration files

The catalog rows name the parts. The bytes come from the programming-data response, then from the
server URI on that response or from `POST /getCalibrationFile`. SPS3 downloads each part, including
the operating-system part, as its own file. The cache, the USB-copy package, the method ids, and
that per-part GET are in [calibration-downloads.md](calibration-downloads.md). `SPS Info`
(`/cvn/partnumber/{part}`) returns a CVN for a part number. It does not return the file.
