# Instructions for coding agents

`spskit` is the GM SPS2 programming-request layer, a **Rust crate**: the VIT1 `getProgrammingData`
body and the GM J2534 wrapper connect string, as a library plus the offline `spskit-vit1` CLI.
`PLAN.md` says what is in this slice, `ROADMAP.md` is the obligation matrix, and `docs/sources.md`
records the decompiled paths the code follows. This file takes precedence over `D:\code\AGENTS.md`
for work in this project. It was ported from Python behaviour-for-behaviour; the git history holds the
Python original.

The TDS and Techline Connect client — sign-in, licensed downloads, SPS Info, the Techline Connect
launcher — is `techlinekit` (`D:\code\techlinekit`, a separate Python repo). The one rule `spskit`
needs from it, VIN validation, is reproduced in `src/vin.rs` because there is no Rust `techlinekit`.
Do not re-add a sign-in, a download, a client CLI, a `.env`, or a session file here; that is
techlinekit's job. Do not edit `D:\code\techlinekit` from this crate.

## Commands

Run from this directory, never from `D:\code`:

    cargo build
    cargo test
    cargo clippy --all-targets -- -D warnings
    cargo fmt --check
    RUSTDOCFLAGS=-D warnings cargo doc --no-deps

`udskit` is a workspace sibling (`D:\code\udskit`), put on the build path by the path dependency
`udskit = { path = "../udskit" }` in `Cargo.toml`. The commands above resolve it only when
`D:\code\udskit` exists beside this checkout; CI checks it out beside `spskit` the same way.

## Invariants

1. **The matrix and the code agree.** A `ROADMAP.md` row is `[ok]` only when it names a callable and a
   Rust test that exists and would fail if the behaviour regressed. The table is `Status | Obligation |
   Anchor | Test`; `python -m projecthub sync --check` keeps it honest against the GitHub issues.
2. **This crate is a library, not a client.** No sign-in, no download, no client CLI, no secrets on
   disk. The one CLI, `spskit-vit1`, is an offline transform: a captured clone file and a VIN in, a
   request body out. The `[no]` rows in `ROADMAP.md` and `docs/tool-boundary.md` are the split; keep
   them true.
3. **No vehicle programming.** No security access, no calibration transfer, and no SAE J2534
   pass-through until that document is in `primarysource`. The dongle and `PassThruSupport.04.04`
   belong to `vcxtoolkit`. The GM wrapper contract, if it is ever spoken, belongs here.
4. **One Rust source of truth for UDS/GMLAN framing.** The `$7F` negative-response marker and the
   `$1A` GMLAN ReadDataByIdentifier service id the format decoders key on are read from the sibling
   `udskit` crate (`../udskit`), not re-rolled. The SPS/VIT1 request shaping itself is spskit's own.
5. `unsafe` is forbidden (set in `Cargo.toml`). Edition 2024, MSRV 1.85.
6. Do not state an RFC or ISO section from memory; read it through `primarysource` first.
