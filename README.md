# spskit

Download the service-programming modules an ACDelco TDS subscription is licensed for, without the Java
Techline Connect client.

Copy `.env.example` to `.env` and fill in the username and password on this machine. `spskit login`
posts that password, asks the sign-in host to email a code, and waits for you to type it. The code is
not saved. The access token is written to `session.json` in `SPS_DOWNLOAD_DIR`, or to `TDS_TOKEN_FILE`
when that path is set. Later commands read it and do not print it. The sign-in password is
`TDS_NEW_PASSWORD` when that is set, and `TDS_PASSWORD` otherwise. `spskit session` stores an access
token you already hold. `spskit token --redirect` exchanges a `https://www.acdelcotds.com/#code=...`
URL from a login you started yourself; set `TDS_CODE_VERIFIER` to that login's verifier.

```
python -m spskit modules --id 25
python -m spskit download --id 25
```

Files are written to `SPS_DOWNLOAD_DIR`. This package does not program a vehicle. That step needs a J2534
pass-through, and SAE J2534 is not in the source library yet.

Standard library only. Apache-2.0.
