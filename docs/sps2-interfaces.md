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

The VIN catalog stores the same split. For `1G1RD6S58HU102764` each function has a method described
`Normal` and a method described `VCI`. `sps.programming-type.normal` is the label `Normal`. The class
distinguishes them with `isProgrammingByVCI` and `isProgrammingByUSB`. `CalDownloadService` then has
`handleDownloadForNormal`, `handleDownloadForUsb` and `handleDownloadForEthernet`.

`standard.user.input` is the label "Standard User Input". It sits with `invalid.user.input` and is the
form prompt, not a second programming interface. `com.gm.sps.model.client.ProgrammingMode` is a
different list again: information, reprogram, replace and reprogram, IVCS tool test, module update
check, OnStar, infotainment, and no selection.

## Calibration files

The catalog rows name the parts. The bytes come later, from SPS2, and land in
`C:\ProgramData\GM\TDM\SPS Cache` (`tdm.calibration.files.path`). `CalDownloadService.downloadCalFileFromDB`
posts `getCalibrationFile` through `RestTemplate` and reads an `InputStreamResponse`. The request type
is `DownloadCalibrationFileRequest` (a download id, the client state, and the part). The server list
on that call is `DownloadServer`, with subtypes `CALDownloadServer` and `DLSDownloadServer`; the
programming-data response supplies those servers, so the file is not a row on the public CDN used for
`TUM2` and `SPS2.msi`.

`SPS Info` (`/cvn/partnumber/{part}`) returns a CVN for a part number. It does not return the file.
