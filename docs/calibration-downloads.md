# Calibration downloads

SPS2 does not take a calibration from the CDN that serves `TUM2` and `SPS2.msi`, and SPS Info does
not return the file. The VIN catalog names the parts. A later programming-data response names the
blob, the download id, and the server list. The bytes are fetched from that list, or from
`POST /getCalibrationFile` when the list is empty.

This is the request the client makes. It is not a write to a controller. The call has not been sent
for `1G1RD6S58HU102764`, so those files are not in the cache.

## What this VIN can ask for

`ProgrammingMethodId` is the method the catalog stores. The `_BSC` ids are the same process with
`block_same_cal` set. For this VIN the catalog has only these four:

| Id | Name | Rows | `block_same_cal` | Label |
| --- | --- | --- | --- | --- |
| 1 | `NORMAL` | 4 | 0 | Normal |
| 2 | `VCI` | 4 | 0 | Programming by VCI |
| 128 | `NORMAL_BSC` | 23 | 1 | Normal |
| 256 | `VCI_BSC` | 23 | 1 | Programming by VCI |

The parts already stored for the selected sequence are `23394159` (operating system), `23394161` and
`84131365` (electronic brake, slot 2), then `23394158`, `23394157`, `23394136`, `23394154`, and
`23394155`.

USB copy is attached to a function by the server. It is not a mode the client turns on for the
whole vehicle, and it is not tied to the word "radio". The ids the client knows, with the English
labels, are:

| Id | Name | Label |
| --- | --- | --- |
| 4 | `FILE` | |
| 8 | `RECONFIGURE` | Reconfigure |
| 16 | `USB_COPY` | USB Copy |
| 32 | `USB_COPY_BY_VCI` | USB Copy by VCI |
| 64 | `MCVM` | MCVM operation selection |
| 512 | `FILE_BSC` | |
| 1024 | `RECONFIGURE_BSC` | |
| 2048 | `USB_COPY_BSC` | |
| 4096 | `USB_COPY_BY_VCI_BSC` | |
| 8192 | `MCVM_BSC` | |

`VciType` is a separate flag on a GSPAS step: `LOCAL`, `ARCHIVE`, `OVERRIDE`, or `NORMAL`. It is not
another download URL.

## Which request returns the file list

The programming-data call is chosen from the method, and each one goes through `RestTemplate` as a
path on the SPS2 service base. The cloud properties file `prodPcf/environment.properties` sets that
base to `https://tlc-dmz-gateway.ext.gm.com/sps/legacy/cloud`. The same path on the gateway root
is not the service. The body is `clientState`, `spsVin`, `method`, `controller`, and
`optionComposite`. A null `mcvm` is omitted. The option composite is the object paired with the method in the fixture's
controller tree. For this VIN the brake module (`K17`, function Programming, method id 128) carries
an empty `ProductionOptionComposite`. A POST with the SPS Info bearer reached that service and
returned no file list before the session expired. No part file was written.

| Method | Service | Path |
| --- | --- | --- |
| Normal | `ProgrammingDataService` | `/getProgrammingData` |
| VCI | `ProgrammingDataVciService` | `/getVciProgrammingData` |
| GSPAS | `ProgrammingDataGspasService` | `/getProgrammingDataGspas` |

The request carries the client state, the VIN, the programming method, and the sequence. The
response is a list of `ProgrammingDataUnit`. Each unit has a blob name, a blob size, a download id,
and a list of `DownloadServer`. A server is a `CALDownloadServer` (a URI, plus secured and Akamai
flags) or a `DLSDownloadServer` (a URI, an Akamai flag, and a description).

