# TUM gateway clients

Source is `local/tlc/extracted/Tum.jar` (`tum.version` `26.8.28.0`). The Feign interfaces live in
`BOOT-INF/classes/com/gm/tlc/tum/feign/`. Paths, verbs, and parameter annotations are the
`@FeignClient` and `@GetMapping` / `@PostMapping` values on those interfaces. Header names, query
keys, and body fields below are the constants and setters in the methods that call them.
`TumSpringApplication` is `@EnableFeignClients` with no client list, so these four interfaces are
the set. Nothing in `com.gm.tlc.tum` uses `RestTemplate`, `WebClient`, or Feign `@RequestLine`.
`DownloadFileService` is the one `HttpURLConnection` caller and is listed after the Feign clients.

No Feign client in this jar is limited to security access, seed or key calculation, calibration
transfer, or SAE J2534, so none was left out under the spskit vehicle-programming rule.

`application.yml` sets Jackson `default-property-inclusion: non_null` and
`deserialization.fail-on-unknown-properties: false`. Wire names below are the JavaBean names of
the getters. A boolean getter such as `isPreLaunchInstall` binds as `preLaunchInstall`.

## Base URL

Every client url is `${base.url}` plus a prefix. `application.yml` selects `base.url` by profile.
spskit's default `TDS_GATEWAY` is the production host.

| Profile | `base.url` |
| --- | --- |
| `prod`, `productionOcp`, `productionAzure` | `https://tlc-dmz-gateway.ext.gm.com` |
| `validation`, `validationOcp`, `validationAzure` | `https://tlc-dmz-gateway-val.ext.gm.com` |
| `simulation` | `https://tlc-dmz-gateway-sim.ext.gm.com` |
| `dev` | `https://tlc-dmz-gateway-dev.ocp-epg-d3-06m1.dev.gm.com` |
| `devAzure` | `https://tlc-dmz-gateway-dev.gm.com` |
| `currentState` | `https://tlc-dmz-gateway-cs.ocp-epg-d3-06m1.dev.gm.com` |
| `currentStateAzure` | `https://tlc-dmz-gateway-cs.gm.com` |
| `futureState` | `https://tlc-dmz-gateway-fs.ocp-epg-d3-06m1.dev.gm.com` |
| `futureStateAzure` | `https://tlc-dmz-gateway-fs.gm.com` |
| `local` | `http://localhost:8122` |

`FeignClientConfiguration.buildFeignRetryer` builds `feign.Retryer.Default` with period `1000`,
max period `10000`, and `3` attempts (`MAX_ATTEMPTS`). The proxied client bean is active when
`feign.proxy.enabled` is true, and that property is missing in every profile except `local`,
where it is `"false"`.

## Headers on every Feign call

`ClientHelper.buildFeignClientHeaderMap` puts two entries in the map passed as `@RequestHeader`:

| Header | Value |
| --- | --- |
| `Authorization` | the characters `bearer `, then `JwtToken.getAccessToken()` (`StringConcatFactory` recipe `bearer \u0001`) |
| `Content-Type` | `MediaType.APPLICATION_JSON`, whose type string in spring-web 5.3.18 is `application/json` |

The access token is the startup access token, replaced after a successful refresh by
`TokenModel.accessToken.tokenValue`. spskit sends `Bearer ` with a capital B, and only when a
SPOREF cookie bearer is loaded (`client.acl_headers`).

## Calls spskit already makes

| TUM call | spskit |
| --- | --- |
| `GET /oauth/user/token/refresh` | no caller |
| `GET /oauth/user/token/child?tokenType=tlc` | no caller |
| `GET /acl/cdl/permissions/search` | `client.required_versions` |
| `GET /acl/cdl/resources/prelaunch` | `client.prelaunch_ids` |
| `POST /cdn/files/downloadCredentials` | no caller. spskit posts `/cdn/files/public/downloadCredentials` (`download.CREDENTIALS_PATH`) |
| `POST /logging/tum/errors` | no caller |
| grant URL `GET` with `Cookie` and `Range` | spskit `GET`s the grant URL with the grant's `headers` and does not send `Range` |

