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

### Licensed modules

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.catalog.parse` | `catalog.parse_permissions()` lists name, type and version and drops the account id | captured permissions response | `[ok]` | `tests/test_catalog.py::test_permissions_drop_the_account_id` |
| `sk.catalog.bearer` | `client.list_modules()` sends a bearer only when one was supplied | captured permissions request | `[ok]` | `tests/test_catalog.py::test_listing_sends_a_bearer_only_when_one_was_supplied` |
| `sk.download.body` | `download.credentials_body()` asks for one module with empty token fields | captured downloadCredentials request | `[ok]` | `tests/test_download.py::test_the_request_starts_with_empty_token_fields` |
| `sk.download.grant` | `download.parse_grant()` accepts one https URL and a single plain filename | captured downloadCredentials response | `[ok]` | `tests/test_download.py::test_a_grant_must_be_https_and_a_plain_filename` |
| `sk.download.save` | `client.fetch_module()` writes the bytes under the download directory and nowhere else | captured file fetch | `[ok]` | `tests/test_download.py::test_download_writes_beside_the_given_directory` |

### Not this slice

| Id | Obligation | Spec | Status | Evidence |
|---|---|---|---|---|
| `sk.sign-in.password` | send `TDS_PASSWORD` only as the body of the sign-in step the host named, once that step has been read | captured password method | `[ ]` | (to be written) |
| `sk.sign-in.token` | turn a continued sign-in into the gateway bearer `TDS_ACCESS_TOKEN` | captured token response | `[ ]` | (to be written) |
| `sk.no.vehicle` | do not program a controller, calculate a seed or key, or speak SAE J2534 until that document is imported into primarysource | ISO 14229-1:2013 clause 15.4.4 | `[no]` | the package has no pass-through and no programming service |
| `sk.no.security-access` | security access and transfer of a calibration stay out of this package | owner decision | `[no]` | same boundary as the volt research notes |
