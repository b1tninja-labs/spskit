# Obligations and their evidence

Every obligation `spskit` has taken on, with an honest status against the code.

**The honesty rule:** a row reads `[ok]` only when the test named in its Evidence cell exists and would fail if the
behaviour regressed. `tests/test_roadmap_rows.py` resolves every `[ok]` row's test and every callable the matrix
names.

Legend: `[ok]` implemented and pinned by a named test — `[part]` partial, what is missing stated — `[ ]` not built —
`[no]` deliberate non-goal, with the reason.

Sources for the download and verification shapes are the captured TDS and Techline Connect calls recorded in
`docs/sources.md`. SAE J2534 is not in `primarysource`. ISO 14229-1:2013 clause 15.4.4 names it as the link between
the application and the service-tool hardware and says the vehicle side uses manufacturer-proprietary information,
so this package does not speak to a vehicle.

## 1. Matrix

### Settings and the verification code

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.env.parse` | `config.parse_env_text()` reads KEY=VALUE lines, comments and quotes | local env file | `[ok]` | `tests/test_config.py::test_comments_and_quotes_parse` |
| `sk.env.override` | `config.load_settings()` lets the process environment replace a file value | local env file | `[ok]` | `tests/test_config.py::test_process_environment_overrides_the_file` |
| `sk.env.absolute` | `config.settings_from()` refuses a relative download directory | local env file | `[ok]` | `tests/test_config.py::test_a_relative_download_directory_is_refused` |
| `sk.env.example` | `config.parse_env_text()` reads `.env.example` with empty username, password and token | local env file | `[ok]` | `tests/test_config.py::test_the_example_names_the_secrets_and_leaves_them_empty` |
| `sk.verify.parse` | `verify.parse_challenge()` keeps the verify path and code length the host returned | captured sign-in challenge | `[ok]` | `tests/test_verify.py::test_a_challenge_keeps_the_path_the_host_named` |
| `sk.verify.length` | `verify.prompt_code()` refuses a code that is not the length the challenge stated | captured sign-in challenge | `[ok]` | `tests/test_verify.py::test_a_code_of_the_wrong_length_is_refused` |
| `sk.verify.link` | `verify.parse_challenge()` refuses a verify link that is not a path on the sign-in host | captured sign-in challenge | `[ok]` | `tests/test_verify.py::test_an_off_host_verify_link_is_refused` |
| `sk.verify.submit` | `client.submit_code()` posts the code once and does not store it on settings | captured verify request | `[ok]` | `tests/test_verify.py::test_the_code_is_posted_once_and_not_kept_on_settings` |
| `sk.cli.verify` | `cli.run()` prompts and reports continue | captured verify response | `[ok]` | `tests/test_cli.py::test_verify_prompts_and_reports_continue` |
| `sk.cli.expired` | `cli.run()` reports a refused gateway session and does not invent a code to send | gateway 401 | `[ok]` | `tests/test_cli.py::test_an_expired_session_is_reported_without_prompting` |
| `sk.login.email` | `login_start.request_email_code()` posts the password and BeginAuth, then `cli.run()` saves the challenge and `spskit code` waits for the email code | captured sign-in | `[ok]` | `tests/test_login_start.py::test_login_posts_the_password_then_waits_for_the_email_code` |
| `sk.login.resume` | `cli.run()` finishes a saved stay-signed-in post and does not call BeginAuth | captured sign-in | `[ok]` | `tests/test_login_start.py::test_a_saved_stay_signed_in_finishes_without_a_new_email` |
| `sk.login.retry` | `cli.urllib_exchange()` retries a connection the host closed | local transport | `[ok]` | `tests/test_cli.py::test_a_closed_connection_is_retried` |
| `sk.client.agent` | `cli.urllib_exchange()` sends the captured Chrome User-Agent | captured browser request | `[ok]` | `tests/test_cli.py::test_the_exchange_sends_a_browser_user_agent` |

### Licensed modules

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.catalog.parse` | `catalog.parse_permissions()` lists name, type and version and drops the account id | captured permissions response | `[ok]` | `tests/test_catalog.py::test_permissions_drop_the_account_id` |
| `sk.catalog.bearer` | `client.list_modules()` sends the SPOREF cookie bearer when supplied and does not send the saved access token | captured permissions request | `[ok]` | `tests/test_catalog.py::test_listing_does_not_send_the_saved_access_token` |
| `sk.download.body` | `download.credentials_body()` asks for one module with empty token fields | captured downloadCredentials request | `[ok]` | `tests/test_download.py::test_the_request_starts_with_empty_token_fields` |
| `sk.download.grant` | `download.parse_grant()` accepts one https URL and a single plain filename | captured downloadCredentials response | `[ok]` | `tests/test_download.py::test_a_grant_must_be_https_and_a_plain_filename` |
| `sk.download.save` | `client.fetch_module()` writes the bytes under `cache/{id}/{version}/` in the download directory and nowhere else, and sends User-Agent `Java/11.0.19` | captured file fetch and the bundled Corretto | `[ok]` | `tests/test_download.py::test_download_writes_beside_the_given_directory` |