`vit1.programming_data_request()` builds that body for K17, K33, K20, and K9. A saved module read
supplies the VIT1 control-module block on `controller`: `vin` from DID `$90` and one decimal
`partno` per part DID. K33, K20, and K9 store `ssecuhn` from DID `$CC` as that same 4-byte
decimal. K17's hardware length is 0, so its `ssecuhn` stays the string from the read. K9's part
list continues through `$4A`. K20 carries `cvn_in_vit1` as `1` or `0`, and a `1` also carries
`partnum`. The
programming-data writer is Gson, so the VIN and the option composite use `type`. The traced post
of K17 with no `vit1` is `D:\data\spskit\re\programming-data-k17.json`, `errorCode`
`VIT_NO_VALID_CMB`. The function returns the body. A live post waits until a real read is on disk.

The same builder also pairs the other method-128 reads on this VIN whose part list is plain
DIDs and whose hardware, when read, is format 0, length 4, start 1. VIN and hardware are
omitted when that request method does not read them. K73's WiFi row (request method 601)
has a VIN and DID `$CB` and no parts. K73 request methods 520 and 566 stay off: their
hardware format is 2. `format2_copy()` returns those bytes and does not turn them into
`ssecuhn`.

Method 1 (`NORMAL`) reaches the same `GetProgrammingDataTask` as method 128. The body is the
same request. Method 2 (`VCI`) does not: `isProgrammingByVCI` sends that sequence to
`/getVciProgrammingData`. K124, K74, K114B, and K36 are method 1. Their part lists are plain
DIDs at format 0, length 4, start 1, so the builder pairs them. K36's hardware DID is `$C1`,
the same read as its first part. K16 stays off: `partAddresses` is `P;C0,C1,C2` and the part
length is 0. That string is handed to the native reader as `pszPartAddresses`. The
DLL has no stored copy of the text, so the prefix is not split here.

`vit1.vci_programming_data_request()` is the other body, for method 2 and method 256.
The field name is `vciVOList`. A null step list becomes `[]`, which is what the
constructor stores. The documents in those lists are the caller's. A null `mcvm` is
omitted. The function does not post.

`SelectedControllerTask` posts that same programming-data body to `/getSelectedController`.
`after_selected_controller()` is the non-GSPAS result. One controller becomes the next
root and does not keep the read that was on the previous root. Several controllers and a
populated option composite stop on the options screen.

`GetProgrammingDataTask` sets the root only after `validateAndReturnResponse` returns.
`after_programming_data()` raises when `success` is not true, so `VIT_NO_VALID_CMB` leaves
the posted controller in place. A success returns the response `controller` and does not
merge the previous root into it.

## Where the bytes go

`CalDownloadService.downloadFiles` sums the blob sizes, then branches on the event rather than on
the method id:

```mermaid
flowchart TD
  units["ProgrammingDataUnit list"] --> usb{"A USB drive is selected?"}
  usb -->|yes| usbGet["Fetch each unit, then unpack onto that drive"]
  usb -->|no| eth{"Ethernet or delta?"}
  eth -->|yes| ethGet["Fetch into the cache, under the archive step folder"]
  eth -->|no| normal["Fetch into the cache under the blob name"]
  units --> servers{"Server list empty?"}
  servers -->|yes| db["POST /getCalibrationFile"]
  servers -->|no| http["GET server URI joined with the download id"]
```

The cache directory is the preference `tdm.calibration.files.path`, and the default is
`C:\ProgramData\GM\TDM\SPS Cache`. The file name is the blob name. A later download of the same blob
name deletes the existing file and writes the new one. That is not the CDN layout, which keeps each
version in `cache/{id}/{version}/`. Two calibration versions stay side by side only when their blob
names differ.

When the server list is empty, `getUnit` posts `DownloadCalibrationFileRequest`: the service id from
the VIN, the archive flag, the blob name as the part number, and the download id. The path is
`/getCalibrationFile`. The body that comes back is an `InputStreamResponse`.

When the list is not empty, `FileDataProvider.getCalData` sends `GET` to the server URI joined with
the download id. The header is `Authorization: bearer` plus the Techline access token. An Akamai
server also gets the Akamai cookie. A 200 response is written to `{cache}/{blobName}`.
`getGspasCalData` is the same fetch for a GSPAS unit. The client retries a status other than 200.

