# spskit

Download the service-programming modules an ACDelco TDS subscription is licensed for, without the Java
Techline Connect client.

Copy `.env.example` to `.env` and fill in the username and password on this machine. When a session expires
and the sign-in host asks for a code, run `spskit verify` and type the code. It is not saved.
`spskit token --redirect` exchanges the `https://www.acdelcotds.com/#code=...` URL from that login.
Set `TDS_CODE_VERIFIER` to the verifier for that login and `TDS_TOKEN_FILE` to an absolute path.
The token is written there and is not printed. If that login then asks for a password reset, the PUT
sends `TDS_NEW_PASSWORD`, or `TDS_PASSWORD` when the new one is empty.

```
python -m spskit modules --id 25
python -m spskit download --id 25
```

Files are written to `SPS_DOWNLOAD_DIR`. This package does not program a vehicle. That step needs a J2534
pass-through, and SAE J2534 is not in the source library yet.

Standard library only. Apache-2.0.
