# Instructions for coding agents

`spskit` downloads SPS2 modules an ACDelco TDS subscription is licensed for. `PLAN.md` says what is in
this slice, `ROADMAP.md` is the work queue, and `docs/sources.md` records the captured calls the code
follows. This file takes precedence over `D:\code\AGENTS.md` for work in this project.

## Commands

Run from this directory, never from `D:\code`:

    python -m pytest -q
    python -m ruff format spskit tests
    python -m ruff check spskit tests
    python -m mypy spskit

Use the pinned toolchain in `projecthub/src/projecthub/shells/requirements-dev.txt` when it is installed.

## Invariants

1. **The matrix and the code agree.** A row is `[ok]` only when it names a callable and a test that exists.
   `tests/test_roadmap_rows.py` checks it.
2. **Secrets stay out of the tree.** `.env` is gitignored. `.env.example` has empty username, password and token.
   A verification code is read from the prompt and is not written to disk. `spskit login` asks the host
   to email a code and saves that challenge. `spskit code` sends the typed code. Repeating `spskit code`
   continues the same challenge. `spskit session` writes an access token the person already holds only to
   the session file outside the repository.
3. **The sign-in password is the login form's `passwd` field.** That value is `TDS_NEW_PASSWORD` when it
   is set, and `TDS_PASSWORD` otherwise. The email code goes on `ProcessAuth` as `otc` and nowhere else.
   The reset PUT, when that separate captured path runs, posts `newPassword` and nothing else. The token
   request has no password field. Do not copy a password into the tree.
4. **No vehicle programming.** No security access, no calibration transfer, and no SAE J2534 pass-through until
   that document is in `primarysource`. The dongle and `PassThruSupport.04.04` belong to `vcxtoolkit`.
   The GM wrapper contract, if it is ever spoken, belongs here. `docs/tool-boundary.md` is the split.
   Do not state an RFC or ISO section from memory; read it through `primarysource` first.
5. **Downloads land outside the repository**, at the absolute `SPS_DOWNLOAD_DIR`. A filename that is not a single
   plain name is refused.
