# Changes

## 1.1.0 (28 October 2026)

All of the F18A's display modes.

- `VMODE`: Text 80, Text 40, Graphics I, Graphics II, Multicolor; 24 or 30 rows; an attribute per position; enhanced colour 1-3 for tiles and for sprites; sprites on, 16 x 16, magnified.
  `VREG` and the `VR_*` register names reach tile layer 2, scrolling, page sizes, the bitmap layer (4 or 16 colours) and the rest.
- The text routines (`PUTS`, `PUTC`, `FILLA`, `FILLN`, `CLS`, `BOX`, `VSHIFT`) follow the mode: `TXCOLS`, `TXROWS`, `TXCELLS`, `TXATTR`, `NAMBAS`.
- **The VRAM map moved** (patterns `>1000` -> `>1800`, attributes `>1800` -> `>0A00`, GPU `>2800` -> `>0960`) so that every mode, enhanced colour planes included, fits one layout.
- `F18OFF` puts back every register `VMODE` and `VREG` can change.
- `kernel.equ` exports only the public routines (`kernel/public.txt`) and the equates, so adding a kernel label cannot collide with an application's.
- `examples/modes`, `tools/f18render.py` (draws any F18A mode from the simulator), `tools/mkshots.py`, `docs/VIDEO-MODES.md` with pictures; tests `modes`, `modesquit`.
- Unverified: the renderer follows js99er's F18A model, not hardware; the bitmap layer in Text 80 is untested; Graphics II has no 30-row form.

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
