# SAMS Kernel: the workbench

The workbench is a program for the TI itself: an **editor**, an **assembler** and a **launcher** in one application, built on the kernel. With it you write a SAMS Kernel program, assemble it and run it
on the TI, with no PC in the loop once the workbench is installed.

**What is checked, and what is not.** All of it runs in a simulator (a TMS9900, the F18A, SAMS, a keyboard, TI's own console ROM and disk controller ROM). The assembler's output is
byte-identical to xas99's for every example module and for two probe sources that use every instruction in every operand form; the editor, the catalog, the assembling and the running are
exercised by key scripts. **It has not run on a real TI-99/4A**, and I have not measured how long an assembly takes on one (part 6 gives instruction counts).

## 1. Getting it onto the TI

A PC is needed once, to make two things:

```
python3 tools/skbuild.py examples/workbench          build/workbench/workbench8.bin: the cartridge image (FinalGROM 99 "8" format)
python3 tools/skdisk.py work.dsk --kernel-equ build/workbench/kernel.equ examples/hello/hello.a99 ...
                                                     a disk image holding KERNEL/EQU and your sources
```

`images/workbench8.bin` and `images/workbench.dsk` in the distribution are these, prebuilt (the disk holds KERNEL/EQU, hello, beep, modes and a probe source). Put the cartridge image where your cartridge
device wants it, and the disk in DSK1 (a TIPI, a CF7+ or a floppy; how the image gets there depends on your hardware, and I have tried none of them). **KERNEL/EQU must come from the same build as the
workbench cartridge**: it holds the addresses of the kernel's routines and equates in that build, and a program assembled against another build's addresses will not run.

The disk image is single-sided single-density (90K), the format TI's own controller and the simulator use. I have not tried it in js99er, whose disk controller setting matters (a double-density "Generic Disk" setting reads other images than TI's own); if it does not read it, make the disk in the format your setup wants.

You need the same machine as for any SAMS Kernel program: an F18A and 512K of SAMS.

**What can be assembled here.** KERNEL/EQU holds the kernel's symbols and the workbench's own (`PG_WB`, `PG_ASM`, `PGUSER`...). A source that needs equates only another application's build has cannot assemble: `examples/music` uses
`PD_TUNE` and `PD_SCALE`, the pages its songs are built into, so it is not on the workbench disk (`beep` is the sound example there). `tests/test_kernel.py nativedisk` checks that everything on the disk assembles.

## 2. The menu

| Key | |
| --- | --- |
| `N` | type a file name (ENTER done, FCTN S or FCTN 1 delete a character, FCTN 9 leaves). It starts as `DSK1.` |
| `C` | the catalog of the file name's disk: UP and DOWN pick, ENTER chooses, FCTN 9 returns |
| `E` | edit the file (a new file if it is not on the disk) |
| `A` | assemble the file; the result, or the errors with their line numbers, appear below |
| `R` | run the program just assembled |
| FCTN = | quit |

TI file names have no dots, so a source file called `hello.a99` on a PC is `HELLO/A99` on the TI (xdm99 and `skdisk.py` do this): the name to type is `DSK1.HELLO/A99`.

## 3. The editor

A full-screen editor for DIS/VAR 80 files, up to 800 lines of 80 columns. The status bar shows the line, the column, INS or OVR, and `*` when there are unsaved changes.

| Key | |
| --- | --- |
| arrows (FCTN E S D X) | move |
| FCTN 5 BEGIN, FCTN 6 PROC'D | start, end of the line |
| FCTN 7 AID, FCTN 8 REDO | up, down 20 lines |
| typing | inserts; FCTN 2 INS switches to overwriting |
| ENTER | splits the line at the cursor |
| CTRL H | deletes the character before the cursor; at the start of a line it joins the line to the one before (if both fit in 80 columns) |
| FCTN 1 DEL | deletes the character under the cursor |
| FCTN 3 ERASE | deletes the line |
| CTRL S | saves (trailing blanks cut) |
| CTRL A | saves and goes to the menu and assembles |
| CTRL X | back to the menu (press twice to leave unsaved changes) |

The keys are those the kernel's keyboard layer decodes (`examples/diag` shows every chord). Lines are stored in SAMS pages in the order of a table, so inserting and deleting lines moves only the table.

## 4. The assembler

It reads xas99's dialect, the part the examples use:

- labels (at the start of a line, an optional colon), comments after the operand field, `*` or `;` lines;
- every TMS9900 instruction, with the operand forms `Rn`, `*Rn`, `*Rn+`, `@expr`, `@expr(Rn)`; `NOP`, `RT`; case does not matter (`mov r1,r2` is fine);
- `AORG`, `DATA`, `BYTE`, `TEXT`, `STRI`, `EVEN`, `EQU`, `COPY`, `END`, `BSS`; `LIST`, `UNL`, `TITL`, `IDT`, `PAGE` are accepted and ignored;
- the kernel's macros `.enter .leave .push R .pop R .intsvc .callmod page,entry`, built in; `COPY "macros.a99"` is accepted and ignored;
- expressions of `+ - * /` and parentheses, **evaluated strictly left to right** (as xas99 does: `2+3*4` is 20); decimal, `>hex`, `'c'` and `'cc'`, symbols, and `$` (the address where the statement starts; inside a `DATA` or `BYTE` list, the address of that item).

