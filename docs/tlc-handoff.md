# Launcher handoff

TUM does not sign in. The browser page `tlc-web` already holds an access token and a refresh
token, mints a `tum2` child of that pair, and puts the child values on the `tlc:` URL that
`TLCLauncher.exe` turns into TUM's thirteen arguments. This is the `tlc-web` script
`static/js/main.c202f1fe.js` and `env.js` on `https://tlc-dmz-gateway.ext.gm.com/tlc-web/`.

## What the page treats as signed in

On load, `tlc-web` reads two cookies, `BROWSER_ACCESS_TOKEN` and `BROWSER_REFRESH_TOKEN`.
Both have to be present. If either is missing it also tries `localStorage` under those same
names, and both reads use the access-token key, so that fallback does not recover a distinct
refresh token. With both values, the page stores them again (localStorage and a cookie on
path `/tlc-web`, domain `window.env.DOMAIN`, which `env.js` sets to `.gm.com`) and opens
`/launch`. Otherwise it opens `/not-authorized`.

Every gateway call from that page sends `Authorization: Bearer` plus the stored access token.
A 401 posts `oauth/user/token/refresh?refreshToken=` plus the stored refresh token. A success
body has `accessToken.tokenValue` and `refreshToken.tokenValue`, and those replace the stored
pair. Production `env.js` sets `TLC_GATEWAY_URL` to `https://tlc-dmz-gateway.ext.gm.com` and
`TUM_ENV_NAME` to `prod`.

## The launch URL

The launch button calls `GET /oauth/user/token/child?tokenType=tum2` with that bearer. The
body uses the same wrappers: `accessToken.tokenValue` and `refreshToken.tokenValue`. The page
then sets `document.location` to one comma-separated `tlc:` URL:

| Field | Value |
| --- | --- |
| `TLC_BROWSE_LAUNCH` | `Y` |
| `TLC_ENVIRONMENT` | `prod` |
| `TLC_LOGIN_SESSION_ID` | `NA` |
| `TLC_LOGIN_SECURITY_ID` | `NA` |
| `TLC_LOGIN_JSESSION_ID` | `NA` |
| `TLC_LOGIN_SI_AUTH` | `NA` |
| `TLC_LOGIN_AS_ADMIN` | `Y` or `N` from the admin checkbox |
| `TLC_TDS_REST_TOKEN` | `NA` |
| `TLC_ACCESS_TOKEN` | the `tum2` access token |
| `TLC_REFRESH_TOKEN` | the `tum2` refresh token |
| `IBM_GATEWAY_URI` | `NA` |
| `IBM_CLIENT_ID` | `NA` |
| `IBM_CLIENT_SECRET` | `NA` |

`TLCLauncher.exe` strips the `tlc:,` prefix and starts TUM with those thirteen values.
TUM copies fields 8 and 9 into its own token, then calls
`GET /oauth/user/token/child?tokenType=tlc` before it starts `TechlineConnectLaunch.exe`.
That second child token is documented in [tum-auth.md](tum-auth.md). The `tum2` type is not
in the TUM jar. Only the browser asks for it.

## Where spskit is

`spskit login` ends at an EEID access token for `backend.acdelcotds.com`. The SPS Info
handoff is `GET /api/v1/spsCallibration/accessSPSCal`, then
`POST /authorization/oauth/user/sporef/ui` with `appParm` `sps2info`. That response sets
`SPS-INFO_ACCESS_TOKEN`. Gateway ACL and the public download grant accept that value as
`Authorization: Bearer`. `GET /oauth/user/token/child` does not: the SPOREF cookies alone
are 401, and the SPS Info bearer is `UTS113`.

The TDS app opens a vehicle through `GET /api/v1/subscriptions/vin/access/{slot}` or
`GET /api/v1/subscriptions/access/{id}`. The captured vehicle form uses `appParm` `techpd`.
That is the handoff that has to leave the browser tokens the launcher reads. A live
`GET /api/v1/subscriptions` for this account returned one product, Service Programming
System (SPS2) VIN, and `GET /api/v1/subscriptions/vin` returned no slots. Calling
`/subscriptions/access/{id}` for that product returned SPOREF code 1003
(`Exception while sending request to SPOREF`), so the `techpd` form and the cookie names
on its response were not observed. The next step is that form, once a VIN occupies a slot.
