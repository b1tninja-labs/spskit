# Sources

Shapes below are field names from the person's own captures of ACDelco TDS and Techline Connect on
2026-11-19. Values that identify an account, a token, or a code are not copied here.

## Sign-in

The sign-in host is `gmb2bciamprod.ciamlogin.com`. `spskit login` follows the password form, then the
email code. It does not call password recovery.

`GET /{tenant}/oauth2/v2.0/authorize` returns a page titled Redirecting whose `$Config` has no `sFT`.
The next GET is that same URL with `sso_reload=true`, and that page carries `sFT` and `sCtx`. `POST /common/GetCredentialType` sends `username`, `flowToken`
(`sFT`) and `originalRequest` (`sCtx`). `POST /{tenant}/login` is the form the browser posted: `passwd`,
`ps=2`, `isReactBundle=1`, `canary`, `ctx`, `hpgrequestid`, `flowToken`, `NewUser=1`, `fspost=0`,
`i21=0`, `CookieDisclosure=0`, `IsFidoSupported=1`, `isSignupPost=0`, `i13=0`, `login`, `loginfmt`,
`type=11`, `LoginOptions=3`, and the empty `psRNGC*`, `PPSX`, `FoundMSAs`, `lrt`, `lrtPartition`,
`hisRegion` and `hisScaleUnit` fields. `passwd` is `TDS_NEW_PASSWORD` when that is set, and
`TDS_PASSWORD` otherwise. `sErrorCode` `50126` is a rejected password. The password POST can instead return the Redirecting
page (`stsErrorCode` `50168`) whose `oPostParams` are the same form and whose `urlPost` is
`/{tenant}/login`. The browser posts that form to `urlPost` with `sso_reload=true` and the cookie
named by `bsso.cookieNames.ssoPulled` (`SSOCOOKIEPULLED`). That response is page `FabricTFA`
(`stsErrorCode` `50074`), the email step.

`POST /common/SAS/BeginAuth` sends `AuthMethodId` `Email`, `Method` `BeginAuth`, `ctx` and `flowToken`.
A success is `Success` true, `ErrCode` 0 and `ResultValue` `Success`, with a new `FlowToken` and `Ctx`.
The code length on that page is `iEmailOtcLength` (8). The command then waits for the person to type it.

`POST /common/SAS/ProcessAuth` sends `otc`, `canary`, `flowToken`, `request`, `login`, `hpgrequestid`
and `mfaAuthMethod` `Email`. That response is the Redirecting page again (`stsErrorCode` `50168`),
and its `oPostParams` include `otc`. Posting that form to `urlPost` with `sso_reload=true` and the
`ssoPulled` cookie returns the next page. A rejected code is page `FabricTFA` with `sErrorCode`
`InvalidOneTimePasscode`. An accepted code is `KmsiInterrupt` (`sErrorCode` `50140`, `urlPost` `/kmsi`).
The host can instead return `CmsiInterrupt` (`stsErrorCode` `399218`, `urlPost` `/appverify`). That post
sends `ContinueAuth=true`, `ctx`, `hpgrequestid` from `sessionId`, `flowToken`, `canary`,
`iscsrfspeedbump=false` and `i19`. The next page is the stay-signed-in form.
`InvalidOneTimePasscode` keeps the same email and returns a new flow token; the command asks again
and does not call `BeginAuth` a second time.
`POST /kmsi` sends `LoginOptions=1`, `type=28`, `ctx`, `hpgrequestid` from the page `sessionId`, `flowToken`, `canary` and `i19`.
That response can be the 302, or the Redirecting page (`stsErrorCode` `50168`) whose `oPostParams` are the same form.
Posting that form back to `urlPost` with `sso_reload=true` returns the 302.
The response is a 302 whose `Location` is `https://www.acdelcotds.com/#code=...`.

A separate captured path, not used by `spskit login`, is password recovery. That JSON challenge has
`state` `verificationRequired`, `codeLength`, `continuationToken` and `_links.verify.href`. The verify
call posts `continuationToken` and `otp`. When that path continues into a reset, `_links.next` is
`recover`. `recover` posts `continuationToken` and returns `state` `methodUpdateRequired` with an
`update` link. The update is a PUT of `continuationToken` and `newPassword`. A 504 is retried once.
`methodUpdatePending` is polled with `continuationToken` only, up to five times, until `state` is
`continue`. `passwd` is not a field on that PUT.

## Access token

The browser lands on `https://www.acdelcotds.com/#code=...`. The token call is
`POST /{tenant}/oauth2/v2.0/token` with form fields `client_id`, `redirect_uri`, `scope`, `code`,
`code_verifier`, `grant_type=authorization_code` and `client_info=1`. The request sends `Origin`
for the redirect site, because this public client only redeems a code on a cross-origin call. The response has `token_type`,
`access_token` and `refresh_token`. Only the access token is kept.

