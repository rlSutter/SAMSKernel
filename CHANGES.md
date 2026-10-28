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
- Tested in the simulator against TI's real disk controller DSR (`tools/tifdc.py`, `realdsr` group): catalog decoding, text files, write/read/delete.
  Found there: the DSR has closed the file after a read reports end of file (`FCLOSE` answers 7), and a missing input file opens with error 2.
- `roms/cf7a+.bin`: the CF7+ DSR ROM, added at the author's request (not yet used by any test).
- `docs/PROGRAMMERS-GUIDE.pdf` (13 pages, bookmarked) and `tools/guide_pdf.py` to rebuild it.
- Known: not yet run on real hardware.
