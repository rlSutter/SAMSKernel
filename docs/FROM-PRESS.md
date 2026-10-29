# From Press to the SAMS Kernel

History and rebasing notes, for the **[PC]** route (a program of Press's size is many modules and data pages).

The kernel is Press 2.0's resident kernel generalised: everything an application needs, nothing that only a word processor does. This note says what
moved, what was renamed, what was left in Press, and what rebasing Press (or F18Base, TXA) on the kernel would involve. **Press itself has not been
changed**; nothing here has been tried against it.

## What came over, and under what name

| Press (`src/`) | Kernel (`kernel/`) | Changes |
| --- | --- | --- |
| `defs.a99` hardware, page and kernel-RAM parts | `kdefs.a99` | Editor variables removed; application numbers come from `appcfg.a99`; slot A re-laid (below) |
| `macros.a99` | `macros.a99` | `.callmod` added |
| `loader.a99` | `loader.a99` | Table-driven (`BANKTB`) instead of one unrolled block per bank; refusal screens generated from the app name and size; clears all of slot A |
| `amsinit.a99`, `f18det.a99`, `f18a.a99`, `vdp.a99` | same names | `vdp.a99` split: primitives stay, Text 80 set-up and colour schemes go to `video.a99`; `VSBR` added |
| `pager.a99` | `pager.a99` | `MAPE`, `MAPF` (Press's `TMAPE`/`TMAPF` without the text iterator's `CLR R15`), `SETPB` |
| `vdp.a99`'s `LDSCHM` | `video.a99` | restores slot B per window with `SETPB`, not as a consecutive pair |
| `t80ini.a99` (module 3) | `video.a99` `VMODE`, `T80INI` | the boot mode is `VMODE` (any F18A mode, with options); `T80INI` = `VMODE` + the DMA test; called by the kernel before the first module; the `KIDLE` calls dropped; slot B saved and restored |
| `m3title.a99` (title screen) | (not kernel) | application-specific |
| `kernel.a99` `KSTART`/`KEXIT` | `kernel.a99` | boot module chosen by `PGBOOT`; `GOMOD` switching; `>83FC` set |
| `keys.a99` | `keys.a99` | `KINIT`, `KFLUSH`, `KWAIT` added; `KIDLE` (was in `layout.a99`) and `KPFR` (was in `tengine.a99`) moved in |
| `text.a99`, `textdbg.a99` | `text.a99` | `PUTC`, `HEX2`, `HEXD` now general; `HEX4`, `CLS`, `BOX` added |
| `layout.a99` `MODCALL` | `modules.a99` | unchanged in behaviour; `GOMOD` added |
| `tengine.a99` `PGNEW`/`PGREL` | `pool.a99` `PALLOC`/`PRELS`/`PINIT` | a general page pool (no page header clearing, no document blocks) |
| `m2files.a99` `UOPEN` `UREAD` `UWRITE` `UCLOSE` `UDEL` `UCALL` `DSRLNK` `DLGPL` `UCNUM` | `files.a99` `FOPEN` `FREAD` `FWRITE` `FCLOSE` `FDELETE` `FCALL` `DSRLNK` `DLGPL` `FCNUM` | caller supplies name and buffer (no `UNMP`/`RECBUF`); name length checked; previous error bits cleared; `>83FC` restored; result in `FERR` |
| `m0test.a99` | `examples/diag/diag.a99` | the key decoder and glyph chart screen, plus a second module of self-tests |
| `databank.a99`, `tools/font.py`, `tools/keytab.py`, `tools/sim9900.py` | same | simulator gained the real-console-ROM mode |
| `tools/build.py` | `tools/skbuild.py` | driven by `app.json`; no Press specifics |

## Variables: where they moved

| Name | Press | Kernel |
| --- | --- | --- |
| `SCHEME` | `>2200` | `>2080` |
| `TXTBUF` | `>2210` | `>2090` |
| `MODRAM` | `>2100` | `>2200` |
| `MCENT`, `MCRET` | `>237C`, `>237E` | `>20A0`, `>20A2` |
| `GPUBUF`, `NODMA` | `>2396`, `>23AC` | `>20B0`, `>20B8` |
| `POOLBM`, `FREECT` | `>2300`, `>2320` | `>20C0`, `>20E4` |
| file service state | `>3800-38FF` | `>2100-21BF` |
| stack | `>3E20-3EFF` (R10 from `>3F00`) | `>3F00-3FFF` (R10 from `>4000`) |
| the hot variables, key buffer, key codes, colour roles | | unchanged |
| patterns `PATTAB` | `>1000` | `>1800` |
| attributes `ATRTAB` | `>1800` | `>0A00` |
| GPU mailbox / program | `>2800` / `>2810` | `>0960` / `>0970` |

(The VRAM map moved in 1.1 so that every F18A mode, enhanced colour planes included, fits one layout: part 3 of VIDEO-MODES.md. Press itself still uses its own.)

## What stayed in Press

The text engine (`tengine.a99`: blocks, gap buffers, TINS/TDEL, the document model), the undo journal (`journal.a99`), layout and the iterator
(`layout.a99`: wrap, tabs, styles, `LINEOF`, `PICK`), the editor's variables (`edvars.a99`), and modules 1-9. They depend on the document model and on
Press's view state (`TADJI`, `DIRTY`, `TBASE`, the iterator's `R14`/`R15`), so they are a library to *design*, not one to relocate. If you want a general
"paged text store" the way to start is the engine's header comment and invariants (`tengine.a99` lines 1-31) with the view hooks removed.

