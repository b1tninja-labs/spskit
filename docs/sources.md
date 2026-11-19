# Sources

Shapes below are field names from the person's own captures of ACDelco TDS and Techline Connect on
2026-11-19. Values that identify an account, a token, or a code are not copied here.

## Sign-in

The sign-in host is `gmb2bciamprod.ciamlogin.com`. `spskit login` follows the password form, then the
email code. It does not call password recovery.

`GET /{tenant}/oauth2/v2.0/authorize` returns the page whose `$Config` carries `sFT` and `sCtx`. A first
response without `sFT` is loaded again. `POST /common/GetCredentialType` sends `username`, `flowToken`
(`sFT`) and `originalRequest` (`sCtx`). `POST /{tenant}/login` is the form the browser posted: `passwd`,
`ps=2`, `isReactBundle=1`, `canary`, `ctx`, `hpgrequestid`, `flowToken`, `NewUser=1`, `fspost=0`,
`i21=0`, `CookieDisclosure=0`, `IsFidoSupported=1`, `isSignupPost=0`, `i13=0`, `login`, `loginfmt`,
`type=11`, `LoginOptions=3`, and the empty `psRNGC*`, `PPSX`, `FoundMSAs`, `lrt`, `lrtPartition`,
`hisRegion` and `hisScaleUnit` fields. `passwd` is `TDS_NEW_PASSWORD` when that is set, and
`TDS_PASSWORD` otherwise. `sErrorCode` `50126` is a rejected password. `sErrorCode` `50074` (page
`FabricTFA`) is the email step.

`POST /common/SAS/BeginAuth` sends `AuthMethodId` `Email`, `Method` `BeginAuth`, `ctx` and `flowToken`.
A success is `Success` true, `ErrCode` 0 and `ResultValue` `Success`, with a new `FlowToken` and `Ctx`.
The code length on that page is `iEmailOtcLength` (8). The command then waits for the person to type it.

`POST /common/SAS/ProcessAuth` sends `otc`, `canary`, `flowToken`, `request`, `login`, `hpgrequestid`
and `mfaAuthMethod` `Email`. The next page is `KmsiInterrupt` (`sErrorCode` `50140`, `urlPost` `/kmsi`).
`POST /kmsi` sends `LoginOptions=1`, `type=28`, `ctx`, `hpgrequestid`, `flowToken`, `canary` and `i19`.
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
`code_verifier`, `grant_type=authorization_code` and `client_info=1`. The response has `token_type`,
`access_token` and `refresh_token`. Only the access token is kept.

`POST https://backend.acdelcotds.com/api/v1/login?zoneId=America/Los_Angeles` sends that token in
`X-EEID-Access-Token` and an empty body. The profile in the response is discarded.

`spskit login` keeps the access token from that exchange in the session file. `spskit session` can
also store an access token the person already holds. The eight-character email code is a different
prompt and is not written to that file.

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

## Vehicle programming

ISO 14229-1:2013 clause 15.4.4 (cited through `primarysource`) names SAE J2534 as the communication
between the application and the service-tool hardware, and says communication to the vehicle uses
manufacturer-proprietary information. The SAE document is not imported. No pass-through API is written
from memory.
