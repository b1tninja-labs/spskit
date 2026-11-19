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
| `sk.cli.expired` | `cli.run()` reports an expired session and does not invent a code to send | gateway 401 | `[ok]` | `tests/test_cli.py::test_an_expired_session_is_reported_without_prompting` |
| `sk.login.email` | `login_start.request_email_code()` posts the password and BeginAuth, then `cli.run()` saves the challenge and `spskit code` waits for the email code | captured sign-in | `[ok]` | `tests/test_login_start.py::test_login_posts_the_password_then_waits_for_the_email_code` |
| `sk.login.resume` | `cli.run()` finishes a saved stay-signed-in post and does not call BeginAuth | captured sign-in | `[ok]` | `tests/test_login_start.py::test_a_saved_stay_signed_in_finishes_without_a_new_email` |
| `sk.login.retry` | `cli.urllib_exchange()` retries a connection the host closed | local transport | `[ok]` | `tests/test_cli.py::test_a_closed_connection_is_retried` |
| `sk.client.agent` | `cli.urllib_exchange()` sends the captured Chrome User-Agent | captured browser request | `[ok]` | `tests/test_cli.py::test_the_exchange_sends_a_browser_user_agent` |

### Licensed modules

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.catalog.parse` | `catalog.parse_permissions()` lists name, type and version and drops the account id | captured permissions response | `[ok]` | `tests/test_catalog.py::test_permissions_drop_the_account_id` |
| `sk.catalog.bearer` | `client.list_modules()` sends a bearer only when one was supplied | captured permissions request | `[ok]` | `tests/test_catalog.py::test_listing_sends_a_bearer_only_when_one_was_supplied` |
| `sk.download.body` | `download.credentials_body()` asks for one module with empty token fields | captured downloadCredentials request | `[ok]` | `tests/test_download.py::test_the_request_starts_with_empty_token_fields` |
| `sk.download.grant` | `download.parse_grant()` accepts one https URL and a single plain filename | captured downloadCredentials response | `[ok]` | `tests/test_download.py::test_a_grant_must_be_https_and_a_plain_filename` |
| `sk.download.save` | `client.fetch_module()` writes the bytes under the download directory and nowhere else | captured file fetch | `[ok]` | `tests/test_download.py::test_download_writes_beside_the_given_directory` |

### Licensed files

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.downloads.access` | `catalog.parse_resource_access()` keeps the resource id and runnable flag and drops the account id | Techline Connect permissions search | `[ok]` | `tests/test_downloads.py::test_resource_access_drops_the_account_id` |
| `sk.downloads.list` | `client.licensed_downloads()` asks for the Techline Connect installer and any other decimal resource the account can run | launcher resource 25 and permissions search | `[ok]` | `tests/test_downloads.py::test_the_installer_and_a_decimal_resource_are_listed` |
| `sk.downloads.fetch` | `cli.run()` lists those files, and `--get` writes them under the download directory | same catalog | `[ok]` | `tests/test_downloads.py::test_downloads_lists_and_get_writes_the_file` |

### Not this slice

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.sign-in.password` | `signin.password_update_body()` posts continuationToken and newPassword, using the new password when it is set | captured password update | `[ok]` | `tests/test_signin.py::test_the_password_update_posts_the_new_password_and_not_the_current_one` |
| `sk.sign-in.code` | `signin.authorization_code()` reads the code from the TDS redirect fragment | captured redirect | `[ok]` | `tests/test_signin.py::test_the_redirect_code_is_the_fragment` |
| `sk.sign-in.form` | `signin.token_form()` is the authorization-code form and has no password field | captured token request | `[ok]` | `tests/test_signin.py::test_the_token_form_has_no_password_field` |
| `sk.sign-in.token` | `signin.parse_access_token()` keeps the access token and drops the refresh token | captured token response | `[ok]` | `tests/test_signin.py::test_the_access_token_is_kept_and_the_refresh_token_is_dropped` |
| `sk.sign-in.session` | `client.open_backend_session()` posts an empty body and the access-token header | captured TDS login | `[ok]` | `tests/test_signin.py::test_the_code_is_exchanged_and_the_profile_is_discarded` |
| `sk.cli.token` | `cli.run()` writes the access token to the token file and does not print it | captured token response | `[ok]` | `tests/test_cli.py::test_token_command_writes_the_token_and_does_not_print_it` |
| `sk.session.prompt` | `session.prompt_emailed_token()` asks for an access token the person already holds and refuses a short verification code | pasted access token | `[ok]` | `tests/test_session.py::test_the_email_prompt_keeps_an_access_token_and_refuses_the_short_code` |
| `sk.session.file` | `session.write_session()` stores that token outside the repository and `session.apply_saved_session()` reloads it | local session file | `[ok]` | `tests/test_session.py::test_the_session_file_is_reloaded_and_a_path_in_the_repository_is_refused` |
| `sk.cli.session` | `cli.run()` prompts, writes the session file, and a later command sends that token | pasted access token | `[ok]` | `tests/test_cli.py::test_session_prompts_for_the_emailed_token_and_later_commands_send_it` |
| `sk.no.vehicle` | do not program a controller, calculate a seed or key, or speak SAE J2534 until that document is imported into primarysource | ISO 14229-1:2013 clause 15.4.4 | `[no]` | the package has no pass-through and no programming service |
| `sk.no.security-access` | security access and transfer of a calibration stay out of this package | owner decision | `[no]` | same boundary as the volt research notes |
