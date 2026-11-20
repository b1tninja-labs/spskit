# spskit

Download the service-programming modules an ACDelco TDS subscription is licensed for, without the Java
Techline Connect client.

Copy `.env.example` to `.env` and fill in the username and password on this machine. `spskit login`
posts that password and asks the sign-in host to email a code. The challenge is written to the session
file. `spskit code` asks for the code and finishes the sign-in. Run `spskit code` again if the
connection drops; that does not send another email. The code itself is not saved. The access token is
written to `session.json` in `SPS_DOWNLOAD_DIR`, or to `TDS_TOKEN_FILE` when that path is set. Later
commands read it and do not print it. The sign-in password is `TDS_NEW_PASSWORD` when that is set, and
`TDS_PASSWORD` otherwise. `spskit session` stores an access token you already hold.
`spskit token --redirect` exchanges a `https://www.acdelcotds.com/#code=...` URL from a login you
started yourself; set `TDS_CODE_VERIFIER` to that login's verifier.

```
python -m spskit modules --id 25
python -m spskit download --id 25
python -m spskit downloads
python -m spskit downloads --get
python -m spskit sps --vin <VIN>
```

`spskit downloads` lists every file version the signed-in license can see. `spskit downloads --get`
stores each one under `SPS_DOWNLOAD_DIR/cache/{id}/{version}/` and skips a file that is already
there. Add `--refresh` to fetch it again.

`spskit sps --vin` writes that vehicle's module catalog to `spsinfo.sqlite` in the download directory.
`vit1.programming_data_request()` builds the programming-data body for the method-128 reads on
this VIN from a saved module read and returns it.

Files are written to `SPS_DOWNLOAD_DIR`. This package does not program a vehicle. The dongle belongs to
`vcxtoolkit`. The split is `docs/tool-boundary.md`. SAE J2534 is not in the source library yet.

Standard library only. Apache-2.0.
