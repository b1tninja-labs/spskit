# TUM packages

`TLCSuite.exe` installs `Tum.exe`, the two launchers `TLCLauncher.exe` and `TLCLauncherAdmin.exe`, and a bundled JRE. There is no separate plugin directory. GDS2 and MDI are separate CDN downloads, and they are not files in `Tum.jar`. Classes below that mention GDS2 or MDI only name a catalog resource type, a folder, a shortcut, or a registry value for those downloads.

`D:\code\spskit\local\tlc\extracted\Tum.jar` is the Spring Boot archive from `Tum.exe`. These notes cover the 115 class files under `BOOT-INF/classes/com/gm/tlc/tum/`, grouped by package, including inner classes, anonymous classes, and `package-info`. Each sentence comes from the class name, its constant-pool strings, and its method names. No class in this tree exists only for security access, seed/key calculation, calibration transfer, or SAE J2534.

The same installer layout is in [tlc-suite.md](tlc-suite.md). The Launch4j stubs and the jar overlay are in [tlc-binaries.md](tlc-binaries.md).

| Package | Classes |
| --- | ---: |
| `com.gm.tlc.tum` | 2 |
| `com.gm.tlc.tum.constants` | 2 |
| `com.gm.tlc.tum.controller` | 13 |
| `com.gm.tlc.tum.exception` | 2 |
| `com.gm.tlc.tum.feign` | 5 |
| `com.gm.tlc.tum.feign.configuration` | 1 |
| `com.gm.tlc.tum.feign.exception` | 1 |
| `com.gm.tlc.tum.feign.model` | 6 |
| `com.gm.tlc.tum.feign.model.data` | 7 |
| `com.gm.tlc.tum.model` | 10 |
| `com.gm.tlc.tum.model.data` | 2 |
| `com.gm.tlc.tum.model.update` | 3 |
| `com.gm.tlc.tum.properties` | 3 |
| `com.gm.tlc.tum.security` | 3 |
| `com.gm.tlc.tum.services` | 21 |
| `com.gm.tlc.tum.services.auth` | 1 |
| `com.gm.tlc.tum.services.legacy` | 3 |
| `com.gm.tlc.tum.services.model` | 1 |
| `com.gm.tlc.tum.services.proxy` | 3 |
| `com.gm.tlc.tum.services.strategy.launch` | 5 |
| `com.gm.tlc.tum.services.util` | 5 |
| `com.gm.tlc.tum.startup` | 3 |
| `com.gm.tlc.tum.thread` | 2 |
| `com.gm.tlc.tum.util` | 11 |

## `com.gm.tlc.tum`

- `TumJavafxApplication` — JavaFX entry that starts the Spring context, sets the stage title to Techline Update Manager, loads the locale from the Techline Connect preferences registry key, and branches into uninstall, the test pane, or the normal startup, including a dialog when the bundled TLS trust store fails.
- `TumSpringApplication` — `main` parses startup arguments, deletes `tum.log`, installs the bundled trust store, and launches `TumJavafxApplication`.

## `com.gm.tlc.tum.constants`

- `Profiles` — names the Spring profiles `default`, `TEST_PANE`, `LOCAL_ACL`, `LOCAL_CDN`, and `LOCAL_AUTH`, and checks which of them are active.
- `PropertyConstants` — holds the property-file names `environment.properties`, `client.properties`, and `locale.properties`, plus the keys `base_url` and `app_parm`.

## `com.gm.tlc.tum.controller`

- `CheckUpdatesController` — JavaFX controller for `checkUpdates.fxml` whose checkbox is marked validation-passed or validation-failed when the update check finishes.
- `ControllerBase` — abstract controller with an empty `close` method.
- `DownloadUpdateController$1` — compiler switch map for `DownloadUpdateController$UpdateStatus`.
- `DownloadUpdateController$UpdateStatus` — enum of row states `DOWNLOADING`, `WAITING_TO_INSTALL`, `INSTALLING`, `COMPLETED`, and `RETRYING`.
- `DownloadUpdateController` — fills `DownloadUpdatePane.fxml` with one `ResourceProgress` row per CDL resource and moves each row through those statuses.
- `ExceptionPaneController` — sets the text and icon on `ExceptionPane.fxml` and closes that pane.
- `InstallingTumController` — controller for `InstallingTumPane.fxml` with initialize and close.
- `LaunchingTlcController` — controller for `LaunchingTlcPane.fxml` with initialize and close.
- `MainController` — owns `Main.fxml` and swaps the center pane among settings, the download list, the TLC launch pane, the restart pane, and the TUM install pane.
- `ResourceProgressController` — one download row: file name, progress bar, and a status label that switches among downloading, waiting, installing, retrying, and completed.
- `RestartPcController` — controller for `RestartingPcPane.fxml`; its initialize log string still says LaunchingTlcController.
- `SettingsController` — edits proxy host, port, username, password, and an authentication checkbox on `Settings.fxml`, then saves or deletes those settings.
- `TestPanelController` — `TEST_PANE` screen that fires launch, check-for-updates, download, token, and uninstall actions against dummy resources, including a sample CSI registry value.

