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
(`humanReadableName`, `versionNumber`, `cdlResourceType`, `tokenType` `TUM`, empty `url`,
`tokenData` `{value, expirationTime}`, `headers`, `md5` and `filename`). An empty-string
`tokenData` is refused by the gateway. The response fills `url`, `filename` and `headers` (a `Cookie`
when the file needs one). The file is fetched from that https URL.

The 2026-11-19 gateway captures returned 200 with no `Authorization` header and no `X-` request
header in the export. Chrome's HAR export also omitted `Cookie` and `Set-Cookie`, so those names
are not in the files. A live check after the same SPOREF handoff showed the names the gateway set:
`SPS-INFO_ACCESS_TOKEN`, `GMWP_location`, `_abck`, `bm_sz`, `AKA_A2` and `ak_bmsc`. Sending only
those cookies, with no `Authorization` header, was a 401. Sending the `SPS-INFO_ACCESS_TOKEN` value
as `Authorization: Bearer` was a 200 on `GET /acl/cdl/resources/25/permissions`, including when the
jar was empty. The EEID access token is not that bearer. It stays on `backend.acdelcotds.com` as
`X-EEID-Access-Token`.

Before those ACL calls, when an access token is loaded, the client repeats the SPOREF handoff:
`GET /api/v1/spsCallibration/accessSPSCal` (EEID header on the backend) and
`POST /authorization/oauth/user/sporef/ui` (no EEID header). It then reads `SPS-INFO_ACCESS_TOKEN`
from the jar and sends that value as the gateway bearer. A gateway 401 is reported as a refused
gateway session, not as an expired TDS session.

In the download capture the order is: an Akamai sensor `POST` (201), then
`GET /acl/cdl/resources/25/permissions` (200), then `POST /cdn/files/public/downloadCredentials`
(200), then `HEAD` of the CDN object (200), then `GET /oauth/user/token/child?tokenType=sps-info`
(200, response key `accessToken`). The child-token call is after permissions and
`downloadCredentials`, so it does not establish those calls. The request body field `tokenType` is
three characters; the value is not stored. The grant's `headers` object uses the name `Cookie` for
the CDN fetch.

The other capture is SPS Info, also with no `Authorization` header: captcha id, image, and validate,
then `GET /spsinfo/vin/fixture/{vin}`, then `POST /spsinfo/progseq`. Neither capture contains the
SPOREF post itself.

The captured browser sent `User-Agent` for Chrome 157 on Windows. This client sends that same agent.
It does not send `Python-urllib`.

## Licensed files

The Techline Connect launcher lists what the signed-in account may open with
`POST /acl/permissions/search` and a body of `{}`. The response is `resourcePermissions`, and each
item has `resourceId` and `runnable`. A UUID is a launcher tab. A decimal id is a file. `userId` is
not stored.

The download button does not use that list for the installer. It always reads
`GET /acl/cdl/resources/25/permissions` and posts the first `resourceVersion` to `downloadCredentials`.
Resource 25 is `TLC Installer`, type `INITIAL_SOFTWARE`, and the grant's filename is `TLCSuite.exe`.
`spskit downloads` unions four lists: resource 25, resource 1, every runnable decimal id from
`POST /acl/permissions/search`, every decimal id from `GET /acl/cdl/resources/prelaunch`
(`resultList`, or `cdlResources` on the update-manager model), and every version from
`GET /acl/cdl/permissions/search`. A UUID is still a page. A version with `disabled`
true is omitted. `spskit downloads --get` writes each version under
`SPS_DOWNLOAD_DIR/cache/{id}/{version}/`. A file already in that directory is left in place.
A later version is a sibling directory, so the older file stays for comparison. The permissions
document for a resource currently lists one version. A disabled row is omitted, and the five
resources checked on 2026-11-19 (`1`, `5`, `7`, `10`, `25`) each had one enabled version and no
disabled row. The CDN directory of that object answers with the same cached NetStorage redirect,
so it does not provide the missing older names.
`spskit downloads --get --refresh` fetches it again. A cached edge redirect to
`*.stor.lb.akamai.net` is reported and not followed. That name is Akamai NetStorage, and public DNS
has no address for it. Download Delivery caches the 302, so another request to the same edge repeats it.

