# TUM authentication

This is how Techline Update Manager signs its own gateway calls. It is taken from
`local/tlc/extracted/Tum.jar` (`BOOT-INF/classes/com/gm/tlc/tum/` and
`BOOT-INF/classes/application.yml`) and from `DataUtil.hasNoValue` in
`BOOT-INF/lib/satin-core-2.1.0.jar`. `javap` was used because `jadx` is not on `PATH`.
No token, password, or trust-store secret is copied here.

The OAuth client is `com.gm.tlc.tum.feign.AuthorizationServiceClient`. It is the Feign
client `authorization.service.client` with `url="${base.url}/oauth"`. The two methods are
`GET` mappings:

| Method | Mapping | Constant |
| --- | --- | --- |
| `refreshToken` | `/user/token/refresh` | `REFRESH_EXTENSION` |
| `retrieveToken` | `/user/token/child` | `CHILD_EXTENSION` |

Each method takes a `@RequestParam` `Map<String,String>` named `parameters` and a
`@RequestHeader` `Map<String,Object>` named `headerMap`, and returns
`ResponseEntity<TokenModel>`. The composed paths are
`GET ${base.url}/oauth/user/token/refresh` and
`GET ${base.url}/oauth/user/token/child`.

## Where the tokens are read and stored

`TumSpringApplication.main` calls `StartupArg.processArgs` on the command-line array
before JavaFX starts. `StartupArg` is an enum. Each constant holds one string in its
`value` field. `processArgs` assigns the arguments in enum order. The count must equal
the enum length, 13, or the method logs `Args provided = {}, Args Expected = {}` and
returns with every `value` still null. The first argument `Uninstall` is the other
accepted shape: every constant, including both tokens, is set to the string `Uninstall`.
On the normal path the method debug-logs `{}: {}` with the constant name and the
argument. `application.yml` sets `com.gm.tlc.tum` logging to `debug`, so that line
contains the token strings.

The positions that matter for sign-in are:

| Index | Constant |
| --- | --- |
| 1 | `TLC_ENVIRONMENT` |
| 2 | `TLC_LOGIN_SESSION_ID` |
| 7 | `TLC_TDS_REST_TOKEN` |
| 8 | `ACCESS_TOKEN` |
| 9 | `REFRESH_TOKEN` |
| 10 | `GATEWAY_URI` |
| 12 | `CLIENT_TYPE` |

The other constants are `TLC_BROWSE_LAUNCH`, `TLC_LOGIN_SECURITY_ID`,
`TLC_LOGIN_JSESSION_ID`, `TLC_LOGIN_SI_AUTH`, `TLC_LOGIN_AS_ADMIN`, and `VIN`.

After the values are stored, `overrideEnvironmentForGatewayDomain` Base64-URL-decodes
segment 1 of `ACCESS_TOKEN` (split on `.` with limit 3, and only when there is more
than one segment). A decode failure replaces `ACCESS_TOKEN` with the literal
`INVALID_TOKEN`. If the decoded payload contains `ocp-epg3im3.epg.nam.gm.com`,
`TLC_ENVIRONMENT` is rewritten to the OCP profile name. Otherwise it is rewritten to
the Azure profile name. `StartupArg.EnvironmentMapping` matches either name, ignoring
case:

| Input (`defaultEnvironment` or `azureEnvironment`) | OCP profile | Azure profile |
| --- | --- | --- |
| `dev` / `devAzure` | `dev` | `devAzure` |
| `futureState` / `futureStateAzure` | `futureState` | `futureStateAzure` |
| `currentState` / `currentStateAzure` | `currentState` | `currentStateAzure` |
| `validation` / `validationAzure` | `validation` | `validationAzure` |
| `prod` / `productionAzure` | `prod` | `productionAzure` |

An empty or unknown environment logs a warning and becomes `prod` on the OCP path or
`productionAzure` on the Azure path.

`TumJavafxApplication.runSpringApplication` passes that rewritten
`TLC_ENVIRONMENT` value to `SpringApplication.setAdditionalProfiles`. `application.yml`
then selects `base.url`:

| Active profile | `base.url` |
| --- | --- |
| `dev` | `https://tlc-dmz-gateway-dev.ocp-epg-d3-06m1.dev.gm.com` |
| `devAzure` | `https://tlc-dmz-gateway-dev.gm.com` |
| `currentState` | `https://tlc-dmz-gateway-cs.ocp-epg-d3-06m1.dev.gm.com` |
| `currentStateAzure` | `https://tlc-dmz-gateway-cs.gm.com` |
| `futureState` | `https://tlc-dmz-gateway-fs.ocp-epg-d3-06m1.dev.gm.com` |
| `futureStateAzure` | `https://tlc-dmz-gateway-fs.gm.com` |
| `simulation` | `https://tlc-dmz-gateway-sim.ext.gm.com` |
| `validation`, `validationOcp`, `validationAzure` | `https://tlc-dmz-gateway-val.ext.gm.com` |
| `prod`, `productionOcp`, `productionAzure` | `https://tlc-dmz-gateway.ext.gm.com` |
| `local` | `http://localhost:8122` |