`GET https://token.gen.acdelcotds.com/api/tds-backend` returns the API Management bearer. It is not
stored. `POST https://backend.acdelcotds.com/api/v1/login?zoneId=America/Los_Angeles` sends that bearer
in `Authorization` and the access token in `X-EEID-Access-Token`, with `Origin` and `Referer` for the
TDS site and an empty body. The access-token header is sent with that spelling. The profile in the
response is discarded. The access token is written before this call, so a refused login can be retried
without a new email code.

`spskit login` stops after BeginAuth and writes the challenge, the code verifier, and the sign-in
cookies to the session file. `spskit code` reads that file and posts the typed code. Once the code is
accepted, the stay-signed-in form is written before it is posted. A closed connection is retried with
a pause of one, then two, then four seconds. `spskit code` can be run again on the saved challenge.
The access token from the exchange is what the file keeps afterwards. `spskit session` can also store
an access token the person already holds. The eight-character email code is a different prompt and is
not written to that file.

## Gateway

`GET /acl/cdl/resources/{id}/permissions` returns `resourceVersions` with `cdlResourceId`,
`cdlResourceName`, `cdlResourceDescription`, `cdlResourceTypeCode` and `versionNumber`. The account id
on `cdlPermission` is ignored.

`POST /cdn/files/public/downloadCredentials` takes `downloadCredentials` of one object
(`humanReadableName`, `versionNumber`, `cdlResourceType`, empty `url`, `tokenData`, `tokenType`,
`headers`, `md5` and `filename`). The response fills `url`, `filename` and `headers` (a `Cookie`
when the file needs one). The file is fetched from that https URL.

The captured calls did not send an `Authorization` header. `TDS_ACCESS_TOKEN`, when set, is sent as
a bearer because a later licensed call may require the session the child-token call returns. An empty
token sends no authorization header.

## Techline Connect launch

The TDS page does not start `TLCSuite.exe`. An access click calls
`GET /api/v1/subscriptions/vin/access/{slot}` or `GET /api/v1/subscriptions/access/{id}`. The SPS
calibration link calls `GET /api/v1/spsCallibration/accessSPSCal`. Each returns HTML titled
`SPOREF Redirection`. The page writes that document into a new window, and the body submits
`redirectForm`.

The form is `POST https://tlc-dmz-gateway.ext.gm.com/authorization/oauth/user/sporef/ui`. The captured
VIN form sends `appParm` `techpd`, `portal_ID` `ACDelco` and `group` `OMUSER,na_SPS2`, plus `ticket`,
`idpaccesstoken`, `acdsub`, `user`, `origin` and `sporefGPLDIP`. `tdsToken` was empty. The calibration
link sends `appParm` `sps2info` and `group` `ACDELCO`, and that post returns the SPS Info page
(`/spsinfo-ui/`), which is a web page.

The installed client is started from `https://tlc-dmz-gateway.ext.gm.com/tlc-web/`, whose page calls
itself the Techline Connect launcher. Its launch button sets `document.location` to a `tlc:` URL.
`TLCLauncher.exe` strips the `tlc:,` prefix and reads thirteen comma-separated fields:
`TLC_BROWSE_LAUNCH`, `TLC_ENVIRONMENT`, `TLC_LOGIN_SESSION_ID`, `TLC_LOGIN_SECURITY_ID`,
`TLC_LOGIN_JSESSION_ID`, `TLC_LOGIN_SI_AUTH`, `TLC_LOGIN_AS_ADMIN`, `TLC_TDS_REST_TOKEN`,
`TLC_ACCESS_TOKEN`, `TLC_REFRESH_TOKEN`, `IBM_GATEWAY_URI`, `IBM_CLIENT_ID`, `IBM_CLIENT_SECRET`.
The button sends `Y`, the environment name `prod`, `Y` or `N` for the admin checkbox, and the access
and refresh tokens from `GET /oauth/user/token/child?tokenType=tum2`. The other fields are the literal
`NA`. Those tokens are not written here.

The same page downloads the installer with `POST /cdn/files/public/downloadCredentials` for
`TLC Installer` `26.8.31.0` `INITIAL_SOFTWARE`. The file is
`https://tlc-cdn.gm.com/cache-downloads/public/Prod/TLC_Installer/26_8_31_0/TLCSuite.exe`.

## Vehicle programming

ISO 14229-1:2013 clause 15.4.4 (cited through `primarysource`) names SAE J2534 as the communication
between the application and the service-tool hardware, and says communication to the vehicle uses
manufacturer-proprietary information. The SAE document is not imported. No pass-through API is written
from memory.