## Reprogram

Reprogram is a programming mode (`programming.mode.reprogram`). SPS2 26.10.27 does not give that
mode its own path. `DOWNLOAD_PROG_FILES_TASK` fetches every unit the programming-data response
named, through the GET and the `/getCalibrationFile` POST above. `REPROGRAM_VEHICLE_TASK` then
reads those blobs (`getCalibrationFiles`, `getProgrammingDataUnits`).

That is the older client. The vehicle software file is a separate object in SPS3 26.10.27
(`SPS3.jar`), the vehicle-wide programming client from the same cache generation. SPS2's
`currentSoftware` and `selectedSoftware` are summary fields on `SPSModule`. They are not the
download. The word firmware in the SPS2 jar is the J2534 tool's own version (`J2534Version`). A
type-4 event is `POST /getType4App`, and it is not this download.

## Vehicle software parts

Vehicle Wide Programming is a button on the SPS2 controller-selection screen. Pressing it writes a
vehicle file and then starts `SPS3.exe`. The file is

`%USERPROFILE%\sps\vwp\{vin}\{eventId}\input\vehicleSupportedEcus.json`

SPS2 and SPS3 both root that tree at `user.home\sps`. The JSON is an `Sps3Vehicle`: the event (VIN,
event id, type `SPS3_EVENT`, the programming mode, locale, country, dealer code), the selected
tool's VCI connection name, the job card, the model year, `rpoContent` from the GSPAS VIN, the
client version, an empty field-action number, the VESCOM flag, and one ECU per supported controller
(`id`, `code`, `name`, `baseVehicleId`). SPS3 reads that file back as its vehicle. The functional-step
call refuses a vehicle with no `rpoContent`.

From there SPS3 does three HTTP calls, then the file GET. Each POST sends `Authorization: bearer`
with the SPS3 session token. `{base.url}` is the Techline session base, the same kind of value SPS2
reads from `ClientApplicationContext.getServerUrl()`. It is not compiled into the jar.

1. `POST {base.url}/sps/gspas/active/vehicles/ecus/functionalSteps`. The body is `eventId`,
   `rpoContent`, the ECU list, `vin`, `fieldActionNumber`, and `autoSubmitEligible`. The response
   replaces the ECU list with functional steps. A step carries `pciSegmentId`, `asIsPartNumbers`,
   `parts`, and `requestMethods`.
2. A native read of the controllers runs between that call and the next one. It fills the as-is
   part numbers. It does not download a file.
3. `POST {base.url}/sps/gspas/active/vehicles/ecus/functionalSteps/parts`. The body is the vehicle
   after the step above. This is the call SPS3 names "get programming data".

Each part in that response carries `number`, `url`, `checkSum`, `size`, and `moduleId`. A part may
also carry `manifestPart`, `signaturePart`, and `internalParts`. The operating-system slot in this
VIN's catalog is part `23394159`. In SPS3 that number is its own part, with its own URL, beside the
calibration part numbers. The parts response is what fills the URL. This call has not been sent, so
the URL for `23394159` is not known yet. The stored catalog has the part number and the label
"Operating system". It does not have `rpoContent` or the part URL.

Parts that already have a checksum, a number, a URL, and a size are downloaded. Missing any of
those, the client skips the part. One token is requested per part that is not already in the cache:

`POST {base.url}/cdn/files/gspas/credentials`

The body is `{"numberOfTokens": N}`. The response is `{"tokens": [...]}`.

The file GET is `{part.url}/{part.number}`. The token is the `Cookie` header. The file is fetched in
10,000,000-byte chunks, each with a `Range` header. The joined file is checked against `checkSum`
and written to `%USERPROFILE%\sps\spsCache\spsCacheInternal\{number}`. A file already there under
that number is not fetched again.