The launcher script `tlc-web/static/js/main.c202f1fe.js` posts that same public body and passes the
returned `url` and `filename` to FileSaver `saveAs`. FileSaver checks the URL with a HEAD and then
downloads it. It does not call NetStorage. TUM's `DownloadFileService` opens the grant URL with
`URLConnection`, sets `Cookie` and `Range`, and does not set `User-Agent`. The bundled Corretto's
`java.version` is `11.0.19`, and `HttpURLConnection` sends `Java/11.0.19`. The file GET uses that
agent. It reads `Content-Length`, and requests `Range: bytes=` in 5000000-byte chunks. A live
public grant for TUM2 is `https://tlc-cdn.gm.com/cache-downloads/public/Prod/TUM2/26.8.28.0.zip`
with a `Cookie` and no query. `GET /oauth/user/token/child` is a separate call: the SPOREF cookies
alone are 401, and the SPS-INFO bearer is `UTS113`. TUM's `POST /cdn/files/downloadCredentials`
answers 403 for this session. The download this login can make is the public grant URL.

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
`NA`. Those tokens are not written here. The page that holds the token, and the call that mints the
`tum2` child, are recorded in [tlc-handoff.md](tlc-handoff.md).

The same page downloads the installer with `POST /cdn/files/public/downloadCredentials` for
`TLC Installer` `26.8.31.0` `INITIAL_SOFTWARE`. The file is
`https://tlc-cdn.gm.com/cache-downloads/public/Prod/TLC_Installer/26_8_31_0/TLCSuite.exe`.

`TLCSuite.exe` installs three pieces: a bundled JDK, `TLCLauncher.exe`, and `TUM.exe`. The file
layout, the binwalk hits, the Ghidra view of the stub, and the gateway calls inside TUM are
recorded in [tlc-binaries.md](tlc-binaries.md). The programs, the extracted jars, and the
decompiled tree are kept in `local/tlc/`, which is gitignored.

TUM calls the gateway with `Authorization: bearer` plus its own access token, and
`Content-Type: application/json`. It refreshes that token at `GET /oauth/user/token/refresh`
and asks for a child token at `GET /oauth/user/token/child` with `tokenType` `tlc`. The production
base URL in its `application.yml` is `https://tlc-dmz-gateway.ext.gm.com`. Its download call is
`POST /cdn/files/downloadCredentials`, and its catalog calls are `GET /acl/cdl/permissions/search`
and `GET /acl/cdl/resources/prelaunch`. The web launcher uses a different download path and
resource 25. TUM's own resource id constant is `1`.

`TLCLauncher.exe` is `com.gm.cca.tlc.launcher.Main` from `tlc-launcher-client` 26.4.23.0. `main`
strips the `tlc:,` prefix, splits on commas, and requires one field per `StartupArg` value. A
fourteenth field may be `installTum` or `revertTum`. When `TLC_LOGIN_AS_ADMIN` is `Y`, it sets that
field to `Y-restarted` and starts `TLCLauncherAdmin.exe` with the `tlc:,` string rebuilt. Otherwise
it starts `cmd /C C:/Program Files/TechlineConnect/TUM/TUM.exe` and passes the thirteen field values
as separate arguments. The working directory is `C:/Program Files/TechlineConnect`. Installing TUM
runs `msiexec /i tumApp.msi /qb` from the temp installer directory.

`TUM.exe` is a Launch4j wrapper. It runs `..\jdk\bin\javaw.exe` with `-Djava.library.path=../jdk`
and main class `org.springframework.boot.loader.JarLauncher`. The manifest `Start-Class` is
`com.gm.tlc.tum.TumSpringApplication`, implementation version 26.8.28.0, built for Java 11, Spring
Boot 2.5.12. That class reads its own arguments, installs a bundled trust store, and opens the
JavaFX application `TumJavafxApplication`.

