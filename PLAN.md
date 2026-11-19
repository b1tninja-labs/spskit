# spskit: plan

An open-source replacement for the Java Techline Connect / SPS2 client, which is built for a bundled
Java 11 and does not run well on current Java. Registered 2026-11-19, untiered and unsequenced.
It sits beside `obd-bridge` and the `volt` research notes. It is a downloader for modules the person's
own ACDelco TDS subscription is licensed for.

## 1. What this slice does

- Reads ACDelco / GM TDS settings from `.env`. `.env.example` ships with empty secrets. `.env` is gitignored.
- Lists the versions of one resource the permissions call returns, and does not keep the account id.
- Asks the gateway for a download grant and writes the file under `SPS_DOWNLOAD_DIR`, which must be an absolute path.
- When the sign-in host returns a verification challenge, prompts for the code, posts it to the path the host named,
  and does not write the code into `.env` or onto the settings object.
- `spskit session` prompts for the access token from the email and writes it to `SPS_DOWNLOAD_DIR/session.json`,
  or to `TDS_TOKEN_FILE` when that absolute path is set. Later commands load it when `TDS_ACCESS_TOKEN` is empty.
- A gateway 401 is reported as an expired session. The command does not invent a code to send.

## 2. What it does not do

- The captured password step is a reset. It sends `newPassword` from `TDS_NEW_PASSWORD`, or from
  `TDS_PASSWORD` when that is the only password set. It does not send either value to the token endpoint.
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
    python -m spskit session
    python -m spskit verify < challenge.json
    python -m spskit token --redirect "https://www.acdelcotds.com/#code=..."

`verify` reads the challenge the sign-in host returned and prompts for the code. Fill in `.env` on this machine.
Do not commit it.
