# SAMS Kernel

A small resident kernel for TI-99/4A programs in TMS9900 assembly, for a console with an **F18A** (or PICO9918) video card and a
**SAMS** memory card, delivered as a cartridge image (FinalGROM 99 "8" format; js99er and Classic99 load it too). It is Press 2.0's
kernel, itself descended from The Lantern Coast's, with everything specific to a word processor taken out.

What you write is a *module*: up to 8K of code that the kernel calls once a frame with the key that was typed. The kernel gives you an 80 x 30 text
screen with colour per cell, a decoded keyboard, every F18A display mode (`VMODE`), optional sprite motion, a music player, a workbench that builds programs on the TI itself, SAMS paging and a page pool, modules that switch and call each other, and disk files (a disk controller, a TIPI or both), plus a loader
that checks the machine, a clean power-up state and a clean exit.

On disk a program is either a whole **disk program** (the kernel and its banks: docs/DISKSTART.md) or just a **module program** for a cartridge that already holds the kernel (134 bytes plus the module: docs/MODPROG.md).

## Two ways to work

**[PC]** On a PC (Python 3 and [xdt99](https://github.com/endlos99/xdt99): put it beside this directory, or set `XAS99` to `xas99.py`):

```
python3 tools/newapp.py myapp --name "MY APP"      a working one-module program
python3 tools/skbuild.py myapp                     build/myapp/myapp8.bin
python3 tools/sim9900.py build/myapp/myapp8.bin --keys "<ALPHA>hello" --frames 200
```

**[TI]** On the TI itself: put `images/workbench8.bin` in the cartridge slot (a FinalGROM 99, or js99er with F18A and SAMS on) and `images/workbench.dsk` in DSK1, then press **N**, type `DSK1.HELLO/A99`, **ENTER**,
**E** to edit, **A** to assemble, **R** to run. Make your own program with **N** `DSK1.MINE/A99` ENTER, **E**, type, **CTRL A**, **R**. No PC is needed once the cartridge and disk exist.

**[PC or TI]** The assembly source and every kernel call are the same on both routes. Documents mark what belongs to one route only:

| Mark | Where | What you use |
| --- | --- | --- |
| **[PC]** | on a PC with Python 3 and [xdt99](https://github.com/endlos99/xdt99) | any editor; `skbuild.py` builds a cartridge image; the simulator, js99er or a real TI runs it; `skdisk.py`, `skmusic.py` and the tests help |
| **[TI]** | on the TI-99/4A itself (or js99er playing one), with the workbench cartridge and its disk | the workbench's editor, assembler and launcher: nothing else |
| **[PC or TI]** | either | the same either way: the assembly source and every kernel call |


| | **[PC]** | **[TI]** |
| --- | --- | --- |
| Modules | as many as you like | one (up to 4,096 bytes, at `>C000`) |
| Data pages, compiled music, own font | yes | no |
| Output | a cartridge image | runs inside the workbench |
| Test | the simulator and key scripts | run it and look |

The full comparison is in [docs/PROGRAMMERS-GUIDE.md](docs/PROGRAMMERS-GUIDE.md) part 0.

## Read

| | |
| --- | --- |
| [docs/PROGRAMMERS-GUIDE.md](docs/PROGRAMMERS-GUIDE.md) ([PDF](docs/PROGRAMMERS-GUIDE.pdf)) | **start here**: write an application. The PDF is built by `tools/guide_pdf.py` (pandoc, wkhtmltopdf, pypdf, reportlab) |
| [docs/ROUTINES.md](docs/ROUTINES.md) | every kernel routine: inputs, outputs, registers used (generated from the source) |
| [docs/VIDEO-MODES.md](docs/VIDEO-MODES.md) | every F18A display mode `VMODE` sets, with pictures: Text 80/40, Graphics I/II, Multicolor, enhanced colour, sprites, tile layer 2, the bitmap layer |
| [docs/WORKBENCH-MANUAL.md](docs/WORKBENCH-MANUAL.md) ([PDF](docs/WORKBENCH-MANUAL.pdf)) | **the workbench user manual**: starting it, the editor's keys, the assembler's syntax and errors, tutorials, troubleshooting |
| [docs/WORKBENCH.md](docs/WORKBENCH.md) | the workbench: an editor, a native assembler and a launcher that run on the TI itself: how it is built and what it costs |
| [docs/RATIONALE.md](docs/RATIONALE.md) ([PDF](docs/RATIONALE.pdf)) | **why the kernel is the way it is**: the problem, the lineage, the design decisions and their alternatives, the use cases |
| [docs/MUSIC.md](docs/MUSIC.md) | music and sound: the player, the compiler (MIDI or a text score to songs), the song format |
| [docs/HARDWARE-CHECKLIST.md](docs/HARDWARE-CHECKLIST.md) | **what has and has not been run on real hardware**, and how to try each thing on a real TI (or js99er): the list to work through next |
| [docs/DEVELOPING-ON-A-TI.md](docs/DEVELOPING-ON-A-TI.md) | working with a real TI: the first-run ladder, refusal messages, debugging, editing on the TI, and what is not possible yet |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | how the kernel works inside; memory maps |
| [docs/HARDWARE.md](docs/HARDWARE.md) | the machine's facts the kernel relies on; the key-code table |
| [docs/GLYPHS.md](docs/GLYPHS.md) | the 256-glyph set |
| [docs/RESIDENT.md](docs/RESIDENT.md) | code every module can call: resident code in the kernel's pages (`app.json` `"resident"`), the options it was chosen over, its budget |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | the rules the code follows |
| [docs/FROM-PRESS.md](docs/FROM-PRESS.md) | what came from Press, what did not, what rebasing Press would take |

## The sources on a TI disk

`python3 tools/mksources.py sources.dsk` makes a 360K disk (`SOURCES`) of the kernel's sources, `lib/`, the generated font and key table
and two example programs, to read and edit on the TI; seven file names are shortened to fit a TI disk (its `SRCNOTES` file lists them).
The kernel cannot be assembled on the TI from it yet.

## Optional includes (`lib/`)

Code that is not worth the kernel's last kilobyte but that many programs want: `COPY` it into your module (the build finds
`lib/`; on the TI put the file on the program's disk).

| | |
| --- | --- |
| `lib/linein.a99` | `LINEIN`: edit a line of up to 159 characters on the screen (insert and overtype, the function keys, a scrolling field, a history in a pool page); about 900 bytes; example `examples/workbench/programs/ask.a99` |

## Examples

| | |
| --- | --- |
| `examples/hello` | one module, 194 bytes: prints, echoes keys, quits |
| `examples/editor` | a text editor as a program of its own: a 1,500-byte front module (a file-name prompt with `LINEIN`) in front of the workbench's editor module, reused unchanged |
| `examples/diag` | two modules: a key/glyph/colour diagnostic, and a self-test of the kernel's services (CTRL T). Run it first on new hardware |
| `examples/modes` | one module, fifteen screens: every display mode and option (keys `1-9 0 A-E`); the pixel tests render them |
| `examples/workbench` | the workbench: edit, assemble and run programs on the TI (an editor, a native assembler checked against xas99, a launcher) |
| `examples/joystick` | both joysticks: states, fire presses, and a switch that makes a joystick type arrow keys |
| `examples/music` | a music player: two songs from SAMS pages, pause, stop, tone effects, music stepping through a long loop |
| `examples/reversi` | a whole program in one module (3,392 bytes): Reversi against the computer, with hints, two levels, joystick and keyboard, save and open. Builds on a PC and assembles on the TI (it is on the workbench disk); checked against a Python model of the rules |
| `examples/browser` | two modules: a DSK1 catalog browser and a text-file viewer (GOMOD with an argument, the file service, the page pool, slot B paging) |

## Tests

```
python3 tests/test_kernel.py            sources dbg sams16 joystick files2 native nativemods nativedisk workbench workbenchfull boot refusal ram keys quit modules files browser modes modesquit music rom realdsr
TI_CONSOLE_ROM=/path/to/console-rom TIFDC_ROM=/path/to/disk-controller-rom python3 tests/test_kernel.py rom realdsr
```

The tests run the examples in `tools/sim9900.py`, a headless TMS9900 + F18A + SAMS + keyboard + stand-in disk simulator. With `TI_CONSOLE_ROM` set to your
own copy of the 8K console ROM (a raw dump, or an EA5 image), it runs TI's real interrupt routine; with `TIFDC_ROM` set to the 8K disk controller ROM (the two 4K EPROM images joined, low half first) the file service and the
disk browser run against TI's own DSR on a WD1771 and a disk image (`tools/tifdc.py`). The console and disk controller ROMs are TI's: they are not, and must not be, part of this repository. The ROMs that are here (`roms/`, see `roms/README.md`) are the CF7+ DSR (no test uses it yet) and the CorComp and Myarc controller cards' ROMs, added at the project owner's request; the CorComp and Myarc DDCC-1 ROMs are used by the tests (double-density disks, `tools/ccfdc.py`, `tools/myfdc.py`); the Myarc HFDC's too (its floppy side only: `tools/hfdc.py`). Their licence is not the project's: see `roms/README.md`.

## Status

Version 1.35.0. All test groups pass in the simulator, including with TI's real console interrupt routine and TI's real disk controller DSR (both from your own
ROM images). **It has not been run on a real TI-99/4A.** The parts it shares with Press and The Lantern Coast have (paging, the keyboard, the F18A text screen, files through the disk controller); everything
else is new since: the module system, the page pool, every other F18A mode, the music player, joysticks, several open files, cards above 1M, the workbench. js99er with a 16M SAMS has run the kernel (it found the QUIT bug fixed in 1.3.1). Run `examples/diag` and press
CTRL T on the first real machine, then work through [docs/HARDWARE-CHECKLIST.md](docs/HARDWARE-CHECKLIST.md).

MIT License, (c) 2026 Rebecca Sutter. Code from the owner's other projects (TXA, Press) that is taken into this tree is MIT too, and each such file says so.