### Licensed files

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.downloads.access` | `catalog.parse_resource_access()` keeps the resource id and runnable flag and drops the account id | Techline Connect permissions search | `[ok]` | `tests/test_downloads.py::test_resource_access_drops_the_account_id` |
| `sk.downloads.list` | `client.licensed_downloads()` asks for the installer, TUM, every runnable decimal id, every prelaunch decimal id, and the update-manager version search | launcher search, `GET /acl/cdl/resources/prelaunch`, and `GET /acl/cdl/permissions/search` | `[ok]` | `tests/test_downloads.py::test_the_installer_and_a_decimal_resource_are_listed` |
| `sk.downloads.fetch` | `cli.run()` lists those files, and `--get` writes each version under the cache and leaves a file that is already there | same catalog | `[ok]` | `tests/test_downloads.py::test_downloads_lists_and_get_writes_the_file` |
| `sk.downloads.skip` | `catalog.parse_permissions()` omits a disabled version and `catalog.parse_prelaunch()` keeps decimal ids | TUM prelaunch and version records | `[ok]` | `tests/test_downloads.py::test_a_disabled_version_is_left_out` |
| `sk.gateway.session` | `client.open_gateway_session()` posts the SPOREF handoff and `client.list_modules()` sends no Authorization | captured gateway calls | `[ok]` | `tests/test_downloads.py::test_the_handoff_leaves_the_eeid_token_off_the_gateway` |
| `sk.gateway.cookies` | `cli.gateway_cookie_names()` lists the gateway cookie names and not their values | SPOREF handoff cookie jar | `[ok]` | `tests/test_cli.py::test_gateway_cookie_names_are_only_names` |

### SPS Info catalog

One VIN the subscription can open. The rows are the controller tree and the calibration part numbers. They are not a calibration file, and they are not every GM VIN.

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.sps.vin` | `spsinfo.check_vin()` accepts one 17-character VIN and refuses I, O and Q | SPS Info viewer | `[ok]` | `tests/test_spsinfo.py::test_a_vin_must_be_seventeen_characters_without_i_o_or_q` |
| `sk.sps.form` | `spsinfo.parse_sporef_form()` reads the form action and its fields | captured SPOREF page | `[ok]` | `tests/test_spsinfo.py::test_the_sporef_form_keeps_the_action_and_the_fields` |
| `sk.sps.save` | `spsinfo.save_vin()` writes the fixture and the programming sequence, and a resync replaces that VIN | captured fixture and progseq | `[ok]` | `tests/test_spsinfo.py::test_the_catalog_is_replaced_when_the_same_vin_is_synced_again` |
| `sk.sps.path` | `spsinfo.save_vin()` refuses a database inside the repository | local catalog file | `[ok]` | `tests/test_spsinfo.py::test_a_database_inside_the_repository_is_refused` |
| `sk.sps.token` | `spsinfo.save_vin()` refuses a document that contains a JWT-shaped string | local catalog file | `[ok]` | `tests/test_spsinfo.py::test_a_token_shaped_string_is_refused` |
| `sk.sps.sync` | `client.sync_sps_vin()` sends the bearer and posts the fixture document | captured progseq request | `[ok]` | `tests/test_spsinfo.py::test_sync_sends_the_bearer_and_posts_the_fixture` |
| `sk.sps.handoff` | `client.request_sps_form()` asks for the SPOREF page with the saved session | captured accessSPSCal request | `[ok]` | `tests/test_spsinfo.py::test_sps_prints_the_catalog_path_and_not_the_bearer` |
| `sk.cli.sps` | `cli.run()` prints the catalog counts and the sqlite path and does not print the bearer | SPS Info viewer | `[ok]` | `tests/test_spsinfo.py::test_sps_prints_the_catalog_path_and_not_the_bearer` |

