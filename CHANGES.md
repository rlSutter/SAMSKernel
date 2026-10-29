# Changes

## 1.7.0 (30 October 2026)

The editor is the guide's multi-page example, and the sources begin to be commented for learning.

- **The workbench editor keeps its lines in pool pages** (`PALLOC`, as the file grows) instead of a fixed block of 16 pages: up to 2,040 lines (was 800), a 51-line block per page, a page table (`EDPGT`) in APPRAM and an order table on a page of its own. `REVERS/A99` (986 lines) could not be opened whole by the old editor; commented sources would be longer still. `PROGRAMMERS-GUIDE.md` appendix C explains the design; `ed.a99` is commented for it.
- **A file too long for the buffer** is loaded in part, the screen says so, and saving is refused (before, it was cut silently and a later save would have cut the file on the disk).
- **Running a program (`R`) gives the editor's pages up**, so a program may use the whole pool and `PINIT` it; `R` refuses to run while the editor holds unsaved changes.
- **Fixed:** with 1.6.0's 31-character names the editor's 24-byte name buffer overflowed into its free list (a name over 23 characters).
- **Comments** (the assembled output is byte for byte unchanged, checked on all 54 build outputs and on each program): `examples/hello` (a tutorial header and the idioms explained), `ed.a99`, `kernel/pager.a99`, `kernel/pool.a99`, `kernel/kernel.a99`, `kernel/macros.a99` and the workbench programs `beep`, `mode`, `clock`, `copy`, `paging`. **Not yet commented to this depth:** the rest of the kernel (`video`, `keys`, `text`, `vdp`, `loader`, `music`, `f18a`; `files` and `kdefs` already had thorough comments), `examples/browser`, `diag`, `modes`, `music`, `joystick`, `reversi` (already well commented), and `wb.a99` and the assembler (`asm_*.a99`).
- **Two workbench disks** (`workbench.dsk`, `examples.dsk`): the commented programs no longer fit on one 90K disk.
- Tests: group `editorpages` (a 1,100-line file in 22 pool pages, edit and save of 600 lines, the 2,040-line limit and the refusal to save a cut file, no run over unsaved edits).

## 1.6.0 (29 October 2026)

Support for a TIPI (and any second DSR card).

- **Fix: every card is powered up.** `DSRLNK` ran the power-up routine of the first card whose device was used, once; a TI disk controller used after a TIPI was never powered up (its VRAM buffers were never made). Now the first device call runs every card's power-up list, in CRU order, as the console does. `tests/apps/tipi` copies from a TIPI model to the real TI controller ROM's disk with the TIPI used first (and shows the copy fails without the power-up).
- **`CLKGET`**: reads TIPI's `PI.CLOCK` (`w,mm/dd/yy,HH:MM:SS`) into `DTDOW DTMON DTDAY DTYEAR DTHOUR DTMIN DTSEC`; new `programs/clock.a99` on the workbench disk.
- **The workbench's includes** come from the main file's directory first (so `PI.PROJ.MAIN/A99` finds `PI.PROJ.INC/A99`), then from the device alone (`PI.KERNEL/EQU`); file names up to 31 characters.
- `tools/skdisk.py --dir DIR` writes the disk's files as TIFILES for a TIPI directory (naming not checked against a real TIPI). The simulator has a model of a TIPI (a card at `>1000`, `PI.` files, a clock). Test group `tipi`.
- **Example: Reversi** (`examples/reversi`, one module of 3,392 bytes; on the workbench disk as `REVERS/A99`): the board painted with attributes and colour roles, keyboard and joystick, hints, two levels, save and open. Checked against a Python model (`tests/reversi_model.py`; groups `reversi`, `reversiti`); the tests found three bugs in it (the disc count crossed the border cells, the winner message jumped on an `LI`'s flags, a routine clobbered its caller's R9). Guide: an appendix, and two checklist items.
- Not tried: a real TIPI's DSR under this kernel, its open-file limit, its answer to a catalog request, and the exact file naming it wants.

## 1.5.2 (29 October 2026)