A programming step (PCI segment 1) keeps that cache file as the part. Ethernet (13) and the two
large-delta segments (2 and 5) take a second pass. A part whose `moduleId` is 0 is copied as itself.
A part that has `internalParts` is unzipped. The manifest is `{number}.mnf`, the signature is
`{number}.smd`, and each internal part is the file named by its part number. Those files are then
gzipped into `%USERPROFILE%\sps\spsCache\spsCacheInternal\archive`. The native library
(`spsvcs.dll` 7.2.11) names an application-software partition and a calibration partition in its
error strings, and it checks that the software part in the manifest is in the part-number list.
The manifest is what says which file is which. This note stops at the file on disk.

`TechUpdate`, `ForceTechUpdate`, `TechResidentUpdate`, and `GetPossibleSWDLActions` are exports of
that same DLL. In this build the `TechUpdate` export logs the call and returns without building a
URL. The download the Java client actually performs is the parts POST and the per-part GET above.

## USB copy

The USB drive screen opens for a function only when that function's method is `USB_COPY`,
`USB_COPY_BSC`, `USB_COPY_BY_VCI`, or `USB_COPY_BY_VCI_BSC`. Normal and VCI go to the calibration
summary instead. On `1G1RD6S58HU102764` no function has those four ids. Radio (`A11`), Radio Controls
(`A22`), the Audio Amplifier (`T3`), and the Human Machine Interface (`K74`) are Normal and VCI, the
same pair as the brake module.

A GSPAS event can still open that screen without those method ids. `isLargeFileTransferUsb` is true
when any step's PCI segment is `LARGEFILETRANSFER` (3). The other large segments do not: large delta
is 2, large delta with programming is 5, large map is 10, and ethernet is 13. The fixture stored for
this VIN does not carry a PCI segment, so that flag is only visible after programming data comes
back. The landing-page mode Infotainment Service is a third list and does not itself select the USB
drive.

Once a drive is selected, USB Copy and a large-file step use the same fetch. The programming-data
response is what names the file. USB Copy and USB Copy with block-same-cal use `/getProgrammingData`.
USB Copy by VCI uses `/getVciProgrammingData`. A GSPAS large-file step uses `/getProgrammingDataGspas`.
Each unit in that response has a blob name, a blob id, a download id, and the server list. The SPS2
service base is `ClientApplicationContext.getServerUrl()`, filled from the Techline session. It is
not compiled into the jar.

`CalDownloadService.download` then does two attempts, in order:

1. `GET {server URI}/{downloadId}` with `Authorization: bearer` and the Techline access token. An
   Akamai server also sends the Akamai cookie. A 200 is written to `{SPS cache}/{blobName}`. The
   default cache is `C:\ProgramData\GM\TDM\SPS Cache`. The same blob name replaces the file already
   there.
2. If that GET fails, or the server list is empty, `POST {serverUrl}/getCalibrationFile`. The body
   is `DownloadCalibrationFileRequest`: the VIN's service id, `isArchive` false, `partNo` set to the
   blob name, and download id `0`. The response stream is written to the same cache path.

The zip is then unpacked at the root of the selected drive. The client writes
`indication.{blobName}.{blobId}` there, one line, the unit checksum in hex. A later run that finds
a matching indication file skips the unpack. A GSPAS package that contains a `.mnf` entry also
`POST`s `/sps/gspas/active/vin-verification` (the VIN plus that manifest as the `file` part) and
writes the returned hash as `{VIN}.lic` on the drive. A package with no `.mnf` skips the license
file. A GSPAS event can upload a blob with `PUT /sps/gspas/active/events/{id}/blob`.

For PCI segment 3 the download is the whole step. After the package validates, the client marks
that step successful and does not keep going into the normal calibration summary. Segments 2, 5,
10, and 13 stay on the cache path: ethernet and delta files land under `{cache}/archive/{stepId}/`,
and an ethernet blob uses the `.smd` extension.

None of these objects are on the CDN that served `SPS2.msi`. This VIN's catalog has no USB-copy
method, and the stored fixture has no PCI segment, so the blob name and the server URI are not
known until one of those programming-data calls returns.
