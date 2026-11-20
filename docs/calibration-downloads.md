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
path on the SPS2 service base (the base is the Techline session, not a host compiled into the jar):

| Method | Service | Path |
| --- | --- | --- |
| Normal | `ProgrammingDataService` | `/getProgrammingData` |
| VCI | `ProgrammingDataVciService` | `/getVciProgrammingData` |
| GSPAS | `ProgrammingDataGspasService` | `/getProgrammingDataGspas` |

The request carries the client state, the VIN, the programming method, and the sequence. The
response is a list of `ProgrammingDataUnit`. Each unit has a blob name, a blob size, a download id,
and a list of `DownloadServer`. A server is a `CALDownloadServer` (a URI, plus secured and Akamai
flags) or a `DLSDownloadServer` (a URI, an Akamai flag, and a description).

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

Reprogram is a programming mode (`programming.mode.reprogram`). It does not have its own download
URL. `DOWNLOAD_PROG_FILES_TASK` runs first and fetches every unit the programming-data response
named, through the GET and the `/getCalibrationFile` POST above. `REPROGRAM_VEHICLE_TASK` then
reads those blobs (`getCalibrationFiles`, `getProgrammingDataUnits`). It does not request a second
file.

On a module, `currentSoftware` and `selectedSoftware` are the software part shown on the calibration
summary and sent with the result. They are fields on `SPSModule`, not a request. The part's
calibration list hangs off that same part (`getCalibrationParts`). For this VIN the operating-system
part is already in that list: slot 1, `23394159`, label "Operating system", beside the electronic
brake parts. Same cache path, same blob-name rule.

The word firmware in this SPS2 build is the J2534 tool's own version (`J2534Version`), not a vehicle
file. A type-4 event is a different download, `POST /getType4App`, and it is not the Reprogram mode.

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
