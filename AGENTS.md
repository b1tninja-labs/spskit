# Instructions for coding agents

`spskit` is the GM SPS2 programming-request layer: the VIT1 `getProgrammingData` body and the GM J2534
wrapper connect string, as a library. `PLAN.md` says what is in this slice, `ROADMAP.md` is the obligation
matrix, and `docs/sources.md` records the decompiled paths the code follows. This file takes precedence
over `D:\code\AGENTS.md` for work in this project.

The TDS and Techline Connect client — sign-in, licensed downloads, SPS Info, the Techline Connect launcher
— is `techlinekit` (`D:\code\techlinekit`). `spskit` imports only `techlinekit.spsinfo.check_vin` and
`SpsInfoError` from it. Do not re-add a sign-in, a download, a CLI, a `.env`, or a session file here; that
is techlinekit's job. Do not edit `D:\code\techlinekit` from this package.

## Commands

Run from this directory, never from `D:\code`:

    python -m pytest -q
    python -m ruff format spskit tests
    python -m ruff check spskit tests
    python -m mypy spskit

`techlinekit` is a workspace sibling, not a published dependency. It is put on the import path by the
`pythonpath` (pytest) and `mypy_path` (mypy) entries in `pyproject.toml`, both `../techlinekit`. The
commands above resolve it only when `D:\code\techlinekit` exists beside this checkout.

## Invariants

1. **The matrix and the code agree.** A row is `[ok]` only when it names a callable and a test that exists.
   `tests/test_roadmap_rows.py` checks it.
2. **This package is a library, not a client.** No sign-in, no download, no CLI, no secrets on disk. The
   `[no]` rows in `ROADMAP.md` and `docs/tool-boundary.md` are the split; keep them true.
3. **No vehicle programming.** No security access, no calibration transfer, and no SAE J2534 pass-through
   until that document is in `primarysource`. The dongle and `PassThruSupport.04.04` belong to `vcxtoolkit`.
   The GM wrapper contract, if it is ever spoken, belongs here.
4. Do not state an RFC or ISO section from memory; read it through `primarysource` first.