TUM's `StartupArg` also has thirteen values. After the shared login fields it expects
`ACCESS_TOKEN`, `REFRESH_TOKEN`, `GATEWAY_URI`, `VIN`, and `CLIENT_TYPE`
(`TLC_CLIENT`, `SDV_CLIENT`, `DPS_CLIENT`, or unknown). `AppLauncherService` picks a strategy from
`CLIENT_TYPE`. `TLC_CLIENT` asks the authentication service for a TLC token and then starts
`cmd /C` plus `TechlineConnectLaunch.exe` under the Techline Connect program directory, passing
TUM's argument list. `SDV_CLIENT` starts `SdvClient.exe` with the environment, the user id taken
from the session id, the access token, the refresh token, and the VIN. `DPS_CLIENT` has an empty
`launch` method in this build. `TechlineConnectLaunch.exe` is not inside `TLCSuite.exe`. It is a
later download, so it is the next program to open with jadx.

## SPS Info catalog

`spskit sps --vin` is one VIN the subscription can open. It is not a dump of every VIN.

`GET /api/v1/spsCallibration/accessSPSCal` returns the SPOREF Redirection page. The form posts to
`/authorization/oauth/user/sporef/ui` with `appParm` `sps2info`. The response sets a cookie named
`SPS-INFO_ACCESS_TOKEN`. `spskit sps` reads that cookie and sends its value as the bearer on the fixture
and programming-sequence calls, then drops the cookie. The 2026-11-19 export of those calls does not
include an `Authorization` header. Gateway ACL calls do not send this cookie, or the EEID token, as
`Authorization`. The value is not written to the catalog.

`GET /spsinfo/vin/fixture/{vin}` returns `controllerReferenceTree` and `spsvin`. `referenceTree` is a list of
controllers. A controller is `[display name, functions]`. The display name has `controllerCode`, `controllerLabel`
and `displayOrder`. A function is `[function, methods]` with `functionLabel` and `displayOrder`. A method is
`[method, options]`. The method has `methodId`, `description` and `blockSameCal`. The options object has `type`,
`currentSelectionIdx`, `selectedCodes` and `options`.

`spsvin` holds the scalar vehicle fields, including `type`, the VIN split (`wmi`, `vds`, `vis`) and
`modelDesignator`. `vciNumbers`, `copControllers` and `deviceList` are stored as JSON. `supportedControllers` is
the controller list (`controllerId`, `displayName`, and the rest of that document). `asbuiltRpoCodes` is the RPO
list. Any other `spsvin` field is kept in a JSON column. The fixture root also carries `displayName`,
`controllerFunction`, `programmingMethod`, `productionOption` and `rpoCodes`, which the page sends back with the
fixture.

`POST /spsinfo/progseq` takes that fixture. The viewer first sets `displayName`, `controllerFunction` and
`programmingMethod` from the chosen controller; the command uses the first method described as Normal. An
unselected fixture is refused. The response has `calibrationData`, `moduleData`, `cvnMap`,
`hasValidChainOfParts`, `adapterType` and `hasDependency`. `calibrationData` maps a slot to a list of
`[part number, flag, label]`. `moduleData` is a list of `[slot, label]`. `cvnMap` maps a part number to its CVN.
A later sync replaces the rows for that VIN.

This does not download a calibration file and does not program a controller. The tool list is in
[sps2-interfaces.md](sps2-interfaces.md). The programming-data call and the calibration fetch,
including USB copy, are in [calibration-downloads.md](calibration-downloads.md).

## Vehicle programming

ISO 14229-1:2013 clause 15.4.4 (cited through `primarysource`) names SAE J2534 as the communication
between the application and the service-tool hardware, and says communication to the vehicle uses
manufacturer-proprietary information. The SAE document is not imported. No pass-through API is written
from memory.
