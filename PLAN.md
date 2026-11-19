# spskit: plan

An open-source replacement for the Java Techline Connect / SPS2 client, which is built for a bundled
Java 11 and does not run well on current Java. Registered 2026-11-19, untiered and unsequenced.
It sits beside `obd-bridge` and the `volt` research notes. It is a downloader for modules the person's
own ACDelco TDS subscription is licensed for.

## 1. What this slice does

- Reads ACDelco / GM TDS settings from `.env`. `.env.example` ships with empty secrets. `.env` is gitignored.
- Lists the versions of one resource the permissions call returns, and does not keep the account id.
- Asks the gateway for a download grant and writes the file under `SPS_DOWNLOAD_DIR`, which must be an absolute path.
- `spskit downloads` lists the Techline Connect installer and any other decimal resource the account can run.
  `spskit downloads --get` writes those files in the same directory.
- `spskit login` posts the password and asks the host to email a code. It writes the challenge to the
  session file and does not write the code. `spskit code` reads that challenge, waits for the code, and
  writes the access token from the redirect. A dropped connection retries, and `spskit code` can be
  repeated without another email.
- `spskit session` prompts for an access token the person already holds and writes it to
  `SPS_DOWNLOAD_DIR/session.json`, or to `TDS_TOKEN_FILE` when that absolute path is set. Later commands
  load it when `TDS_ACCESS_TOKEN` is empty.
- A gateway 401 is reported as an expired session. The command does not invent a code to send.

## 2. What it does not do

- The sign-in password is posted as `passwd`. A separate captured reset, not used by `spskit login`,
  sends `newPassword`. Neither value is sent to the token endpoint.
- It does not talk to a vehicle. Programming a controller is a later step and needs the VCX/VXDIAG J2534
  pass-through. ISO 14229-1:2013 clause 15.4.4 names SAE J2534 as the link between the application and the
  service-tool hardware, and says the vehicle side uses manufacturer-proprietary information. SAE J2534 is not
  in `primarysource`, so `obd-bridge` does not grow a pass-through in this change, and this package does not
  invent one.
- It does not implement security access or a calibration transfer.

## 3. Commands

From this directory:

    copy .env.example .env
    python -m spskit modules --id 25
    python -m spskit download --id 25
    python -m spskit downloads
    python -m spskit downloads --get
    python -m spskit login
    python -m spskit code
    python -m spskit session
    python -m spskit verify < challenge.json
    python -m spskit token --redirect "https://www.acdelcotds.com/#code=..."

`verify` reads the challenge the sign-in host returned and prompts for the code. Fill in `.env` on this machine.
Do not commit it.