`simulation` and `local` are in the yaml. `processArgs` rewrites the startup
environment to one of the ten mapped names before that profile is applied.

`TumJavafxApplication.runAuthenticatedStartup` calls
`AuthenticationService.initializeAuthentication`. That method reads
`StartupArg.ACCESS_TOKEN` and `StartupArg.REFRESH_TOKEN` and copies them into the
in-memory `JwtToken` field `tumToken` with `setAccessToken` and `setRefreshToken`.
`tumToken` is created empty in the `AuthenticationService` constructor. The same method
sets `expirationDate` from the access token. Nothing in this flow writes either token
to a file.

`JwtToken` is the in-memory pair. Its Jackson names are `access_token`,
`refresh_token`, `expires_in`, `token_type`, and `scope`. `AuthenticationService` never
calls `setTokenType`, `setExpiresIn`, or `setScope`. The gateway body is a different
type, `com.gm.tlc.tum.feign.model.TokenModel`: `accessToken` and `refreshToken`, each a
`com.gm.tlc.tum.model.update.TokenWrapper` with `tokenValue` and `expiresAt`. Neither
model class has `@JsonProperty`. `application.yml` sets Jackson
`fail-on-unknown-properties` to false and `default-property-inclusion` to `non_null`,
and it sets no property-naming strategy, so those JavaBean names are the names Feign
binds.

`createExpirationDate` splits the access token on `.`, Base64-URL-decodes segment 1 as
UTF-8, and reads `JwtPayload.exp` (`@JsonIgnoreProperties(ignoreUnknown=true)`) as epoch
seconds. The `LocalDateTime` uses `ZoneId.systemDefault()`. It debug-logs the decoded
payload text. A `JsonProcessingException` during startup is logged as
`Could not proccess expiration date from token {}` and startup continues with
`expirationDate` still null.

## Refresh

`getTumToken(boolean forceRefresh)` returns `tumToken`. It calls `refreshToken` when
`forceRefresh` is true, when `expirationDate` is null, or when
`LocalDateTime.now().plusMinutes(1)` is after `expirationDate`.

`refreshToken` builds one query parameter, `refreshToken`, from
`tumToken.getRefreshToken()`. The header map comes from
`ClientHelper.buildFeignClientHeaderMap(tumToken)`. It then calls
`AuthorizationServiceClient.refreshToken`. On a 2xx body whose `refreshToken` wrapper
and `tokenValue` are all non-null, it logs `TUM Token refreshed.`, recomputes
`expirationDate` from the access token already in `tumToken`, and only then replaces
`tumToken` from `TokenModel.getAccessToken().getTokenValue()` and
`TokenModel.getRefreshToken().getTokenValue()`. A `JsonProcessingException` from that
expiration step is logged as `Could not proccess expiration date from TUM token {}` and
leaves `tumToken` unchanged. A non-2xx response is logged with the string
`Status code from retrieving TLC token: {},  Body: {}` and also leaves `tumToken`
unchanged. A `FeignException` is wrapped in `TumFeignException` (`ErrorCode.NONE`, empty
message) and logged as `Unable to refresh TUM token. {}`. Any other `Exception` is
logged as `Runtime Exception for refresh token.` `refreshToken` does not throw, and it
does not call `StartupArg.updateTokens`.

`CheckUpdatesService`, `InstalledResourcesService`, `CdnTokenService`, and
`ExceptionService` call `getTumToken(false)` and pass the result through
`ClientHelper`. `TestPanelController.refreshToken`, present when the `TEST_PANE`
profile is active, calls `getTumToken(true)`.

## Child token

`retrieveTlcToken` is the only caller of `AuthorizationServiceClient.retrieveToken`.
Its query map has one entry: `tokenType` = `tlc`. The header map is the same
`ClientHelper` map, built from the current TUM `tumToken`, not from the child response.

The only `tokenType` value this jar sends on `GET /oauth/user/token/child` is `tlc`.
`DownloadService` also has a `tokenType` literal, `TUM` (`TUM_TOKEN_TYPE`). That value
is set on `DownloadCredentialData` for the CDN download-credential body. No class passes
`TUM`, `tum2`, or `sps-info` to `retrieveToken`.

A 2xx body with a non-null `accessToken` wrapper and `tokenValue` is returned as the
`TokenModel`. The method does not require a refresh wrapper. A 2xx body that fails that
check logs `TokenModel didn't contain TLC token. Can not continue.` A non-2xx body uses
the same status log string as refresh. A `FeignException` becomes a `TumFeignException`
with `ErrorCode.TLC_TOKEN_RETRIEVAL_FAILED` (`AS103`) and the translated
`TLC_INITIALIZATION_FAILED` string, and is logged as `Unable to retrieve TLC token. {}`
and rethrown. Any other unsuccessful return throws `TumException` with
`ErrorCode.TLC_TOKEN_RETRIEVAL_FAILED2` (`AS104`) and the same translated string.