spskit also calls three routes that have no TUM Feign method: `POST /acl/permissions/search`
with body `{}` (`client.search_access`), `GET /acl/cdl/resources/{id}/permissions`
(`client.list_modules`), and the SPOREF handoff `POST /authorization/oauth/user/sporef/ui`
(`client.submit_sporef_form`). TUM's oauth prefix is `${base.url}/oauth`, so the SPOREF path is
outside this client.

## AuthorizationServiceClient

Feign name `authorization.service.client`. Base `${base.url}/oauth`.
`AuthenticationService` is the caller. Both methods take `@RequestParam Map<String,String>` and
`@RequestHeader Map<String,Object>`, and return `ResponseEntity<TokenModel>`. The annotations
name no single parameter, so each map entry is one query parameter or one header.

| Method | Verb and path | Query |
| --- | --- | --- |
| `refreshToken` | `GET /user/token/refresh` | `refreshToken` = `JwtToken.getRefreshToken()` |
| `retrieveToken` | `GET /user/token/child` | `tokenType` = `tlc` |

The interface constants `REFRESH_EXTENSION` and `CHILD_EXTENSION` hold those same two paths.
`retrieveTlcToken` is the only builder of the child query. `ClientProcessLauncher.retrieveTokenWithRetries`
always calls it; the string argument is only the log label. `TlcClientLaunchStrategy` and
`SdvClientLaunchStrategy` both go through that method, so both ask for `tokenType=tlc`.

No body. A null access token or a null refresh token at startup throws before either call.
The refresh failure log is `Unable to refresh TUM token`. The child failure log is
`Unable to retrieve TLC token`.

`TokenModel` fields are `accessToken` and `refreshToken`, each a `TokenWrapper` with `tokenValue`
(`String`) and `expiresAt` (`LocalDateTime`). Refresh reads `tokenValue` on both wrappers and
stores those strings as the next access and refresh tokens. The child call requires
`accessToken.tokenValue`. The class extends satin `BaseModel`.

## AclServiceClient

Feign name `acl.service.client`. Base `${base.url}/acl`. Both methods take only the header map.
No query and no body.

| Method | Verb and path | Returns | Caller |
| --- | --- | --- | --- |
| `retrieveRequiredResources` | `GET /cdl/permissions/search` | `CdlPermissionModel` | `CheckUpdatesService.loadRequiredVersions` |
| `retrieveAllPossibleResources` | `GET /cdl/resources/prelaunch` | `ResponseEntity<CdlResourceModel>` | `InstalledResourcesService.retrieveAllPossibleResources` |

`CdlPermissionModel.resourceVersions` is `List<CdlResourceVersionData>`. `ResourceType` is
`SOFTWARE`, `ZIP`, `GDS2_ZIP`, and `INITIAL_SOFTWARE`, and the enum has no `toString` override, so
those names are the text. The caller keeps a row whose `cdlResourceTypeCode` is any of those
except `INITIAL_SOFTWARE`. It then copies these getters into its local resource: `cdlResourceId`, `cdlResourceDescription`,
`cdlResourceName`, `cdlResourceVersionId`, `versionNumber`, `versionDescription`,
`sourceSubDirectory`, `registryKey`, `executeCommand`, `targetPath`, `cdlResourceTypeCode`,
`installationPriority`, `disabled`, `preLaunchInstall`, `productCode`, `uninstallCommand`.
`cdlResourceTypeCode` has to be one of those enum names because the copy calls
`ResourceType.valueOf`. A true `isPreLaunchInstall` goes on the pre-launch list; a false value
goes on the post-launch list. spskit's `catalog.parse_permissions` reads `resourceVersions` and
the same id, name, description, type code, and version.

