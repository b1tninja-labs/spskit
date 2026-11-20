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
  `partno` per part DID (4 bytes from byte 1), and `ssecuhn` as the hardware string the reader
  stored. K9 adds part DIDs `$41` through `$4A`. K20 carries `cvn_in_vit1` as `1` or `0`. A `1`
  also carries `partnum` values, each a part string, a hyphen, and a decimal. The function returns
  the body. Gson writes `type`, not a Jackson `@type`, on the VIN and the option composite.
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
- It does not talk to a vehicle. Programming a controller is a later step and needs the VCX/VXDIAG J2534
  pass-through. ISO 14229-1:2013 clause 15.4.4 names SAE J2534 as the link between the application and the
  service-tool hardware, and says the vehicle side uses manufacturer-proprietary information. SAE J2534 is not
  in `primarysource`, so `obd-bridge` does not grow a pass-through in this change, and this package does not
  invent one.
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