## `com.gm.tlc.tum.exception`

- `ErrorCode` — enum of TUM failure codes, each paired with a short id such as `ALS101` for a failed TLC launch, `CTS101` for empty CDN credentials, and `TS101` for a CDN token failure.
- `TumException` — checked exception that carries an `ErrorCode`, a process error code, and a message.

## `com.gm.tlc.tum.feign`

- `AclServiceClient` — Feign client whose methods call `/cdl/permissions/search` and `/cdl/resources/prelaunch`.
- `AuthorizationServiceClient` — Feign client whose methods call `/user/token/refresh` and `/user/token/child`.
- `CdnServiceClient` — Feign client whose one method posts to `/files/downloadCredentials`.
- `ClientHelper` — builds the Feign header map with `Authorization` and `Content-Type`.
- `LoggingServiceClient` — Feign client whose one method posts a `TumErrorModel` to `/tum/errors`.

## `com.gm.tlc.tum.feign.configuration`

- `FeignClientConfiguration` — builds the Feign HTTP client against an authenticated proxy, a basic proxy, or no proxy, and supplies a retryer.

## `com.gm.tlc.tum.feign.exception`

- `TumFeignException` — turns a Feign error status and body into a `TumException`, or records that the body was missing or not JSON.

## `com.gm.tlc.tum.feign.model`

- `CdlPermissionModel` — response model whose field is the list of resource versions from the permissions search.
- `CdlResourceModel` — response model with `cdlResources`, `resultList`, and `errorList`.
- `CdnTokenModel` — response model with CDN token data and an environment directory.
- `TokenModel` — response model with an access-token wrapper and a refresh-token wrapper.
- `TumErrorModel` — body posted to the logging client: an error message, resource versions, and a log file.
- `UserAttributeModel` — response model whose only field is a `UserAttributeData`.

## `com.gm.tlc.tum.feign.model.data`

- `CdlResourceData$CdlResourceDataBuilder` — builder for `CdlResourceData`.
- `CdlResourceData` — server description of one CDL resource: priority, type code, registry key, execute and uninstall commands, target path, product code, and disabled.
- `CdlResourceVersionData$CdlResourceVersionDataBuilder` — builder for `CdlResourceVersionData`.
- `CdlResourceVersionData` — a `CdlResourceData` plus version id, version number, version description, and source subdirectory.
- `CdnTokenData` — a token string and an expiration time.
- `TumLogCdlResourceVersionData` — the resource version id, name, and version number attached to an error report.
- `UserAttributeData` — a single `value` field.

## `com.gm.tlc.tum.model`

- `CdlResource$CdlResourceBuilder` — builder for `CdlResource`.
- `CdlResource` — local record of one catalog resource, built from `CdlResourceData`, `CdlResourceVersionData`, or `TdmMetadataFile`, with version, path, type, registry key, commands, and install priority.
- `DownloadChunk` — one byte range of a download and the file where that range is stored.
- `DownloadCredentialModel` — list of `DownloadCredentialData` sent to and returned from the CDN credentials call.
- `JwtPayload` — JWT payload model whose only field is `exp`.
- `JwtToken` — access token, refresh token, `expiresIn`, token type, and scope.
- `ProxySettings` — proxy host, port, username, and password, with the password masked in `toString`.
- `ResourceType` — enum `SOFTWARE`, `ZIP`, `GDS2_ZIP`, and `INITIAL_SOFTWARE`; `GDS2_ZIP` names a CDN resource type, and the GDS2 bytes are not in this jar.
- `TdmMetadataFile` — legacy metadata pair of a human-readable name and a version id.
- `UserPreferences` — a `Locale` and an SI region code.

## `com.gm.tlc.tum.model.data`

