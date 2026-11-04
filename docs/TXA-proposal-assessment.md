# Assessment: "SAMS Kernel: contributions and requests from TXA" (1 November 2026)

Assessed against kernel **1.19.0**. TXA's document evaluated 1.16.1; several things changed since, and they are noted where they matter.
Costs are my estimates, not measurements, unless marked *measured*. "Kernel bytes" means bytes in the resident kernel image, which has
**1,002 bytes free by default** (6,678 of 7,680) and up to **4,626** when a program leaves out music, files, the pool, the graphics modes and
enhanced colour (`app.json` `"omit"`).

## Status (2 November 2026)

| Item | State | Release |
| --- | --- | --- |
| 1.1b js99er Generic Disk; 1.2 bitmap settings; 1.3 file buffers and bitmaps | recorded (docs) | 1.20.0 |
| 2.3 `.mape` / `.mapf` | done | 1.20.0 |
| 2.5 `FLOAD` / `FSAVE` (and finding 1.1's test) | done | 1.20.0 |
| 2.8 blocking-interpreter pattern; `LINEIN` to 159 characters | done | 1.20.0 |
| 2.4 4K modules, window D, `MAPD` | **done** (one design with TIthon K5: `"size": 4096` per module or `"module_size"`, header flag, `MODCALL` restores both windows) | 1.22.0 |
| common code at `>D000` (the build's help for the common-page lever) | done: `app.json` `"common"` | 1.24.0 |
| 2.1 disk start / `PRUN` | **done in the simulator** (`skbuild --disk`, the bootstrap at `>C000`, `PRUN` with `"prun": true`; tests `ea5`, `diskboot`, `prun`; real hardware not tried: checklist D1-D5) | 1.25.0 |
| 2.2 code in application RAM | **done**: `app.json` `"appram_code"` (code at `>2300`, `APPRAM` after it; also from a disk start) | 1.26.0 |
| 2.7 `.txm` as the default notation | **done**: `tools/skmusic.py` compiles `.txm` through TXA's reference compiler (`tools/txamusic.py`, vendored); the player and format unchanged; tested against the reference compiler's state at every tick | 1.27.0 |
| 2.6 picture libraries and `BMLON`; 2.7 `SFXPLAY`; 1.4, 1.5 (TXA's repository, with `src/picture.a99`, `tools/tiartist.py` and `src/wtiart.a99`, arrived 3 November 2026) | not done | |

**Two corrections to this assessment's earlier text:** the free VRAM run in Text 80 is `>2000-35FF` (5,632 bytes), so TXA's 6,144-byte bitmap cannot sit beside file calls (my first FLOAD test overwrote the file service's own PAB); and request 2.4's `GOMOD` question is settled per module by the header flag rather than for the whole program.

## In short

- Nothing in the proposal conflicts with the kernel's design rules. Most of it fills gaps the kernel already has (program files, the bitmap layer,
  shared code, one notation for music).
- **Part 1 (contributions) is cheap and mostly documentation, tests and optional includes.** I would take all of it, after TXA's code is
  reviewed for fit.
- **Part 2 splits three ways**: five requests are small (2.3, 2.5, 2.6, 2.8, and the documentation half of 2.7), two are medium and structural
  (2.2, 2.4), and two are large (2.1 disk start, and the music engine half of 2.7). **2.1 is the one TXA cannot do without**, and it is the
  biggest and the riskiest: it changes how a kernel program starts.
- Building everything as kernel code would use most of the default room. Each new routine should be **omittable** the way music, files and the
  pool now are, so a program pays only for what it uses.

## What changed since 1.16.1 that bears on the proposal

| Change | Effect on the proposal |
| --- | --- |
| `LINEIN` has a scrolling field (1.17.0) | a long line is editable in an 80-column field; 2.8's two-row field is not needed. The 79-character limit remains. |
| `"omit"`: music, files, pool, graphics, enhanced (1.18.0, 1.19.0) | the resident room is no longer "about 1K": about 2,660 bytes with files kept, up to 4,626 without. RESIDENT.md's levers 1 and 3 are built; lever 2 (common page) is not. |
| `lib/` optional includes, `examples/editor`, the sources disk | the pattern for 1.4, 1.5 and 2.6's libraries already exists. |

## Part 1: contributions

| # | Item | Value | Cost to take | Notes |
| --- | --- | --- | --- | --- |
| 1.1 | Power-up forgets open files | a test | tiny | The kernel powers each card once per program start, as TXA says. The test (open, LOAD, READ) needs `FLOAD` (2.5) to exist first. The simulator's TI controller runs the real ROM, so it already forgets open files at power-up. |
| 1.1b | TI's controller reads single-density only; js99er's "Generic Disk" reads double-density | **settles an open question** | docs | I said the 360K workbench disk works in js99er's generic controller setting as a belief; TXA reports it as tested. I will record it with that attribution. |
| 1.2 | Bitmap layer over Text 80: settings | closes "untested" in VIDEO-MODES part 10 | docs | Tested on js99er only, with its horizontal-doubling bug; no real F18A. State both. |
| 1.3 | File calls overwrite a bitmap kept in file-buffer VRAM | a rule | docs | VIDEO-MODES already warns about this for Graphics II (the colour table at `>2000-3FFF` is where the disk buffers sit). Extend the same sentence to the bitmap at `>2800`. |
| 1.4 | Packed picture format and decoder | useful to any picture-showing program | an optional include, no kernel bytes | Review `src/picture.a99` for the kernel's conventions (labels, registers, stack). |
| 1.5 | TI Artist conversion (PC tool and a 1.9K TI converter) | moderate | a tool and an include | PC tool is free; the TI side is a separate decision. |
| 1.6 | TXA music notation 1.0 and tools | see 2.7 | review | Needs reading `docs/MUSIC.md` and the compiler against the kernel's song format before deciding. |

## Part 2: requests

| # | Request | Kernel bytes | Build/test effort | Risk | Who else benefits | My view |
| --- | --- | --- | --- | --- | --- | --- |
| 2.3 | `.mape` / `.mapf` macros | **0** (each use adds code) | small | low | any program that remaps often | **Do.** I checked the numbers: a remap through `MAPE` is about 17 instructions plus the call, of which `MAPPG` is 10 (it switches the card's registers on and off around the write); an inline version that keeps `R12` set and writes the record is plausibly 10-12, so the saving is real. The macro must switch the registers on and off exactly as `MAPPG` does, or leave the records wrong. |
| 2.5 | `FLOAD` / `FSAVE` | 150-250, in `files` (omittable with it) | small to medium | low | pictures, saved games, anything stored as PROGRAM files | **Do.** Also resolves 1.1's test. The data goes to VRAM; the buffer address must stay clear of the DSR's own buffers. |
| 2.6 | Bitmap layer documented; `BMLON` / `BMLOFF`; `lib/picture.a99` | **0** (an include) | small | low | a bitmap layer is useful to any F18A program | **Do** (documentation first; the wrappers are about 30 bytes each). |
| 2.8 | A blocking-interpreter pattern; longer `LINEIN` lines | 0 to 20 | small | low | the editor-style programs | **Do.** Document "a module that never returns calls `KIDLE` at least once a frame and handles quit itself". For `LINEIN`, raise the 79 limit to about 159 (history slots become 160 bytes, 25 to a page) and rely on the scrolling field rather than a two-row field. |
| 2.2 | Code in application RAM (`"appram_code"`) | about 60-100 (a copy at start-up) | medium | medium | any big program: TXA's workbench, a database engine | **Do, but as an option of the existing `"resident"`** (`"in": "appram"`, `"size"`) rather than a second mechanism: same exports, same friendly errors, same build path. Needs `APPRAM` to become a per-application value (the way `POOLBM` did) and a refusal when the size leaves application RAM negative. It costs data RAM, up to 7K. |
| 2.4 | Modules of at most 4K and a third data window D (`MAPD`, `.mapd`) | about 60 (`MAPD`, changes to `GOMOD` and `MODCALL`) | medium | medium | programs with three tables, and the "common page" lever | **Do, opt-in.** The freed `>D000` window can be a data window (TXA) or a shared code page (RESIDENT.md's lever 2): one mechanism, two uses. The `CURCD` record already exists. Modules over 4K are refused by the build (the workbench's assembler, 5.5K, would not qualify, so it stays on 8K modules). |
| 2.7 | `SFXPLAY` (effects take voices from the song and return them); `.txm` in the build | about 150-250, in `music` (omittable with it) | medium | medium | the games | **Do after reading** TXA's notation and its voice-handover definition against the kernel's song format; the notation question (one notation for all the projects) is a decision for you before it is an engineering one. |
| 2.1 | A disk start, `skbuild --disk`, `PRUN` | the loader gets a file reader (about 400-600 bytes, in the cartridge bank, which has 6K free); `PRUN` about 200-300, omittable | **large** | **high** | anyone without a FinalGROM; any program that launches another | **The one TXA cannot do without; also the biggest piece of work in the list.** It changes how a program starts: an E/A option 5 loader file, the loader loading 4K PROGRAM files into SAMS pages (the loader today only copies banks), a launch block, and `PRUN` replacing the running kernel (it must run from scratchpad, as the bank copier does). Design it as its own project, with TXA's `src/disk.a99` as the starting code. It cannot be fully tested in the simulator without modelling E/A 5; it needs real hardware. |

## Decisions for you

1. **Is a disk-started kernel in scope?** 2.1 is a strategy question as much as a feature: it opens the kernel to machines without a FinalGROM,
   and it is what TXA's end product (games as disk files) needs. Everything else in Part 2 is incremental; this is not.
2. **One music notation or two?** Accepting `.txm` makes TXA's notation the build input for the kernel's songs too. That is a good outcome only
   if it can express what the kernel's songs already do.
3. **Whose code, and under what licence?** The contributions are TXA's source (`picture.a99`, `wtiart.a99`, the Python tools). They are yours, but
   the kernel's tree is MIT and each file taken in should say so.

## A suggested order

1. Documentation and tests that need no design: 1.1b, 1.2, 1.3, 2.6's text, 2.8's section. (A day.)
2. `.mape`/`.mapf` (2.3); `FLOAD`/`FSAVE` and the power-up test (2.5, 1.1); the `LINEIN` limit (2.8). (Small, each with a test.)
3. `"resident"` in application RAM (2.2); then the 4K-module window (2.4). (Medium, structural.)
4. The picture libraries (1.4, 1.5, 2.6) and the bitmap wrappers.
5. `SFXPLAY` and `.txm` (2.7), once the notation decision is made.
6. The disk start (2.1) as a designed project, last, because it touches the loader and needs hardware.

## What I could not check

- I have not read TXA's repository, only this document. Every size and cost above is my estimate from the kernel's own sources.
- TXA's "23 to about 10 instructions" figure I could confirm only as plausible (see 2.3), not measure.
- Nothing in either side's list has run on a real TI, F18A or SAMS card; TXA says the same of Part 1.
- 1.2's register values are as TXA reports for js99er; I have not run them.

*Release 1.28.0 (4 November 2026): nothing in this table changed; see `CHANGES.md` for what was added since (the workbench manual, the rationale document, Press's `DSRLNK` fix and expression checker).*
