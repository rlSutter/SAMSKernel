# SAMS Kernel

A small resident kernel for TI-99/4A programs in TMS9900 assembly, for a console with an **F18A** (or PICO9918) video card and a
**SAMS** memory card, delivered as a cartridge image (FinalGROM 99 "8" format; js99er and Classic99 load it too). It is Press 2.0's
kernel, itself descended from The Lantern Coast's, with everything specific to a word processor taken out.

What you write is a *module*: up to 8K of code that the kernel calls once a frame with the key that was typed. The kernel gives you an 80 x 30 text
screen with colour per cell, a decoded keyboard, every F18A display mode (`VMODE`), a music player, SAMS paging and a page pool, modules that switch and call each other, and disk files, plus a loader
that checks the machine, a clean power-up state and a clean exit.

```
python3 tools/newapp.py myapp --name "MY APP"      a working one-module program
python3 tools/skbuild.py myapp                     build/myapp/myapp8.bin
python3 tools/sim9900.py build/myapp/myapp8.bin --keys "<ALPHA>hello" --frames 200
```

You need Python 3 and [xdt99](https://github.com/endlos99/xdt99) (put it beside this directory, or set `XAS99` to `xas99.py`).

## Read

| | |
| --- | --- |
| [docs/PROGRAMMERS-GUIDE.md](docs/PROGRAMMERS-GUIDE.md) ([PDF](docs/PROGRAMMERS-GUIDE.pdf)) | **start here**: write an application. The PDF is built by `tools/guide_pdf.py` (pandoc, wkhtmltopdf, pypdf, reportlab) |
| [docs/ROUTINES.md](docs/ROUTINES.md) | every kernel routine: inputs, outputs, registers used (generated from the source) |
| [docs/VIDEO-MODES.md](docs/VIDEO-MODES.md) | every F18A display mode `VMODE` sets, with pictures: Text 80/40, Graphics I/II, Multicolor, enhanced colour, sprites, tile layer 2, the bitmap layer |
| [docs/MUSIC.md](docs/MUSIC.md) | music and sound: the player, the compiler (MIDI or a text score to songs), the song format |
| [docs/DEVELOPING-ON-A-TI.md](docs/DEVELOPING-ON-A-TI.md) | working with a real TI: the first-run ladder, refusal messages, debugging, editing on the TI, and what is not possible yet |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | how the kernel works inside; memory maps |
| [docs/HARDWARE.md](docs/HARDWARE.md) | the machine's facts the kernel relies on; the key-code table |
| [docs/GLYPHS.md](docs/GLYPHS.md) | the 256-glyph set |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | the rules the code follows |
| [docs/FROM-PRESS.md](docs/FROM-PRESS.md) | what came from Press, what did not, what rebasing Press would take |

## Examples

| | |
| --- | --- |
| `examples/hello` | one module, 196 bytes: prints, echoes keys, quits |
| `examples/diag` | two modules: a key/glyph/colour diagnostic, and a self-test of the kernel's services (CTRL T). Run it first on new hardware |
| `examples/modes` | one module, fifteen screens: every display mode and option (keys `1-9 0 A-E`); the pixel tests render them |
| `examples/music` | a music player: two songs from SAMS pages, pause, stop, tone effects, music stepping through a long loop |
| `examples/browser` | two modules: a DSK1 catalog browser and a text-file viewer (GOMOD with an argument, the file service, the page pool, slot B paging) |

## Tests

```
python3 tests/test_kernel.py            sources dbg boot refusal ram keys quit modules files browser modes modesquit music rom realdsr
TI_CONSOLE_ROM=/path/to/console-rom TIFDC_ROM=/path/to/disk-controller-rom python3 tests/test_kernel.py rom realdsr
```

The tests run the examples in `tools/sim9900.py`, a headless TMS9900 + F18A + SAMS + keyboard + stand-in disk simulator. With `TI_CONSOLE_ROM` set to your
own copy of the 8K console ROM (a raw dump, or an EA5 image), it runs TI's real interrupt routine; with `TIFDC_ROM` set to the 8K disk controller ROM (the two 4K EPROM images joined, low half first) the file service and the
disk browser run against TI's own DSR on a WD1771 and a disk image (`tools/tifdc.py`). The console and disk controller ROMs are TI's: they are not, and must not be, part of this repository. The one ROM that is here is the CF7+ DSR (`roms/`, see `roms/README.md`); no test uses it yet.

## Status

Version 1.2.0. All test groups pass in the simulator, including with TI's real console interrupt routine and TI's real disk controller DSR (both from your own
ROM images). **It has not been run on a real TI-99/4A.** The parts it shares with Press and The Lantern Coast have; `GOMOD`, the page pool, `FCNUM`, the
table-driven loader and the packaging are new. Run `examples/diag` and press CTRL T on the first real machine.

MIT License, (c) 2026 Rebecca Sutter.