- `DownloadCredentialData$DownloadCredentialDataBuilder` — builder for `DownloadCredentialData`.
- `DownloadCredentialData` — one CDN download descriptor: name, version, token type, resource type, URL, md5, token data, and headers.

## `com.gm.tlc.tum.model.update`

- `FileInfo` — class file with a constructor and no fields or other methods.
- `FxFileInfo` — class file whose only member besides the constructor is a Log4j logger.
- `TokenWrapper` — a token string and the `LocalDateTime` it expires.

## `com.gm.tlc.tum.properties`

- `ClientProperties$ClientKey` — property keys `test.tool` and `tum.version`.
- `ClientProperties$TranslateKey` — resource-bundle keys for update status, proxy settings, launch and install errors, the single-instance warning, and the admin warning.
- `ClientProperties` — loads `client.properties` and the `tum` resource bundle, defaulting the locale to `en_US`.

## `com.gm.tlc.tum.security`

This package is the TLS trust store for HTTPS. It is not vehicle security access.

- `BundledTrustStoreBootstrap$InstallStatus` — enum `NOT_ATTEMPTED`, `SUCCEEDED`, and `FAILED`.
- `BundledTrustStoreBootstrap` — reads the bundled trust store resource `/security/cacerts` and installs it as the default `SSLContext`.
- `package-info` — empty package marker for `com.gm.tlc.tum.security`.

## `com.gm.tlc.tum.services`

