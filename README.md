# spskit

Download the service-programming modules an ACDelco TDS subscription is licensed for, without the Java
Techline Connect client.

Copy `.env.example` to `.env` and fill in the username and password on this machine. When the access
token arrives by email, run `spskit session` and paste it. The session file is `session.json` in
`SPS_DOWNLOAD_DIR`, or `TDS_TOKEN_FILE` when that path is set. Later commands read it and do not print it.
When the sign-in host asks for a verification code, run `spskit verify` and type the code. That code is not
saved. `spskit token --redirect` exchanges the `https://www.acdelcotds.com/#code=...` URL from that login.
Set `TDS_CODE_VERIFIER` to the verifier for that login. If that login then asks for a password reset, the PUT
sends `TDS_NEW_PASSWORD`, or `TDS_PASSWORD` when the new one is empty.

```
python -m spskit modules --id 25
python -m spskit download --id 25
```

Files are written to `SPS_DOWNLOAD_DIR`. This package does not program a vehicle. That step needs a J2534
pass-through, and SAE J2534 is not in the source library yet.

Standard library only. Apache-2.0.