`ClientProcessLauncher.retrieveTokenWithRetries` calls `retrieveTlcToken` up to three
times. `MAX_AUTH_ATTEMPTS` is 3, and the loop compares against the literal 3. It sleeps
500 ms (`sleepBeforeRetry`) between failures and rethrows the `TumException` on the
third failure.

`TlcClientLaunchStrategy.launch` (`ClientType.TLC_CLIENT`) and
`SdvClientLaunchStrategy.launch` (`ClientType.SDV_CLIENT`) call
`retrieveTokenWithRetries`, then `StartupArg.updateTokens` on that child `TokenModel`.
`updateTokens` writes `accessToken.tokenValue` into `StartupArg.ACCESS_TOKEN` and
`refreshToken.tokenValue` into `StartupArg.REFRESH_TOKEN`, with no null check. It does
not change `AuthenticationService.tumToken`. Later TUM calls still authorize with the
TUM access token. The launched process receives the child values:

- TLC: `launchTlcWithArgs` passes `StartupArg.getArguments()`, the thirteen values in
  enum order. If `TLC_ENVIRONMENT` is one of `devAzure`, `futureStateAzure`,
  `currentStateAzure`, `validationAzure`, or `productionAzure`, `getArguments` first
  rewrites it to the OCP name (`dev`, `futureState`, `currentState`, `validation`,
  `prod`). Positions 8 and 9 are the child access and refresh values.
- SDV: `buildSdvLaunchArgs` passes the current environment, the session id after
  `replaceAll(".*\\.", "")` (the suffix after the last `.`), the child access token,
  the child refresh token, and `VIN`.

`DpsClientLaunchStrategy.launch` returns immediately and does not request a child token.
`TestPanelController.getTlcToken` calls `retrieveTlcToken` and discards the model.

## Authorization header

`ClientHelper.buildFeignClientHeaderMap` puts two entries in the header map:

- `Authorization` is the string concatenation `bearer ` plus `JwtToken.getAccessToken()`.
  The recipe in the class file is `bearer \u0001`: the word is lowercase, and there is
  one space before the token.
- `Content-Type` is `org.springframework.http.MediaType.APPLICATION_JSON`.

`FeignClientConfiguration` does not set this header. It configures the HTTP proxy,
including the branch logged as `Using Authenticated proxy.`
`AuthorizationServiceClient` has no Feign `configuration` attribute, so it uses that
default client.

## Missing token

`DataUtil.hasNoValue(String)` is true for null and for a string that is empty after
`trim`. `initializeAuthentication` checks the access token first. When it has no value
the method logs `{} - Access Token is null.  Shutting Down.` with
`ErrorCode.MISSING_AUTH_TOKEN` (`AS101`) and throws `TumException` carrying that code
and `ClientProperties.TranslateKey.AUTHENTICATION_ERROR`. A missing refresh token does
the same with `ErrorCode.MISSING_REFRESH_TOKEN` (`AS102`) and
`{} - Refresh Token is null.  Shutting Down.`

`runAuthenticatedStartup` catches that `TumException`, logs
`Non-UI Initialization failed by TumException.`, and calls
`ExceptionService.handleUnrecoverableError`. The handler shows the error on the UI
thread and posts it to the logging client. That post calls `getTumToken(false)`. A
failed startup leaves `expirationDate` null, so `getTumToken` still enters
`refreshToken`. `refreshToken` catches its own failures and returns. The startup catch
does not continue into the update check.

A token that fails JWT decoding is not treated as missing. `INVALID_TOKEN` has a value,
so it is copied into `tumToken` and the expiration parse is logged and ignored.

## Other classes in the auth packages

`com.gm.tlc.tum.services.auth` contains only `AuthenticationService`
(`@Service`). It autowires `ClientHelper` and `AuthorizationServiceClient`.

`com.gm.tlc.tum.security` contains `BundledTrustStoreBootstrap` and its
`InstallStatus`. `TumSpringApplication.installTrustStore` calls `tryInstall` before
JavaFX. The class loads the classpath resource `/security/cacerts` as a `JKS` with a
null keystore password and installs it as the default TLS `SSLContext`.
`TumJavafxApplication.init` returns without starting Spring when that install did not
succeed, and the failure dialog uses `ErrorCode.TRUST_STORE_UNAVAILABLE` (`TJA102`).
This is the TLS trust store for the gateway connection, not the OAuth token client.

`com.gm.tlc.tum.constants.Profiles` defines `LOCAL_AUTH` with the value `LOCAL_AUTH`.
No other class under `com.gm.tlc.tum` references that field, and `application.yml` has
no `LOCAL_AUTH` profile. The profile this flow does use for a test-only token button
is `TEST_PANE`.

No class under `com.gm.tlc.tum` names security access, a seed or key calculation,
calibration transfer, or SAE J2534.