- `AdminService` — runs `net session` to see whether the user is an administrator and shows a warning dialog when the install is not elevated.
- `AppLauncherService` — picks a client launch strategy, or unzips the current or new TUM installer and starts `TLCLauncher` with `installTum` or `revertTum`.
- `ArchiveService` — stores a downloaded resource as a zip plus a json sidecar under the archive folder and deletes the least recently used copies, with a separate cap whose name is GPLD.
- `CdnTokenService` — calls `CdnServiceClient` for download credentials and fails when the model or the list is empty.
- `CheckUpdatesService` — compares installed CDL versions with the ACL list, updates the `TUM2` package first, then runs pre-launch installs, post-launch installs, re-downloads, and removal of resources the ACL no longer allows.
- `ClientProcessLauncher` — starts TLC or SDV with `cmd /C`, retries token retrieval, and drains the child process output until the process exits or the launch grace period ends.
- `CommandService` — deletes the public-desktop shortcut `GDS 2.lnk` through an elevated command; that shortcut is not a plugin in this jar.
- `DownloadFileService` — downloads a CDN file in byte ranges, joins the chunks, and checks the md5.
- `DownloadService` — asks `CdnTokenService` for credentials, then `DownloadFileService`, including a download whose token type is `TUM`.
- `ExceptionService` — shows `ExceptionPane`, builds the error text, and posts a `TumErrorModel` with `tum.log` to the logging client.
- `GDS2ZipResourceTypeService` — installs and uninstalls a `GDS2_ZIP` catalog resource by placing its deliverable and `BinaryFile` contents in the GDS 2 download folders; the zip is a separate CDN download and is not in this jar.
- `InstallService` — queues ready resources by install priority and dispatches each one through `ResourceTypeServiceFactory`.
- `InstalledResourcesService` — reads and writes `CurrentVersions.json` and asks the ACL client for the list of every possible resource.
- `ResourceTypeService` — interface with `install` and `uninstall` for one `CdlResource`.
- `ResourceTypeServiceFactory$1` — compiler switch map for `ResourceType`.
- `ResourceTypeServiceFactory` — returns the software, zip, or GDS2-zip service for a resource, and logs when the type is missing.
- `RestartService` — shows the restart pane and runs `shutdown /r /t 5`.
- `SingleAppInstanceService` — uses PowerShell `Win32_Process` to notice a TLC `javaw.exe`, to stop other `TechlineConnect\TUM\` processes, and to stop `proxy_server.exe`.
- `SoftwareResourceTypeService` — installs or uninstalls a `SOFTWARE` resource by running its command and comparing the version read from the registry.
- `TestingService` — test-only helper whose one method bypasses validation and toggles the check-for-updates mark.
- `ZipResourceTypeService` — unzips a `ZIP` resource onto its target path, substitutes the `<user-id>` placeholder, and reads `version.txt`.

## `com.gm.tlc.tum.services.auth`

- `AuthenticationService` — holds the TUM session token, refreshes it through `AuthorizationServiceClient`, and requests a TLC child token.

## `com.gm.tlc.tum.services.legacy`

- `FileMetadataService` — reads legacy TDM metadata files and maps GDS 2 data names (BrightDrop, Cruise, China, Medium Duty, FCCC, VinFast, Saab, SAIC, NAVISTAR, Global, OpelVauxhall) to deliverable folder names; those data packages are not in this jar.
- `LegacyVersionsFileService` — merges registry and metadata lists into `CurrentVersions.json`, keeps the newer resource, and builds the GDS2 zip list from files on disk.
- `RegistryService` — reads one registry value with `reg query`; a failure string names the MDI version, and MDI is not in this jar.

## `com.gm.tlc.tum.services.model`

- `ProcessInfo` — process id, name, and command line parsed from the PowerShell `ConvertTo-Json` output.

## `com.gm.tlc.tum.services.proxy`

- `EncryptionService` — encrypts and decrypts the proxy-settings file that `ProxySettingsService` stores.
- `ProxySettingsService$1` — anonymous `Authenticator` that returns the proxy username and password already held by `ProxySettingsService`.
- `ProxySettingsService` — loads, saves, and deletes the proxy-settings file and exposes a basic proxy, an authenticated proxy, or no proxy.

## `com.gm.tlc.tum.services.strategy.launch`

- `ClientLaunchStrategy` — interface with `getClientType` and `launch`.
- `DpsClientLaunchStrategy` — strategy whose client type is `DPS_CLIENT`; `launch` calls no other method.
- `SdvClientLaunchStrategy` — strategy whose client type is `SDV_CLIENT` and whose `launch` goes through `ClientProcessLauncher`.
- `TlcClientLaunchStrategy` — strategy whose client type is `TLC_CLIENT` and whose `launch` goes through `ClientProcessLauncher` and `MainController`.
- `UnknownClientLaunchStrategy` — logs an unknown client type and calls `TlcClientLaunchStrategy`.

## `com.gm.tlc.tum.services.util`

- `CatchableTumProcess` — interface whose `run` returns an object, used by `TumRetryUtil`.
- `CatchableTumVoidProcess` — interface whose `run` returns void, used by `TumRetryUtil`.
- `ProcessStarter` — interface whose `start` returns a `Process`.
- `ProcessUtil` — starts a command list, reads the process error text, and shares a shutdown exit value with `RestartService`.
- `TumRetryUtil` — reruns a `CatchableTumProcess` or `CatchableTumVoidProcess` a given number of times and logs each failure.

## `com.gm.tlc.tum.startup`

- `StartupArg$ClientType` — enum `SDV_CLIENT`, `TLC_CLIENT`, `DPS_CLIENT`, and `UNKNOWN`, with `fromString` defaulting null or unknown text to `UNKNOWN`.
- `StartupArg$EnvironmentMapping` — maps `dev`, `futureState`, `currentState`, `validation`, and `prod` onto a default name and an Azure name.
- `StartupArg` — parses the comma-separated startup arguments (browse launch, environment, login ids, tokens, gateway URI, VIN, and client type) and selects the environment profile.

## `com.gm.tlc.tum.thread`

- `ThreadManager` — shared pool named `TUMthreadPool-%d`, plus a single-thread scheduled executor.
- `UIThreadManager` — one thread named `UI Manager Thread` that drains a fixed queue of UI runnables.

## `com.gm.tlc.tum.util`

- `ApplicationShutdownUtil` — calls `System.exit`.
- `ApplicationState` — holds a map named `users`.
- `CdlResourceIds` — constant `TUM_ID` whose value is `1`.
- `Constants` — the two folder names `currentTum` and `installTum`.
- `FilePaths$PidFile` — pid-file paths ending in `tum.pid` and `tlc.pid`.
- `FilePaths` — path constants for the Techline Connect user folder, preferences, proxy file, `CurrentVersions.json`, archived downloads, TUM installer temp, the TLC and SDV launch executables, and the GDS 2 download folders; the TLC launch executable, SDV executable, GDS2 tree, and MDI are not in this jar.
- `FileUtil$1` — anonymous Jackson `TypeReference` used when `FileUtil` reads a list from a file.
- `FileUtil` — saves and loads JSON, unzips, copies, purges files and directories, and lists a directory.
- `FxmlConstants` — font-size strings `6.0`, `10.0`, `18.0`, and `30.0`.
- `LaunchThreadStarter` — starts a `Thread` for a `Runnable`.
- `UserState` — boolean `isUsingNewTum`.