## Rebasing Press on the kernel: what would be involved

Not done; a list of what I found, not a plan.

1. **Slot A is full in Press.** It uses `>2300-3FFF` almost entirely (block tables `>2400-27FF`, editor state `>2800-2FFF`, `IOBUF` `>3000-37FF`,
   style tables `>3A00-3DFF`, stack `>3E20`, tab stops `>3F00-3FFF`). The kernel takes `>2000-22FF` for its own and reserves `>3F00-3FFF` for the stack, so
   Press's tab stops (`DTABS`, 256 bytes) and part of its tables would have to move, probably into a SAMS page.
2. **The file service moves** from `>3800` (inside `IOBUF`'s neighbourhood and read by modules 2 and 7 through their own copies) to `>2100`. Module 7 (printing) has its own copy of the DSR call (`PCALL`); it could call `FCALL`.
3. **Module pages**: Press assigns `PGM1..9` in `defs.a99`; `app.json` would assign them and emit `PG_<NAME>`.
4. **The title screen** (module 3) sets up Text 80 itself; the kernel now does that before the first module, so the title would run in Text 80 or switch to Graphics II and back (and keep `VR1CPY` right).
5. **Press's tests** compare against `tools/model.py` through its own copy of the simulator; they would need the kernel's variable addresses.
6. **The label rule**: Press's module labels begin with a letter per module to avoid kernel clashes; the kernel's new labels (`BOX`, `CLS`, `MAPE`, ...) must not collide with any Press label.

None of these is hard, but together they are a milestone's worth of work and a full re-run of Press's hour-long test suite, so I left Press alone.

## Findings made while generalising (worth knowing even if you never rebase)

- **The stand-in disk left old error bits in the PAB flag byte.** A `CLOSE` after a read that hit end-of-file reported error 5. The kernel clears the bits before every
  call. Press's `UCALL` does not; I did not look into whether that ever matters in Press, and whether a real DSR clears the bits itself is unknown to me.
- **`LDSCHM` restored slot B as a consecutive pair** from the first page of `CURPB` (one packed word; since 1.4.0 the pager keeps `CURBE`/`CURBF`, a page each, and `GETPB`/`SETPB` save and restore both). Press maps `>F000` to unrelated pages (the header/footer page, the journal), so a
  colour-scheme change made while `>F000` held a non-neighbouring page would remap it wrongly. I did not check whether Press can reach that state; the kernel's
  version restores each window separately and cannot.
- **The console's frame counter advances by `>83FC`'s high byte.** Seen by running TI's real interrupt routine in the simulator. The console normally leaves it
  non-zero; the kernel sets it anyway.
