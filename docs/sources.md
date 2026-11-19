# Sources

Shapes below are field names from the person's own captures of ACDelco TDS and Techline Connect on
2026-11-19. Values that identify an account, a token, or a code are not copied here.

## Sign-in

The sign-in host is `gmb2bciamprod.ciamlogin.com`. When it wants an email code it returns JSON with
`state` `verificationRequired`, `codeLength`, `continuationToken`, and `_links.verify.href` as a path
on that host. The verify call posts `continuationToken` and `otp`. A continued sign-in returns
`state` `continue`.

The password call that follows verification is a reset. `recover` returns `state` `methodUpdateRequired`
and an `update` link. The update posts `continuationToken` and `newPassword`. This package refuses that
step and does not send `TDS_PASSWORD`.

## Access token

The browser lands on `https://www.acdelcotds.com/#code=...`. The token call is
`POST /{tenant}/oauth2/v2.0/token` with form fields `client_id`, `redirect_uri`, `scope`, `code`,
`code_verifier`, `grant_type=authorization_code` and `client_info=1`. The response has `token_type`,
`access_token` and `refresh_token`. Only the access token is kept.

`POST https://backend.acdelcotds.com/api/v1/login?zoneId=America/Los_Angeles` sends that token in
`X-EEID-Access-Token` and an empty body. The profile in the response is discarded.

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