Instructions and `DATA` are placed on even addresses (a padding byte is added), and a label on such a line takes the aligned address, as in xas99.

| | |
| --- | --- |
| symbol names | up to 12 characters, upper and lower case the same; at most about 580 symbols (the kernel's 274 included) |
| image | up to 4,096 bytes, in one run from the first `AORG` (gaps between `AORG`s are zero-filled) |
| `EQU` | its value must be defined already (xas99 has the same rule) |
| strings | `TEXT` and `STRI` take one quoted string, `''` for a quote; no empty `STRI ''` |
| `COPY "name"` | the file `name` on the main file's disk, dots turned into slashes (`kernel.equ` is `KERNEL/EQU`); up to three levels |
| not supported | user macros (`.defm`), `DEF`, `REF`, relocatable output, listings |

**Errors.** The list shows the line number, a message, and `(in a COPYed file)` if the line is in an included file. Besides the errors xas99 reports, it also refuses a `SBO`/`SBZ`/`TB` displacement outside -128..127, a shift
count over 15, an `XOP` level over 15, an `LDCR`/`STCR` count outside 1-16, a `BYTE` outside -128..255 and a name over 12 characters. Unknown operations, bad operands, undefined symbols, labels defined twice, jumps out of range or to odd
addresses, `COPY` of a file that is not there, `AORG` that is not defined and a label whose value changes between the passes are errors, as in xas99.

**One difference from xas99 is deliberate.** xas99 assembles `LDCR Rn,16` as `>3401`, which is `STCR Rn,0`; the TI's own encoding for 16 bits is 0, `>3001`, and that is what the workbench produces.

## 5. Writing a program for it

A program is **one kernel module**, as in the programmer's guide, with these specifics:

```
       COPY "kernel.equ"             the kernel's routines and equates (the file KERNEL/EQU)
       COPY "macros.a99"             accepted, and the macros are built in
       AORG >C000                    a module lives at >C000
       DATA INIT,TICK,REDRAW,0       the entry table first
INIT   ...
```

- `R` puts the image into two SAMS pages, `PGUSER` (an equate in KERNEL/EQU: the workbench's first free page + 2), and switches to them with `GOMOD`; the program's `INIT` runs with R0 = the workbench's page.
- **To come back**: `LI R0,PG_WB / CLR R1 / BL @GOMOD`. The assembled image stays in the workbench's memory, so `R` runs it again without assembling. FCTN = quits the whole workbench.
- The program shares the kernel with the workbench. Free SAMS pages for your own use start at `PGUSER+2`; the editor's buffer uses the pages above that, and a program that uses them loses the editor's text (the file on the disk is safe).
- The program is not a cartridge: it exists in SAMS while the workbench runs. The workbench cannot write a cartridge image (a FinalGROM's storage is not something the TI can write); for that, build the program on the PC with `skbuild.py`.

## 6. How it works, and what it costs

`asm.a99` is a module of 5.3K. It reads the source a line at a time with the kernel's file service, **twice** (pass 1 gives every label its address, pass 2 produces the bytes). The symbol table is a hash table of 14-byte entries in two SAMS pages mapped
at `>E000`; the image is built in a 4K buffer in slot A. A `COPY` closes the file, assembles the included file, and reopens the first file, reading on to where it was (the file service has one file open at a time). Pass 2 does not read KERNEL/EQU again: its symbols stay in the table.
The editor (`ed.a99`, 2.4K) keeps lines in SAMS pages (51 lines of 80 bytes a page) in the order of a table of slot numbers. The shell is `wb.a99` (2K).

Instructions executed, in the simulator, including reading the disk through TI's disk controller ROM and the 274-line KERNEL/EQU:

| Source | Lines | Image | Instructions |
| --- | --- | --- | --- |
| `examples/hello` | 67 | 194 bytes | 1.9 million |
| `examples/diag` | 630 | 2,260 bytes | 6.8 million |
| `examples/modes` | 754 | 2,870 bytes | 8.2 million |

A real TI's speed in seconds is not measured. As a guess only, at a few hundred thousand instructions a second, a small program would take seconds and the larger ones tens of seconds.

## 7. Checking it

```
python3 tests/test_kernel.py native          the probes byte for byte against xas99, the error file, LDCR
python3 tests/test_kernel.py nativemods      every example module assembled on the simulated TI, against xas99's
python3 tests/test_kernel.py workbench       the editor's keys, the catalog, a program returning to the workbench
python3 tests/test_kernel.py workbenchfull   type a program in the editor, assemble it, run it
```

They need the disk controller ROM (`TIFDC_ROM`, see `tools/tifdc.py`) and xdt99 (`XAS99`); without the ROM they say so and skip. `tools/asmharness.py` is the harness: `assemble(source, app)` runs the assembler in the simulator,
`workbench_ui(keys, frames, files)` plays a key script against the whole workbench.

Not verified: a real machine, real timing, and the path from a TIPI, CF7+ or floppy to the workbench's disk.
