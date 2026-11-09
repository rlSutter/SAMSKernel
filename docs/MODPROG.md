# Module programs: a kernel module on a disk, run by a cartridge that has the kernel

Status: **built and tested in the simulator** (1.32.0, 5 November 2026); **not run on real hardware** (docs/HARDWARE-CHECKLIST.md, steps M1 to M3).

## What it is for

A kernel disk program (docs/DISKSTART.md) carries the whole application: a 4.3K bootstrap, the kernel (6.9K), the data pages and its modules. When the cartridge in the slot already holds the kernel, that is a lot to
carry again: measured in the simulator, the bootstrap and the kernel are 27% to 43% of a small program's disk. A **module program** carries only the module. The cartridge supplies the kernel, the loader and the
machine checks; the program is **one file of 134 bytes plus the module** (the hello example's module is 193 bytes, so a 327-byte file: two data sectors and the file's own entry).

## Using it

**The host** is any cartridge built with `"modprog": true` in its `app.json` (it implies `"ea5"`, the cartridge's RUN PROGRAM FILE entry; the workbench cartridge has both). Its kernel's identity, the **build ID**, is printed
by the build (`kernel build ID E8A7222C: ...`).

**The program** is a module, written like any module (the header at `>C000`: INIT, TICK, REDRAW and a flags word; `COPY "kernel.equ"`), built against the host's `kernel.equ`:

    python3 tools/skmodprog.py guest.a99 --target build/workbench -o GUEST [--title "MY GUEST"]
    python3 tools/skmodprog.py guest.a99 --target build/workbench --disk guest.dsk          # a single-density disk with the program on it

`--target` is the host's build directory (or its `kernel.equ`; each release ships `images/workbench.kernel.equ`). The tool assembles the module with the host's names, refuses one larger than the host takes
(`MODMAX`: 8,192 bytes, or 4,096 if the host has common code at `>D000`), and writes the file. To run it: the host cartridge, **RUN PROGRAM FILE**, `DSK1.GUEST`. `examples/modprog/guest.a99` is a small one;
`images/modprog-demo.dsk` has it built for the released workbench cartridge.

## What happens

1. RUN PROGRAM FILE loads the file with the disk controller (as for any option 5 image) into VRAM and looks at it before copying it anywhere: a single file, load address `>2000`, and the signature `SKMP` after the first 96 bytes.
2. It compares the program's **build ID** with the cartridge's own. A program for another build is refused, with both IDs on the screen (`CARTRIDGE >E8A7222C` / `PROGRAM   >6CAFE88E`): its calls would go to the wrong addresses.
   A module longer than the file holds, or than `MODMAX`, is refused too (`MODULE TOO BIG OR DAMAGED`).
3. Otherwise it leaves a hand-off in the scratchpad (`>8320` = `>A55C`, the module's address in VRAM, its length) and jumps to the cartridge's own start. The loader does its usual checks, copies the cartridge's banks into SAMS, then **copies the module over the
   boot module's page pair** and starts the kernel, which starts it as the application (`PGBOOT`). Nothing else changes: the host's other modules, data pages, font and music stay where they were, and the program may call, `GOMOD` to and read them by their
   `kernel.equ` names (`PG_...`, `PD_...`).
4. FCTN = quits as ever: the console resets, to the menu; the program has to be started again from RUN PROGRAM FILE (the cartridge's own application is back at its menu entry).

## The file

An Editor/Assembler option 5 image for `>2000` (so `xas99`'s tools and `tools/ea5.py` read it): the 6-byte header (flag 0, the length, `>2000`), then

| Offset | Bytes | What |
| --- | --- | --- |
| 0 | 96 | the **stub** (`kernel/modstub.a99`): what the Editor/Assembler's own option 5 runs if given the file: it writes `NEEDS THE SAMS KERNEL CARTRIDGE` on row 11 and returns. The kernel cartridge never runs it. |
| 96 | 4 | `SKMP` |
| 100 | 2 | version, 1 |
| 102 | 4 | the host's kernel build ID |
| 106 | 2 | the module's length |
| 108 | 2 | flags, 0 |
| 110 | 18 | the title: a length byte and up to 15 characters, padded |
| 128 | n | the module |

**The build ID** is the CRC-32 of the host's `kernel.equ`: every address of a kernel routine and every equate an application sees (`kdefs.a99`, the generated `appcfg.a99` with the page numbers of its modules and data, the public routines of
`kernel/public.txt`). Anything that moves or renames one changes it: a kernel change, an `app.json` that adds a module or data page, `"omit"` or `"sfx"`, a new release. A bug fix inside a routine that moves nothing does not. That is
the right test for "will this program's calls land": it is conservative, and a refused program is rebuilt against the new `kernel.equ`.

## Limits

- **One module**, at most `MODMAX`. More code goes in a data file the program reads at run time with the kernel's file service (`FOPEN`, `FREAD`, `FLOAD`) into pages from the pool (`PALLOC`).
- The program **is** the application: it replaces the host's boot module, so the host's own program does not run (the host's other modules are still resident for the program to use).
- A program is for **one build** of one cartridge. The workbench cartridge's `kernel.equ` ships with each release; a program built for 1.32.0 needs rebuilding for the next release if the ID changes.
- Not tried: a program that uses the host's other modules; a host with common code at `>D000` (the tool sets the module's single-page flag for a module of 4,096 bytes or less; an 8K module is refused).

## Assumed, not known (to be tried on a real TI)

- The module program's bytes survive in VRAM (`>1406` upward) through the loader's machine checks (a SAMS test of every page, an F18A unlock and detection). The simulator shows they do; the F18A's unlock and the
  checks do not write VRAM in the design, which is all that is known.
- Everything in docs/DISKSTART.md's assumptions about option 5 and the controller's LOAD, as RUN PROGRAM FILE is the same code.

## Tested (simulator, TI controller ROM)

Test group `modprog`: the file's layout and ID; a different kernel build gives a different ID; GUEST boots under the host's kernel and its screen replaces the host's; the hand-off is used once; a program for another build is refused with both IDs and nothing runs; a damaged file is
refused; an ordinary option 5 image still runs on the same cartridge; the stub, run with no kernel cartridge, says what is missing and returns; the tool refuses a module of 9,000 bytes and a host built without `"modprog"`.