Every document now shows both ways of working, marked **[PC]**, **[TI]** or **[PC or TI]** (the legend and a comparison table are in the programmer's guide part 0 and the README; each document has a route note and the parts that differ carry their own).

- New programs on the workbench's disk, one for each area the guide covers, each assembled and run on the simulated TI by the new test group `tiprograms`: `MODE/A99` (`VMODE`, Text 80 / Text 40), `PAGING/A99` (the page pool, `MAPE`, `GETPB`/`SETPB`), `COPY/A99` (two files at once), and `examples/joystick/joy.a99`, which now also assembles on the TI (its variables sit at `APPRAM+5760`, clear of the workbench's own state; so do those of the other programs).
- `WORKBENCH.md` part 2a: one program, typed and run on the TI, built and run on the PC; the same 50 bytes.
- The conventions list the extra rules of the TI route; the hardware checklist marks its steps by route; the skill states the routes.

## 1.5.1 (29 October 2026)

Documentation only; no code or image changed. `docs/HARDWARE-CHECKLIST.md` (what has and has not run on a real machine, and a twelve-step walk through the rest, with what to expect and what to report); stale statements corrected (the guide said 1M and "version 1.1";
the architecture notes listed cards over 1M and sound as untested for the wrong reasons); the README's status says what is old and what is new.

## 1.5.0 (29 October 2026)

- **Joysticks.** `KPOLL` reads both joysticks (keyboard columns 6 and 7) every frame: `JOYGET` (R0 = 1 or 2) returns what is down and the presses since the last look, `JOY1`/`JOY2` hold the states, and `JOYKEY` makes the kernel type
  arrow-key and ENTER codes for a joystick with the keyboard's repeat. New `examples/joystick`; the simulator's key script has `<J1-FIRE>`, `<J1-LEFT+UP>`, `<J2-DOWN>`. Test group `joystick`.
- **Several files open at once.** Each file has a handle 0-2, chosen with `FSEL`; every handle keeps its own PAB in VRAM and its own place in its file, and `FOPEN FREAD FWRITE FCLOSE FDELETE` act on the selected one. Handle 0 is the default, so existing code is unchanged. Three
  is the disk controller's own limit (its three file buffers). Test group `files2` (a file copied while a third is read alongside, against TI's real controller ROM and the stand-in drive; `tests/apps/files2`).
- Not tried on a real TI: real joysticks, and the file handles on a controller other than TI's (TIPI, CF7+ ...).

## 1.4.0 (29 October 2026)

The kernel uses the whole of a big SAMS card: pages are numbers 0-4095 (up to 16M), where they were 0-255 (1M).

- **A clean break in the slot-B save-and-restore idiom.** `CURPA/CURPB/CURPC` (one packed word a slot) are gone; the pager records one page a window in `CURA2 CURA3 CURBE CURBF CURCC CURCD` (`>21E0-21EB`). `GETPB` (new) returns the pages in `>E000` and
  `>F000` in R0 and R1; `SETPB` now takes them in R0 and R1 (it took one packed word in R0). Code that did `MOV @CURPB,R0 ... BL @SETPB` becomes `BL @GETPB` ... `BL @SETPB` with both registers saved. The kernel, the music player and the diagnostic are converted.
- `MAPPG` writes a page with its bytes swapped (`SWPB`), the layout of a 12-bit register; for pages under 256 this is what 1.3.1 wrote. `AMSSIZ` tells 32 ... 4,096 pages (it stopped at 256); `AMSTST` tests them all (about 0.25 million instructions on 16M); the refusal screen shows 3 digits.
- The page pool's bitmap is 512 bytes at `>BE00` in the kernel's own pages (it was 32 bytes in slot A); `skbuild.py` refuses a kernel over 7,680 bytes (it is about 5,000). `"min_pages"` may be 32 ... 4096.
- The self-test checks pages above 255 (each its own page, page >30 undisturbed) and the pool's last four pages. Test group `sams16`: cards of 128K, 1M, 2M and 16M in the simulator, QUIT included.
- Not tried on a real card above 1M, nor in js99er's 16M setting.

## 1.3.1 (29 October 2026)

- **Fix: QUIT on a SAMS of more than 1M.** The page registers were written with the page in both bytes of the word; on a 12-bit card the odd byte is bits 8-11, so identity-mapped page *p* was not page *p*, and switching the mapping off at quit moved the
  kernel's own code out from under it (found by running the 1.3.0 images on a 16M card in js99er: everything worked until QUIT). `MAPPG` and `AMSINI` now write the page in the high byte only. The simulator models 12-bit registers (`tests/test_kernel.py sams16`).