### Programming data

The body of `POST /sps/legacy/cloud/getProgrammingData` for K17, K33, K20, and K9. A saved module
read supplies the VIT1 control-module block. The function returns that body. A live post waits
until a real read is on disk.

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.vit1.request` | `vit1.programming_data_request()` attaches a saved K17 module read as VIT1 control-module blocks on the controller | saved module read; the traced post with no vit1 is `VIT_NO_VALID_CMB` | `[ok]` | `tests/test_vit1.py::test_a_saved_k17_read_is_the_vit1_block_on_the_request` |
| `sk.vit1.siblings` | `vit1.module_attributes()` pairs a saved read for K33, K20, and K9, and `vit1.programming_data_request()` attaches it | fixture request methods from the VIN catalog | `[ok]` | `tests/test_vit1.py::test_k33_k20_and_k9_reads_attach_as_vit1_blocks` |
| `sk.vit1.format0` | `vit1.format0_decimal()` reads the GMLAN format-0 integer from a service $1A response | spsvcs FUN_10015d80 | `[ok]` | `tests/test_wrapper.py::test_a_positive_gmlan_response_is_the_format0_decimal` |
| `sk.wrapper.init` | `wrapper.parse_init()` classifies the connect string and does not load a library | J2534Tool.init and CSpsVcsImpl::Init | `[ok]` | `tests/test_wrapper.py::test_the_percent_form_names_the_version_and_the_tool` |
| `sk.vit1.rest` | `vit1.module_attributes()` pairs the other method-128 reads whose parts and hardware are format 0, length 4, start 1 | fixture-fresh.json supportedControllers | `[ok]` | `tests/test_vit1.py::test_the_other_method_128_reads_attach` |
| `sk.vit1.normal` | `vit1.programming_data_request()` accepts method 1, the same body as method 128, for K124, K74, K114B, and K36 | GetProgrammingDataTask and ProgrammingMethod.isProgrammingByVCI | `[ok]` | `tests/test_vit1.py::test_method_1_reads_use_the_same_programming_data_body` |
| `sk.vit1.vci` | `vit1.vci_programming_data_request()` builds the method 2 and 256 body and copies the caller's step lists | ProgrammingDataVCIRequest | `[ok]` | `tests/test_vit1.py::test_method_2_is_the_vci_body_and_does_not_invent_steps` |
| `sk.vit1.selected` | `vit1.after_selected_controller()` replaces the root with one response controller and does not copy vit1 | SelectedControllerTask and handleAfterSelectedControllerResponse | `[ok]` | `tests/test_vit1.py::test_one_selected_controller_replaces_the_root_and_drops_vit1` |
| `sk.vit1.progdata` | `vit1.after_programming_data()` raises on a failed body and otherwise keeps only the response controller | GetProgrammingDataTask and validateAndReturnResponse | `[ok]` | `tests/test_vit1.py::test_a_failed_programming_data_response_leaves_the_posted_root` |
| `sk.vit1.sequences` | `vit1.sequences_after_programming_data()` lists the sequences checked for programmingData and raises when one has none | buildPSList and handleNextScreenAfterProgrammingDataRetrieval | `[ok]` | `tests/test_vit1.py::test_a_sequence_without_programming_data_stops_before_a_security_screen` |
| `sk.vit1.modules` | `vit1.normal_programming_data_loop()` raises for unauthored id 10 and for an empty module list that still has a partno | handleNormalAfterProgrammingData | `[ok]` | `tests/test_vit1.py::test_an_empty_module_list_with_a_partno_stops_before_a_security_screen` |
| `sk.vit1.format12` | `vit1.format1_text()` and `vit1.format2_copy()` read the other two GMLAN formats | spsvcs FUN_10015d80 | `[ok]` | `tests/test_vit1.py::test_format1_is_two_characters_per_byte_and_format2_is_the_slice` |

### Not this slice

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.sign-in.password` | `signin.password_update_body()` posts continuationToken and newPassword, using the new password when it is set | captured password update | `[ok]` | `tests/test_signin.py::test_the_password_update_posts_the_new_password_and_not_the_current_one` |
| `sk.sign-in.code` | `signin.authorization_code()` reads the code from the TDS redirect fragment | captured redirect | `[ok]` | `tests/test_signin.py::test_the_redirect_code_is_the_fragment` |
| `sk.sign-in.form` | `signin.token_form()` is the authorization-code form and has no password field | captured token request | `[ok]` | `tests/test_signin.py::test_the_token_form_has_no_password_field` |
| `sk.sign-in.token` | `signin.parse_token_pair()` keeps the access token and the refresh token | captured token response | `[ok]` | `tests/test_signin.py::test_the_token_pair_keeps_the_refresh_token` |
| `sk.sign-in.refresh` | `signin.refresh_form()` is the RFC 6749 section 6 grant and `client.renew_access_token()` stores the new pair | RFC 6749 section 6 | `[ok]` | `tests/test_signin.py::test_a_refresh_replaces_the_access_token_and_a_new_refresh_token` |
| `sk.sign-in.session` | `client.open_backend_session()` posts an empty body and the access-token header | captured TDS login | `[ok]` | `tests/test_signin.py::test_the_code_is_exchanged_and_the_profile_is_discarded` |
| `sk.cli.token` | `cli.run()` writes the access token to the token file and does not print it | captured token response | `[ok]` | `tests/test_cli.py::test_token_command_writes_the_token_and_does_not_print_it` |
| `sk.session.prompt` | `session.prompt_emailed_token()` asks for an access token the person already holds and refuses a short verification code | pasted access token | `[ok]` | `tests/test_session.py::test_the_email_prompt_keeps_an_access_token_and_refuses_the_short_code` |
| `sk.session.file` | `session.write_session()` stores that token outside the repository and `session.apply_saved_session()` reloads it | local session file | `[ok]` | `tests/test_session.py::test_the_session_file_is_reloaded_and_a_path_in_the_repository_is_refused` |
| `sk.cli.session` | `cli.run()` prompts, writes the session file, and a later gateway permissions call does not send that token as Authorization | pasted access token | `[ok]` | `tests/test_cli.py::test_session_prompts_for_the_emailed_token_and_later_gateway_calls_omit_it` |
| `sk.no.vehicle` | do not program a controller, calculate a seed or key, or speak SAE J2534 until that document is imported into primarysource. The dongle and PassThruSupport.04.04 belong to vcxtoolkit | ISO 14229-1:2013 clause 15.4.4 | `[no]` | `docs/tool-boundary.md` |
| `sk.no.security-access` | security access and transfer of a calibration stay out of this package | owner decision | `[no]` | same boundary as the volt research notes |
