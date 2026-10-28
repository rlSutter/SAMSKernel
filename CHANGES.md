# Changes

## 1.0.0 (28 October 2026)

First packaging: Press 2.0's kernel generalised.

- Table-driven loader; refusal screens built from `app.json`.
- `GOMOD` module switching with an argument and `PREVPG`; `.callmod`.
- Page pool (`PINIT`, `PALLOC`, `PRELS`); `MAPE`, `MAPF`, `SETPB`.
- General file service (`FOPEN` ... `FCNUM`); clears stale PAB error bits; restores the console's frame increment.
- `KINIT`, `KFLUSH`, `KWAIT`; `CLS`, `BOX`, `HEX4`, `VSBR`, `SETSCH`.
- `tools/lkbuild.py`, `tools/newapp.py`, `tools/docindex.py`; examples `hello`, `diag`, `browser`; `tests/test_kernel.py`.
- Simulator: optional real console ROM (`TI_CONSOLE_ROM`).
- Known: not yet run on real hardware.