- **Fix: the workbench disk.** It held `MUSIC/A99`, which needs `PD_TUNE` and `PD_SCALE` (data pages of the music app's own build): two undefined symbols on the workbench. The disk now holds hello, `beep` (a new program for the workbench), modes and a probe source, and the test group `nativedisk` checks that all of them assemble and that beep plays its note.

## 1.3.0 (29 October 2026)

Building on the TI: `examples/workbench`, with a native assembler, an editor and a launcher (docs/WORKBENCH.md).

- `asm.a99`, a module of 5.3K: two passes, `COPY` includes, every TMS9900 instruction and operand form, `AORG DATA BYTE TEXT STRI EVEN EQU COPY END BSS`, the kernel's macros built in, xas99's left-to-right expressions and
  alignment rules, 12-character symbols. **Byte-identical to xas99** for every example module and for two probe sources, on the simulated TI reading its source through TI's disk controller ROM. It encodes `LDCR Rn,16` correctly (xas99 makes an STCR of it).
- `ed.a99`, a full-screen DIS/VAR 80 editor (800 lines of 80 columns); `wb.a99`, the shell: file name, disk catalog, assemble, run, back to the menu with `GOMOD PG_WB`.
- `tools/skdisk.py` (a disk of sources plus KERNEL/EQU), `tools/asmharness.py` (the assembler and the whole workbench in the simulator); test groups `native`, `nativemods`, `workbench`, `workbenchfull` (a program typed in the editor, assembled and run).
- The 80-column fixer now computes split strings' lengths with the assembler instead of freezing a count; `skbuild.py` exports each module's symbols (`NAME.equ`).
- Unverified: a real TI, real assembly time, the way the workbench's disk reaches a real machine.

## 1.2.0 (28 October 2026)

Renamed **SAMS Kernel** (it was "Lantern Kernel"; `lkbuild.py` is now `skbuild.py`, the diagnostic `skdiag8.bin`; The Lantern Coast, the game it descends from, keeps its name). Music.

- Music: `MUPLAY`, `MUSTOP`, `MUPAUSE`, `MUTICK`, `SNDTONE`, `SNDOFF`; the SKM song format (a register log, 192 bytes of player); stepped every frame by the main loop and by `KIDLE`, `KPFR`, `KWAIT`;
  songs read from SAMS pages through slot B, which the player puts back each frame.
- `tools/skmusic.py`: MIDI files and a text score language (MML) to SKM, with loops, PAL timing and a WAV preview from `tools/sn76489.py`, a model of the sound chip. `skbuild.py` compiles `"from"` data entries.
- `examples/music`; `docs/MUSIC.md`; tests `music` (bytes, timing, pitch by Fourier transform, pause, resume, loop, KIDLE stepping, MIDI) and under TI's real console ROM.
- Sources fit a TI text file: `tools/lint80.py` (check, and `--fix` without changing a byte of the program; all images identical), test group `sources`; `kernel/dbg.a99`, a register display for debugging; `docs/DEVELOPING-ON-A-TI.md`.
- The build keeps an application's files from shadowing the kernel's during the kernel's assembly.
- Unverified: how the music sounds on a real TI, and the player mixed with the console's sound lists.

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
- `tools/skbuild.py`, `tools/newapp.py`, `tools/docindex.py`; examples `hello`, `diag`, `browser`; `tests/test_kernel.py`.
- Simulator: optional real console ROM (`TI_CONSOLE_ROM`).
- Tested in the simulator against TI's real disk controller DSR (`tools/tifdc.py`, `realdsr` group): catalog decoding, text files, write/read/delete.
  Found there: the DSR has closed the file after a read reports end of file (`FCLOSE` answers 7), and a missing input file opens with error 2.
- `roms/cf7a+.bin`: the CF7+ DSR ROM, added at the author's request (not yet used by any test).
- `docs/PROGRAMMERS-GUIDE.pdf` (13 pages, bookmarked) and `tools/guide_pdf.py` to rebuild it.
- Known: not yet run on real hardware.