`CdlResourceModel` declares `cdlResources`, `resultList`, and `errorList`. The prelaunch caller
reads `resultList` (`List<CdlResourceData>`) and `errorList`. It does not read `cdlResources`.
The filter keeps a row when `CdlResourceData.isDisabled()` is false. Each kept row is copied
from `id`, `description`, `name` (satin `BaseData` getters), `registryKey`, `executeCommand`,
`targetPath`, `typeCode`, `installationPriority`, `preLaunchInstall`, `productCode`,
`uninstallCommand`, and `disabled`. `typeCode` is passed to `ResourceType.valueOf`, so it has to
be one of those enum names. The copy sets `versionNumber` to the literal `0.0.0`.
`BaseData` also declares `disabled` (`Boolean`), `createDate`, `createUser`, `updateDate`,
`updateUser`, and `tcn`. spskit's `catalog.parse_prelaunch` uses `cdlResources` when that value
is a list, and otherwise `resultList`, and keeps a decimal `id` or `cdlResourceId`.

`CdlResourceIds.TUM_ID` is the string `1`. Neither ACL method puts that id on the request.

## CdnServiceClient

Feign name `cdn.service.client`. Base `${base.url}/cdn`.

| Method | Verb and path | Header | Body |
| --- | --- | --- | --- |
| `retrieveDownloadCredentials` | `POST /files/downloadCredentials` | the shared map | `@RequestBody DownloadCredentialModel` |

`CdnTokenService.retrieveDownloadCredentials` passes `AuthenticationService.getTumToken` through
`buildFeignClientHeaderMap` and returns the response list. `DownloadService` builds the model.

`DownloadCredentialModel.downloadCredentials` is `List<DownloadCredentialData>`. The builder in
`DownloadService` sets four fields on each item and then `build()`:

| Field | Value |
| --- | --- |
| `humanReadableName` | `CdlResource.getHumanReadableName()` |
| `versionNumber` | `CdlResource.getVersionNumber()` |
| `tokenType` | `TUM` |
| `cdlResourceType` | `ResourceType.toString()`, one of `SOFTWARE`, `ZIP`, `GDS2_ZIP`, `INITIAL_SOFTWARE` |

The class also has `url`, `md5`, `tokenData` (`CdnTokenData`, fields `value` and
`expirationTime`), and `headers` (`Map<String,String>`). That builder leaves them null, and
`non_null` omits nulls. There is no `filename` member. There is no resource-id member.
`CdlResourceIds.TUM_ID` (`1`) is not written into this body.

The response is the same model. `DownloadFileService` then reads `url`, `headers` key `Cookie`,
and `md5`.

spskit's public body (`download.credentials_body`) is one `downloadCredentials` object with
`humanReadableName`, `versionNumber`, `cdlResourceType`, `tokenType` `TUM`, plus empty `url`,
`tokenData` `{value, expirationTime: -1}`, `headers`, `md5`, and `filename`. The path is
`/cdn/files/public/downloadCredentials`.

## LoggingServiceClient

Feign name `logging.service.client`. Base `${base.url}/logging`.

| Method | Verb and path | Header | Body |
| --- | --- | --- | --- |
| `logTumError` | `POST /tum/errors` | the shared map | `@RequestBody TumErrorModel` |

`ExceptionService.handleUnrecoverableError` is the caller. `TumErrorModel`'s
`(String, List, String)` constructor assigns:

| Field | Value |
| --- | --- |
| `errorMessage` | the message string passed into `createTumErrorModel` |
| `resourceVersions` | one `TumLogCdlResourceVersionData` per installed resource |
| `logFile` | the text read from the TUM log file |

Each `resourceVersions` item is `cdlResourceVersionId` = the resource's version id,
`cdlResourceName` = its human-readable name, and `versionNumber` = its version number. The type
extends satin `BaseData`, so `id`, `name`, and `description` are also on the bean. spskit has no
logging call.

## Grant URL fetch

`DownloadFileService` is not a Feign client. After the credentials response it opens `url` with
`HttpURLConnection`. The first request sets `Cookie` to `headers.get("Cookie")`. Chunk requests
set `Range` to the recipe `bytes=\u0001-\u0001` (start and end) and the same `Cookie`.
`CHUNK_SIZE_IN_BYTES` is `5000000`. It checks the body against `md5`.

## Models that are not clients

`CdnTokenModel` (`tokenData`, `environmentDirectory`) and `UserAttributeModel` (`userAttribute`)
sit in the feign model package and have no method on these four interfaces.
