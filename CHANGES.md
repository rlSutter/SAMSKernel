# Changes

## 1.25.0 (3 November 2026)

- **The disk start** (docs/DISKSTART.md; the owner decided it is in scope on 2 November 2026): a kernel application can be a disk. `skbuild.py APP --disk [--geometry sssd|dsdd]` writes `OUT/NAME.dsk`: the **bootstrap** `NAME`, an Editor/Assembler option 5 image for `>C000` (the cartridge loader assembled with `-D DISKBOOT`, about 4.3K), and every bank after bank 0 as an 8K PROGRAM file `NAME/Bnn`. The bootstrap does the cartridge loader's checks and refusal screens, then reads each bank with the kernel's own file service (`files.a99`, `FLOAD`) into VRAM and from there to `>A000` or its SAMS page pair, and starts the kernel; it tries `DSK1.` to `DSK3.` for the files unless handed a device. New: `kernel/dskboot.a99`, the `DISKBOOT` conditionals in `loader.a99` (the cartridge build is unchanged: the kernel is still 6,894 bytes), `app.json` `"disk_name"`.
- **`PRUN`** (`"prun": true`, 206 bytes of kernel, off by default): R2 = a path such as `DSK2.GAME`; loads that program's bootstrap into VRAM with `FLOAD`, leaves a handoff block (`>8320-833F`: `>A55A`, the device prefix's length and characters, `>5AA5`), maps the identity pages `>0C-0D`, copies the bootstrap to `>C000` and jumps; the bootstrap takes the device from the block and loads its own banks. If the file is missing or is not a one-file image for `>C000` it returns R0 = the error (7, `>FF`, or `>FE`) and the program goes on. A program that uses `PRUN` without the flag is refused by name; the flag with `"files"` left out is refused.
- **Tools:** `skdisk.make_disk(..., programs=[(name, bytes)])` writes PROGRAM files; `tifdc.read_program` reads them back (8K, 100-byte and 512-byte files on both geometries); `tools/ea5.py` is an Editor/Assembler option 5 loader for the simulator (a chain of files, the next name being the last character incremented, as `xas99 -i` writes them).
- **Test groups:** `ea5` (the loader on a one-file image, a two-file chain, a missing file); `diskboot` (the build, the files, hello booting from the disk through TI's real controller ROM, the refusal screen for a disk without the banks, and the same bootstrap through the CorComp, Myarc DDCC-1 and Myarc HFDC cards with a double-density disk); `prun` (two programs on one disk: G chains from ALPHA to BETA, X on a missing program returns error 7 and keeps running, the refusals). **None of this has run on a real TI**: `docs/HARDWARE-CHECKLIST.md` has steps D1-D5.
- **Decisions recorded** (`docs/ROADMAP.md`): the ROM files in `roms/` stay; code taken in from TXA and TIthon is MIT; the default music notation will be TXA's `.txm` (not built: it needs TXA's specification and compiler, `docs/MUSIC.md`).

## 1.24.0 (2 November 2026)

- **A cycle model for the simulator: `tools/cycles.py`** (K6 of the TIthon proposal). `CycleCPU` replaces `sim9900.CPU` and adds clock cycles of the 3 MHz TMS9900: the data manual's cycles per instruction and addressing mode, plus **8 wait cycles for every access outside the console ROM and the scratchpad** (the 8-bit expansion bus), counting the instruction fetches, the workspace registers, the address words and the operands. It only measures: the simulator's frames and interrupts still follow the instruction count. Test group `cycles`: ten instructions against the manual's numbers, and the classic `DEC R2 / JNE` loop counting 65,535 at 0.437 s in the scratchpad and 0.786 s in expansion RAM (known from real machines: about 0.44 s and 0.79 s). Not verified against a real console beyond those; leaves out the video and sound chips' delays, the interrupt context switch and `DIV`'s variable time. Use it for ratios.
- **Common code at `>D000`: `app.json` `"common"`** (the build's help for RESIDENT.md's lever 2). `{"source": "common.a99", "exports": [...]}`: code shared by every module, assembled at `>D000` first, refused if over 4K, given its own page (`PG_COMMON`; the equate `COMMONPG` is 0 when there is none), exports written to `common.equ`; the kernel maps it into `>D000` at start-up (6 more bytes of kernel: 6,894). Every module must be `"size": 4096` (an 8K module beside it is refused by name). Test group `common`: two modules call the common code after a boot, a `GOMOD` and a `MODCALL`, `>D000` stays on the common page throughout; refusals for an 8K module, a common image over 4K, and an export the source does not define. The build now assembles modules in an order of its own (the common code first) and still lays the banks out in module-list order.
- **`lib/float.a99`: `XCFI` (`XML` `>12`, float to integer) verified**: rounds to the nearest integer, halves up (2.5 gives 3, -2.5 gives -2), leaves it in FAC's first word, sets the error byte `>8354` to 3 outside -32768..32767; 18 values and 4 overflows in test group `float`. The rest of the second table is the GPL interpreter's: `>13`, `>16-1A`, `>1C` and `>1D` never return outside it (found by running them: the simulator loops), the others do little; the file and the guide say not to call them.
- **Documentation:** the guide's memory map no longer says the kernel is "3.6K of 8K used" (6.9K of the 7.5K it may use) and chapter 15's heading no longer says "version 1.6".

## 1.23.1 (2 November 2026)

- **`FPCALL` loads the GPL port registers** (R13 = `>9800`, R15 = `>8C02`, as the console's start-up does; 8 more bytes, 90 in all). The stack forms of the float routines read the VRAM through R15, and the simulator's boot, like any cartridge started without the title screen, leaves it zero, so they read nothing.
- **The stack forms are verified** (`XSADD` `>0B` to `XSCOMP` `>0F`, equates and `FPSTK` for the pointer at `>836E`): the second number is the one at the top of the console's VRAM value stack, and the pointer drops by 8. 120 random stack operations match Python to 2.6e-13; `SCOMP` gives the same result bits as `FCOMP`. The pointer's low byte, `>836F`, joins the bytes the float package changes (still inside the reserved `>834A-836F`).
- **More of the console's scratchpad reserved.** The float package also uses `>8375` (the sign of FAC), `>8376` (a copy of its exponent), `>8377` and the GPL status byte `>837C`; the static layout test (`fplayout`) now forbids kernel names there too, and `kdefs.a99` and the architecture notes say so. (The kernel had nothing there.)
- **`ROUND` (`XML` `>02`) reads its digit count from `>8354`**, as the console code at `>0FB2` shows (`MOVB @>8354,R1`) and a run confirms: with the count at `>835C`, which one source gives, nothing changes. Not covered by the test: it expects the state the BASIC interpreter leaves around it (the sign and a copy of the exponent), so a plain call is not a "round to n places".
- **A note on the documentation:** one page of Nouspikel's tech pages (`reals.htm`) gives `FDIV` as FAC / ARG; the console's code, run in the simulator, computes ARG / FAC (the subtraction is ARG - FAC on both). The file and the guide say so. The page's other facts agree with what was measured: the XML tables (master table `>0CFA`, table 0 at `>0D1A`, `FADD` `>0D80`, `FSUB` `>0D7C`, `FMUL` `>0E88`, `FDIV` `>0FF4`, `FCOMP` `>0D3A`, the stack forms), FAC at `>834A`, ARG at `>835C`, the sign byte at `>8375`, the error code at `>8354`, and the value stack pointer at `>836E`. (The page `roms.htm` itself is not fetchable from here; the table was read from a search result of it and from the console ROM.) Still not covered: the second table's conversions.

## 1.23.0 (2 November 2026)

- **`lib/float.a99`: `FPCALL`, a call to the console ROM's floating-point routines** (an optional include, 82 bytes; TIthon's spike B). `R0` = the XML code; the routine's address is read through the console's tables (table of tables at `>0CFA`; tables 0 at `>0D1A` and 1 at `>12A0` are the console's, any other is refused), then run in the GPL workspace (`LWPI >83E0`, `R11` set to come back; the routines return through `R11` or `R10`, a copy of it, and finish at `>0FAA`, which stores the status byte at `>837C`). The simulator needs no `XML` instruction: they are ordinary subroutines of the console ROM, and `XML` is a GPL opcode that the TMS9900 does not have, so the "XML in the simulator" part of TIthon's K6 is not needed. Equates `XFADD` `XFSUB` `XFMUL` `XFDIV` `XFCOMP` and the addresses of `FAC`, `ARG` and the status byte. The numbers' format, the operations' operand order (`FSUB` is ARG - FAC and `FDIV` ARG / FAC) and the compare result (status mask `>60`: `>20` equal, `>40` FAC less than ARG, 0 greater; the `>80` bit follows the raw bytes and is not for numbers) are documented in the file and in the guide.
- **K1's dynamic test, done.** Test group `float` (needs `TI_CONSOLE_ROM`) runs the console's real routines through `FPCALL` in the simulator: 240 random operations on both signs and a wide range of exponents match Python to a relative error of 3.8e-13, FCOMP is right on 120 pairs of either sign, R4-R10 and R12-R15 of the caller come back unchanged, a code in a table that is not the console's or an empty entry gives `>FFFF`, and **every scratchpad byte the routines change below the GPL workspace** (`>834A-8353`, `>8356-8359`, `>835C-8361`, `>8365-8369`, `>8375`, `>8377`, `>837C`) **is outside the kernel's variables**. The measurement widened the reserved area: the float package works in `>834A-836F`, not only in FAC and ARG, so the static layout test (`fplayout`) and `kdefs.a99` and `docs/ARCHITECTURE.md` now reserve all of `>834A-836F` (the kernel had nothing there).
- Not covered: the `S` entries (`>0B-0F`) and the second table's conversions (numbers to and from strings and integers): reachable through `FPCALL`, not verified.

## 1.22.0 (2 November 2026)

K5 of the TIthon proposal and request 2.4 of the TXA proposal, as one design (`TIthon-proposal-assessment.md`, `TXA-proposal-assessment.md`). Kernel 6,888 bytes (+46), 792 free.

- **Single-page modules.** A module of at most 4K declares `"size": 4096` (or the application `"module_size": 4096`; a module's own `"size"` wins). The build refuses one that assembles to more than 4,096 bytes and sets bit 0 of the last word of its header (`>C006`); `PAGEC` reads it and, for such a module, maps only `>C000` and **leaves `>D000` as the program had it**. A module of the default size is as before (its second page at `>D000`), so nothing existing changes. The image still occupies an 8K bank and two SAMS pages.
- **`MAPD`** (public; R0 = a page; unless it is there already; recorded in `CURCD`) and **`.mapd Rn`** (inline, the rules of `.mape`): window `>D000` for the program. `KSTART` maps page `>0D` there so that `CURCD` is true from the start.
- **`MODCALL` saves and restores both windows** `>C000` and `>D000` separately (it restored the first page of the pair, through `PAGEC`, before), so a callee of either size, and TIthon's native calls from a 4K VM core into 8K modules, leave the window as the caller had it. `GOMOD` does not restore it: a switch to a single-page module leaves it, a switch to an 8K module overwrites it, and a return to a single-page module does not put the old page back (the program maps its own).
- Settles the one point on which the two proposals differed: TIthon would have `GOMOD` map the new module's pair; TXA only `>C000`. Both are right for their module sizes, decided per module by the header flag.
- Test group `slotd`: the flag in the image (set in the two 4K modules, clear in the 8K one); a single-page boot module's `MAPD` stays; `GOMOD` between single-page modules leaves `>D000`; to an 8K module maps its second page; back does not restore; `MODCALL` into each size restores both windows (also after a trip through the 8K module); `.mapd` against `MAPD` over 600 pseudo-random pages; the build refuses a 4K module that is larger, a default that does not fit, a bad size. The existing `modules` group passes unchanged.
- RESIDENT.md's lever 2 (a common page): the mechanism now exists; the build's help in placing shared code at `>D000` does not.

## 1.21.0 (2 November 2026)

From the TIthon project's proposal (K1 to K4; `TIthon-proposal-assessment.md`). Kernel 6,842 bytes (+104), 838 free.

- **K1. Float-safe scratchpad.** The console's floating-point routines keep FAC at `>834A-8351` and ARG at `>835C-8363`, and until now `F18VER`, `NPAGES`, `QUITF` and `VDPPIC` lay in FAC: any program that called a float routine corrupted the page count the pool depends on, could set `QUITF` and quit, and lost the PICO9918 flag. `F18VER`, `NPAGES` and `QUITF` are now `HOT+2`, `+4`, `+6` (`>8342`, `>8344`, `>8346`; `F18FLG` stays at `>8348`, below FAC); `VDPPIC` is the slot A word `>20AA` (the loader's detection runs after it has cleared slot A). Programs and `KERNEL/EQU` files built before this release must be rebuilt (every source names the variables by label; the workbench disks carry the matching `KERNEL/EQU`); the two tests that read the addresses directly were updated. **Test `fplayout` checks the layout statically** (no kernel name in FAC or ARG; no two names at one slot A word); the dynamic check (floats through the real console ROM, every other scratchpad byte unchanged) needs the simulator to dispatch the GPL `XML` call and a float-call include for programs, neither of which exists yet. FAC and ARG are from the console ROM's documented layout, so that check may find more.
- **K2. The frame hook.** `FRMHK` (`>20DA`) holds 0 or the address of a routine; `KFRAME` replaces the four places that stepped the song (the main loop, `KIDLE`, `KPFR`, `KWAIT`): it calls `MUTICK`, then the hook, unless `FRMGD` (`>20DC`) says the hook is running, so a hook that calls `KIDLE` cannot recurse. The hook may change `R0-R8` and `R12`, must keep `R9-R11` and the stack, and must be resident. Test `framehook`: a long loop that calls only `KIDLE` runs the hook once per frame that passed; none when none is set; a hook that runs past a frame and calls `KIDLE` is not re-entered; file calls reach it.
- **K3. The break flag.** `BRKF` (`>20DE`) is set by `KPUT` when the code is `KCLEAR` (FCTN 4, `>F4`), before the full-buffer test; the code is still buffered when there is room. (TIthon proposed a new `KBREAK` equate; `KCLEAR` already is that code.) Test `brkflag`: an ordinary key leaves it clear; FCTN 4 with room sets it and is buffered; with a full buffer (63 keys) the code is dropped but the flag is set; a real FCTN 4 press through the keyboard decoder sets it.
- **K4. A faster pool and `PALLOCA`.** `PALLOC` and the new `PALLOCA` (R0 = the first page to consider; below the pool's first page is taken as the first; at or above its end, 0) skip a bitmap byte with no free page in five instructions: at 3,900 of 4,096 pages in use an allocation costs 2,589 instructions, not about 107,000 (measured). `PALLOC` is `PALLOCA` from the pool's first page (about 40 bytes more in all; both leave with `"pool"` in `"omit"`). Results are unchanged: the lowest free page. Test `poolscan`: 500 random allocate / `PALLOCA` / release steps in each of three pool shapes agree with a plain model; the cost; `PALLOCA` at the pool's edges and under `pool_max_pages`. TIthon's optional hint word was not added (the byte skip is enough).
- **Not done from the TIthon proposal:** K5 (`MAPD` and a two-halves `MODCALL`, to be designed with TXA's 4K-module request), K6 (the simulator's cycle model and `XML`), and the float-call include the assessment recommends.
- Room figures updated: the default free room is about 840 bytes (the kernel is 6,842); all five `"omit"` words give a 3,622-byte kernel with 4,570 free. The resident and pool-size tests were resized to match.

## 1.20.0 (1 November 2026)

From the TXA project's proposal (`TXA-proposal-assessment.md`): the items that needed no design decision.

- **`FLOAD` and `FSAVE`** (in `files`, 60 bytes): the DSR's LOAD and SAVE (opcodes 5 and 6) on the selected handle's PAB: `R2` the name, `R0` the VRAM address, `R1` the most bytes or the count; `R0` = 0 or the error (a missing file: 7; a name too long for the PAB: `>FF`). Tested through TI's real controller ROM: 4,096 and 5,632 bytes saved and loaded back byte for byte; and **finding 1.1 of the proposal** checked: a record file open on one handle is still readable after a LOAD and a SAVE on another (the kernel never reruns a power-up while files are open). The data goes straight to VRAM, so the address must avoid the screen's tables, the file service's own buffer and PAB (`>3600-37D7`) and the controller's buffers: **the free run in Text 80 is `>2000-35FF`, 5,632 bytes**. (My first test loaded 6,103 bytes and overwrote the file service's own PAB: a 6K picture does not fit beside file calls, which is why TXA redraws its bitmap after each disk call.)
- **`.mape Rn` and `.mapf Rn`** (macros): `MAPE` and `MAPF` inline, about 10 instructions when the page changes and 2 when it does not, against about 17 plus the call; no kernel bytes. They switch the mapper's registers on and off as `MAPPG` does and keep `CURBE` and `CURBF` true. `R12` is loaded and left. Test group `fastmap`: 2,000 pseudo-random page reads through each macro and through the call agree, the records follow, `GETPB` and `SETPB` round-trip, and a page already mapped writes nothing.
- **`LINEIN` takes lines up to 159 characters** (it was 79). A history page's slot size is chosen when the page is first set up: 80 bytes (50 lines of up to 79 characters) if that call allowed up to 79, else 160 (24 lines of up to 159); a later call that allows more than the page holds is cut to what it holds. Page layout in `lib/linein.a99`; the include grows by 84 bytes (1,100 in a module). The scrolling field of 1.17.0 already handles long lines in a narrow field, so no two-row field.
- **Documentation:** VIDEO-MODES part 10 now has TXA's working settings for the bitmap layer over Text 80 (js99er only, with its horizontal doubling) and the rule that a bitmap must keep out of every file buffer, with the real numbers; the guide has "A module that never returns (an interpreter)" and "Mapping fast"; the hardware checklist records TXA's report that js99er's Generic Disk reads double-density images (which supports the 360K disks).
- Test groups `fastmap`, `fileprog`; `linein` extended (long lines, the clamp, 24-line pages).
- Not done from the proposal: the disk start and `PRUN`, code in application RAM, the 4K-module window, the picture libraries, effects and `.txm`. See the assessment.

## 1.19.0 (1 November 2026)

- **A text-only `VMODE`: two more `"omit"` words.** `"graphics"` leaves Graphics I, Graphics II and Multicolor out of the kernel (308 bytes: their rows of `MODTAB`, `VR1TAB` and `COLTAB`, the Graphics II name table and sprite table, the tables `VT2` and `VT3`, Graphics I's colour table, and the branches in `VMODE`); `"enhanced"` leaves out enhanced colour and sprites (164 bytes: the enhanced-colour and sprite bits of VR49-VR51 and VR1, the extra pattern planes, the enhanced attribute fill and the palette entry that makes attribute 0 the text colour). The build defines `NOGRAPHICS` and `NOENHANCED`; `video.a99` skips the code with `.ifdef`. Both: 472 bytes, and a kernel whose `VMODE` sets Text 80 and Text 40, 24 or 30 rows, with or without position attributes, as before. All five words (`music`, `files`, `pool`, `graphics`, `enhanced`): a 3,566-byte kernel with 4,626 bytes free in its 8K (the default has about 1,000). A module that names `VMGM1`, `VMGM2`, `VMMC`, `VOTE1-3`, `VOSE1-3`, `VOSPR`, `VOS16` or `VOSMG` with the word that removes it is refused by name; a mode number worked out at run time cannot be checked, and a trimmed kernel asked for a mode it lacks does undefined things. Applications without the words build exactly as before (6,678 bytes). Found by prototyping the cut in a scratch copy first (`text-only-vmode-prototype.patch`).
- Test group `textonly`: each combination boots in Text 80 and echoes keys, sets Text 40, Text 80 in 24 and 30 rows and position attributes with the right geometry, and what was kept still works (Graphics II without `"enhanced"`, enhanced-colour text without `"graphics"`); the refusals.

## 1.18.0 (31 October 2026)

- **The trimmed kernel: `app.json` `"omit"`** (a list of any of `"music"`, `"files"`, `"pool"`). The build defines `NOMUSIC`, `NOFILES` and `NOPOOL` for the kernel's assembly (xas99's `-D`) and `kernel.a99` leaves the part out with `.ifdef`: the **music** engine (506 bytes; `MUTICK`, which three places in the key and module loops call, becomes a bare return), the **files** code (the DSR calls and the file routines, `CLKGET`: 1,962 bytes), the **page pool** (172 bytes, and, with no bitmap, its 512 bytes of room: the kernel limit is then 8,192 bytes instead of 7,680). All three: the kernel is 4,038 bytes instead of 6,678, with 4,154 bytes free in its 8K instead of about 1,000. The rest of the kernel does not call into any of the three (checked), so each can go alone; a module, the resident code or a file they `COPY` that uses a routine that was left out is refused by name with the word that removes it (`hello uses FOPEN, which this kernel does not have: app.json leaves "files" out of it`); an unknown word is refused; `"omit": ["pool"]` together with `"pool_max_pages"` is refused. The F18A modes are not omittable: the boot screen is set by `VMODE`, which carries all five modes. Applications without `"omit"` build exactly as before.
- Test group `trim`: each part left out and the application still running (sizes 506, 1,962, 172 and 2,640 smaller), the build's report, the refusals, and resident code that does not fit beside a pool bitmap fitting without one (8,054 bytes).

## 1.17.0 (31 October 2026)

- **`examples/editor`: the workbench's editor as a program of its own.** A small front module (`front.a99`, about 1,500 bytes with `LINEIN`) asks for a file name with `LINEIN` (with a history of the names typed, kept in the page `PGFREE`, which is below the editor's pool) and hands over to `examples/workbench/ed.a99`, used unchanged: the front module is named `wb`, so the editor's `GOMOD PG_WB` for CTRL X and CTRL A returns to the prompt, and the file name is shared in `SRCNAME` as it is under the shell. Build with `python3 tools/skbuild.py examples/editor`. CTRL S saves, CTRL X returns to the prompt (twice with unsaved changes), FCTN = quits; a bare device name is refused. Test group `editorapp` (a name opens an empty buffer, typing and CTRL S write the file to the disk, CTRL X returns with the name kept, the bare device is refused).
- **`tools/mksources.py`: a 360K disk of the kernel's sources to read and edit on the TI** (`SOURCES`: kernel, `lib/`, the generated `FONT/A99` and `KEYTAB/A99`, hello and the editor's front module, and a `SRCNOTES` file; 930 of 1,440 sectors). Four file names are too long for a TI disk as `NAME/A99` (`amsinit`, `databank`, `modules` and the build's `kresident`): they are stored as `AMSINI`, `DATABK`, `MODULE` and `KRES`, with the `COPY` lines that name them changed in the disk's copies only. The kernel cannot be assembled on the TI from it yet (the per-application `appcfg`, `appname` and `appmsg` are not on it, and the assembler's limits stand in the way: `SRCNOTES` says so). Test group `sourcesdisk`.
- **`tools/jumpcheck.py`**: lists the jumps in an assembler listing that have few words to spare (a TMS9900 jump reaches 128 words back and 127 forward; code added between a jump and its target pushes it out, and the assembler's error shows up in the file holding the jump, far from the change). The kernel has 241 jumps; the tightest has 6 words to spare (`JEQ VT3` in `video.a99`, the one that broke when code was inserted ahead of it earlier). Test group `jumpcheck`.
- **`LINEIN`: a scrolling field.** The high byte of `R3` is the field's width in cells (2 or more): a longer line scrolls sideways and the field always shows the cursor (`LI R3,20*256+60`: a line of up to 60 in a field of 20). A width of 0, 1, or the longest line + 1 or more is the plain field as before, so existing callers are unchanged. The include grows by 86 bytes (1,016 in a module). **A consequence for resident code:** as resident code `LINEIN` is now about 1,050 bytes, which no longer fits the default room (about 1,000 bytes: the kernel is 6,678), so the resident test application now declares `"pool_max_pages": 1024`; a program that wants the editor resident does the same, or `COPY`s it into its modules. (Earlier notes said the line editor fits the default room; it did until it gained this field.)
- **A mistake of mine in 1.16.1, now fixed: its `README.md` was empty.** A one-line edit of the version number truncated the file before reading it, and the release was packaged that way. 1.16.1's zip, tar.gz and bundle carry an empty README; this release restores it from 1.16.0's with the new entries. Nothing else was affected (every tracked file was checked).

## 1.16.1 (31 October 2026)

- **The kernel no longer runs a TIPI's power-up routine** (`DSRPWR`). Found by reading the real TIPI DSR ROM (js99er's copy of it, 2025): at `>1000` and `>1200` its power-up does nothing but pulse CRU bit 1, the Pi's RESET line, and return; only at `>1100` (standing in for the disk controller) does it make buffers. The console has already done that at start-up, so running it again at the program's first file call gained nothing and made the Pi drop its session: js99er's TIPI emulation closes its websocket on a RESET and holds the CPU until it reconnects. A TIPI is recognised by its first device name (`TIPI`), and one at `>1100` is still powered. Since 1.6.0 the kernel had powered every card on the belief that a TIPI needed it; that rested on a model of a TIPI, not its ROM. The TI controller (and CorComp, Myarc, HFDC, CF7+) are powered as before. The kernel grows by 42 bytes (6,678).
- The simulator's TIPI model now lists `TIPI` as its first device, as the real card does; the `tipi` test expects it not to be powered.
- **Not shown to fix a freeze reported in js99er** (the workbench stays frozen after being chosen from the menu with TIPI emulation on): the workbench makes no file call and touches no card at start-up (checked in the simulator), so that freeze is probably elsewhere; js99er's TIPI setting (`Mouse` at `>1200` without a websocket, or `Full` at `>1000` with one) and whether `hello8.bin` freezes the same way are not known yet.
- **Open:** the real TIPI DSR also claims the names `DSK0`-`DSK9` and `DSK`, ahead of a disk controller at a higher CRU address, and asks the Pi about them: with TIPI emulation on but no Pi (no websocket proxy) behind it, any `DSKn` access waits for a reply that never comes, in any program.

## 1.16.0 (31 October 2026)

- **`app.json` `"pool_max_pages"`** (a multiple of 64 from 64 to 4096; default 4096): the most pages the program's pool will ever manage. The pool's bitmap, 512 bytes for a 16M card, is now pages/8 bytes **at the top of the kernel's pages** (`POOLBM`, `POOLMX`, `POOLWD` are written into `appcfg.a99` by the build; `POOLBM` is no longer in `kdefs.a99`), so a program that pools at most 256 pages (a 1M card) leaves the kernel and its resident code 480 bytes more room: the kernel may be 7,680 bytes by default, 8,160 with 256 pages, 8,064 with 1,024. `PINIT` cuts its range to the limit (no page from there up is handed out; `PRELS` ignores one) and clears only the smaller bitmap; the build refuses a value that is not a multiple of 64, is out of range, or is at or below the first free page (the pool would be empty). The cost is that default kernels grow by 10 bytes for the clamp (6,636 bytes). The kernel's size line and error now name the bitmap's real address.
- New test group `poolmax` (a kernel with 500 more resident bytes fits only with the smaller bitmap; PINIT cut to 256 pages; nothing written below the bitmap; exactly 224 pages handed out; out-of-range PRELS ignored; the refusals).
- **The "key delivery" question, answered: there is no bug.** In 1.15.0's resident test, real key presses seemed never to reach `LINEIN` in module B. They did: the test module set `QUITF` after `LINEIN` returned, the quit restarts the machine, the start-up clears slot A, and the results the test then read were zeros. (An earlier run also ended before its keys were due.) Keys reach `KWAIT` and `LINEIN` in `INIT` of a second module, with or without resident code, in the simulator (bisected over single module, two modules, resident, and each module's calls). The test module now stays up and the `resident` test uses real key presses; the guide's testing part and the skill say that a quitting test application loses its results.

## 1.15.0 (31 October 2026)

- **Resident code for multi-module programs** (`app.json` `"resident": {"source", "exports"}`; `docs/RESIDENT.md`): a source file assembled INTO THE KERNEL's pages (after the kernel, in the same assembly), so every module reaches its exported routines with a plain `BL` and the routines run with the caller's module still mapped: they can read the caller's tables and call back into the caller's code, which `MODCALL` cannot. The listed labels join `kernel.equ`; the rest of the resident code is private. The resident source may `COPY` the optional includes in `lib/` (the line editor once for the whole program), the application's own files, and the kernel's. `skbuild` reports how much of the kernel is resident and now checks the kernel against the pool bitmap (`>BE00`: at most 7,680 bytes) before the generic 8K check, naming the resident part; it refuses a resident source that is missing, an export that is not a name, and an export that is not a label. An application without `"resident"` builds byte for byte as before (the kernel is 6,626 bytes, about 1,050 free). The levers for more room (a smaller pool bitmap by declaring the most pages pooled, a common page, trimming the kernel) are described in `docs/RESIDENT.md`, not built. `[PC]` only.
- Test group `resident` and `tests/apps/resident`: two modules, each calling the resident `RSUM` on a table in its own code and `RCALL` with a callback in its own code, and reading a line with the one resident `LINEIN`; the exports and nothing else reach the modules; the refusals.
- The build's kernel line now says "free below the page-pool bitmap at >BE00" (it said the free part of the 8K bank).

## 1.14.0 (31 October 2026)

- **`LINEIN`, a line editor, as an optional include** (`lib/linein.a99`, about 900 bytes; `COPY "linein.a99"` after a module's code): one call reads a line of up to 79 characters at a screen position, edited in place in the program's buffer. Typing (insert, or overtype with INS), left and right arrows, BEGIN and PROC'D (start and end), DEL, CTRL H, ERASE; ENTER, BACK and QUIT end it and are returned. The cursor is the cell in the text's colours swapped. With a **history page** from the pool the up and down arrows recall earlier lines (a ring of 50; ENTER stores a non-empty line that is not a repeat of the one before; going down past the newest brings back the line as typed); the page is mapped into `>F000` only while it is read or written and slot B is put back as it was. It uses about 60 bytes of the stack and `R0-R8`, `R12`; `R9` is kept. It is an include, not kernel code, so the kernel stays at 6,626 of its 7,680 bytes (about 1,050 free, for the resident-code design); the cost is that each module that prompts carries its own copy. Every label in it begins `LN`. The build finds it in `lib/` (`skbuild` adds it to a module's include path, `lint80` and `docindex` cover it); on the TI the disk must hold `LINEIN/A99` beside the program.
- **`programs/ask.a99`**, the example on the workbench's disks: asks a name with `LINEIN` and a history and greets it; the disks now carry `LINEIN/A99` as well.
- **FEXCAT's stack guard.** Its frame (192 bytes since the HFDC change) is most of the 256-byte software stack: it now answers `>FF` ("cannot be read") instead of running off the bottom of the stack when the code calling it has already used more than 36 bytes. `FEXIST` asks STATUS first, which needs no frame, and falls back to `FEXCAT` only for a device that does not answer it.
- Tests: new group `linein` (typing and every key, the limits, the screen, ENTER and BACK, the history, the ring of 50, slot B, R9 and the stack; through a module that carries the include, `tests/apps/linein`), and `ask` in `tiprograms` (assembled on the simulated TI with `LINEIN/A99` read from the disk, and run).
- Not done: LINEIN on a real TI; a horizontally scrolling field (the field must fit on its row).

## 1.13.0 (31 October 2026)

- **The Myarc HFDC's floppy side in the simulator** (`tools/hfdc.py`), on its real 16K ROM: the card (four 4K ROM pages, 32K RAM in 1K pages, the CRU latch and its bit order, the chip's ports) from MAME's description, and an HDC9234 at sector level (a command stream with a register file and DMA into the card's RAM, density from the clock-divider bits) from Myarc's own DSR source, which you supplied. 360K double-density disks open, read, write and catalogue through it, including files on the second side. Hard disks and formatting are not modelled.
- **Catalogs on the HFDC, and a fix for everyone**: the HFDC refuses an explicit record length of 38 for a catalog open and writes up to 146 bytes per record. `FCATOP`, `FEXCAT`, the disk browser and the workbench shell now open catalogs with length 0 (the DSR's own: 38 on the other cards), and the record buffers are big enough: `FCATOP`'s buffer is documented as 150 bytes or more, `FEXCAT`'s stack frame is 192 bytes, the browser's record buffer 160, and the workbench shell's catalog buffer moved to the assembler's idle line area (`APPRAM+256`; it would have overrun the editor's variables on an HFDC).
- New test group `hfdccru` (LDCR bit order for the paging bits); `fileapi`, `dsdd` and `dsddworkbench` now run on the HFDC as well (the file API tests on four cards, the others on three); `TESTCARDS=HFDC` (or a comma list of words from the card names) runs a group on just those. The test harness allows 300 million instructions per call (the HFDC DSR is slow).
- Both Myarc cards answer 7 for a missing file opened for input (TI's controller and the CorComp answer 2).

## 1.12.0 (31 October 2026)

- **`images/workbench-360k.dsk`**: the workbench's disk as a 360K double-sided double-density disk: `KERNEL/EQU`, `SRC`, every program (the two 90K disks' contents together) and the sources of the workbench itself (`WB/A99`, `ED/A99`, `ASM/A99`) to read on the TI: 855 of 1,440 sectors used. For the CorComp and Myarc cards, a TIPI or CF7+, or js99er's generic disk controller; TI's own single-density controller cannot read it, so the 90K `workbench.dsk` and `examples.dsk` stay. New test group `dsddworkbench`: through each double-density card's real DSR, the catalog lists the disk's files and `HELLO/A99` assembles on the simulated TI, identical to xas99.
- **The Myarc HFDC is still not modelled.** Its DSR ROM is in `roms/`, but its controller chip (not a WD177x) and its card RAM and paging need a hardware description that I do not have: see the status note in `roms/README.md`.

## 1.11.0 (31 October 2026)

- **The Myarc DDCC-1 in the simulator** (`tools/myfdc.py`), on its real ROM: two 4K ROM banks at `>4000`, 2K RAM at `>5000-57FF`, the WD177x at the odd addresses `>5F01-5F07`, the CRU latch (card enable, reset, side, bank and density, drive select) and the INTRQ / DRQ inputs. Built from the hardware description in MAME's source for the card (supplied by the project owner; the model is written from that description). A 360K double-density disk opens, reads, writes and catalogues through it.
- **The chip now answers 'record not found' for the wrong density** (`fdc.py`: the disk's density is read from its volume block; a card that has a density line is asked). The Myarc DSR tries single density first and finds a double-density disk this way.
- **Simulator bug fixed**: `B Rn` (branch to a register) went to the register's contents instead of the register's own address, so code running in the workspace registers (the Myarc DSR's bank trampoline) derailed.
- `fileapi` now runs on three cards (TI 90K, CorComp 360K, Myarc 360K), `dsdd` on both double-density cards.
- **A finding about open errors:** a missing file opened for input answers 2 on TI's and the CorComp's controllers, but **7 on the Myarc DDCC-1**, while a file of the wrong kind answers 2 on all three. So F18Base's double open (7 = missing, 2 = wrong kind) would work on a Myarc but not on the other two cards; `FEXIST` asks STATUS, which all three answer alike (bit 7 = no such file).
- **`roms/hfdc_dsr.u34`** (the Myarc HFDC's DSR, 16K) added to the distribution; the HFDC is a different card (hard and floppy), not modelled.

## 1.10.0 (30 October 2026)

Double-density disks, through the CorComp controller's real DSR.

- **The CorComp disk controller (v89) in the simulator** (`tools/ccfdc.py`): its two ROMs, their bank switch (CRU bit 11), the 128 bytes of RAM in bank 1, the chip on a plain data bus, drive, side and head lines; worked out from the ROM, which then runs. A 360K double-sided double-density disk (1,440 sectors, 18 a track) opens, reads, writes and catalogues through it.
- **`tools/fdc.py`**: the disk geometry (from the volume information block: sectors a track, tracks, sides; V9T9 sector order) and the WD177x chip model, split out of `tifdc.py` (which uses it; the TI card behaves as before) and extended to double density and two sides.
- **The simulated CPU gained `X`** (execute), which the CorComp ROM uses; a controller declares its own CRU range (the CorComp card has 32 bits).
- **`skdisk.py --geometry sssd|dssd|ssdd|dsdd`**: a 360K disk for a TI, a CorComp or js99er's generic controller.
- **ROMs now in the distribution** (`roms/`): the CorComp card's `ccdcc_v89.u3` and `.u4` (used by the tests) and the Myarc DDCC-1's `ddcc1.u3` (no model yet), added at the project owner's request. Their licence is not the project's, and their authors and terms are unknown to me: see `roms/README.md`. The tests that use them skip themselves if they are removed.
- Tests: `fileapi` now runs on both cards (the TI's 90K disk and the CorComp's 360K disk); new group `dsdd` (a file on the second side, a new file written there, the catalog's 1,440 sectors).
- Not done: the Myarc card's model; the workbench disks as 360K disks; any of it on a real card.

## 1.9.0 (30 October 2026)

- **`FSYNC`**: close and reopen the selected handle so everything written so far is safe on the disk, keeping the file open and its place: output and append files (reopened for append) and relative files (reopened for update); an input file does nothing; a sequential update file answers `FNOPL` (>FD) and stays open. Test (real controller ROM): after three `FWRITE`s the disk holds no record of the file until `FSYNC`, then all three; writing goes on at the end; five records in order after two syncs and the close; four relative records across two syncs.
- **Keys and music are kept during file calls**: `FCALL` calls `KIDLE` after every DSR call. A key tapped during 40 `FREAD`s is in the key buffer afterwards, and a song goes on playing (27 sound bytes in the test); both tests fail without the change. Cost measured in the simulator: about 200 instructions a call, +3.4% for open, 200 reads and close (1,171,841 to 1,211,646 instructions), which is little beside real disk time. Note: `FRAME` now counts the frames that pass during file work.

## 1.8.0 (30 October 2026)

New routines, from what F18Base had to work around (all tested in group `fileapi`; the file ones against TI's real controller ROM):

- **`FRREAD` / `FRWRITE`**: records of a RELATIVE file by number (R3), with the new open flag `FREL` (>0100). Records written out of order, read back in another order.
- **`FCATOP` / `FCATNX`**: the catalog one file at a time, the radix-100 numbers decoded into an entry (`CE_NAME`, `CE_TYPE`, `CE_SECT`, `CE_RLEN`); `FCEND` at the end.
- **`FEXIST`**: is a named file on the device? It asks for the file's STATUS (opcode 9: bit 7 = no such file), which is the same whatever kind of file it is (checked on TI's real ROM for sequential, relative and internal files). Opening cannot answer it: the real controller answers 2 for a missing file in every mode and for a file of the wrong kind alike, so a second open without the relative flag does not tell them apart (tested). A device that does not answer STATUS is asked through the catalog (`FEXCAT`, also public). Uses file handle 2.
- **`DECD`**: an unsigned 32-bit number as decimal, with a width (right-aligned).
- **`YESNO`**, **`PRESSK`**: a question on the message line answered with Y or N; a prompt that waits for a key.
- The kernel grows by about 500 bytes (now about 6.1K of the 7.7K it may have). KERNEL/EQU has 325 symbols (the TI assembler's table holds 580).
- **Not done** (proposed, see the review of the F18Base list): `FSYNC` (needs a specification: only output and relative files can be reopened at their place), key polling inside `FCALL` (to be measured against assembly speed), `LINEIN`, resident code for multi-module applications.

## 1.7.3 (30 October 2026)

- **Fixed: the arrow keys did nothing in js99er** (editor, and every application on the kernel, with js99er's option "Map arrow keys to Fctn+SDEX"). Since 1.5.0 `KPOLL` read the joystick columns (keyboard columns 6 and 7) every frame. js99er (`keyboard.js`, `isKeyDown`) takes any read of those columns to mean 'this program uses the joystick' and, for the next 250 reads, stops mapping the PC's arrow keys to FCTN+S/D/E/X; the arrows then act only as joystick 1, which a program that is not looking at the joystick ignores. Press, which reads no joystick, was not affected. Now the kernel reads the joysticks only for a program that uses them: the first `JOYGET` call (its own answer is 0) or a non-zero `JOYKEY` starts it (`JOYON`, `>20CE`). Tests (`joystick` group): `hello` never reads columns 6 or 7; the joystick example does.
- A program that uses `JOYKEY` (Reversi) is unaffected: in js99er its arrows reach it through the joystick, typed back as arrow keys.

## 1.7.2 (30 October 2026)

- **Fixed:** the workbench's file-name cursor was drawn one cell too far right, leaving a blank cell between the last character typed and the cursor (reported in js99er as offset to the right). It is now the cell right after the last character. Test: `workbench` (cursor at column 15 after 'DSK1.AB').

## 1.7.1 (30 October 2026)

The comment pass (assembled output unchanged except one message).

- **Commented for learning:** every assembly source in `kernel/` and `examples/` now opens with a block that explains the idea behind it (the video chip's ports, the keyboard matrix, the loader and cartridge banks, SAMS windows and the pool, the main loop, a symbol table as a hash table, how a TMS9900 instruction is encoded, ...) and has notes on the routines where the reasoning is not obvious. Files that were already thorough (`files`, `modules`, `reversi`, `diag`) received concept blocks rather than line-by-line notes. Not part of this pass: the test programs under `tests/` (`tests/asm`, `tests/apps`) and the Python tools (they have docstrings).
- **Checked:** the assembled output of every example, test application and workbench program is byte for byte what it was (52 of 54 build outputs; the other two are the workbench's `wb` module and its cartridge image, which differ only by the message below), and the commented sources still assemble on the simulated TI, identical to xas99.
- **Stale comments corrected** in the assembler: names are 12 characters (the comments said 8) and the symbol table has 580 slots of 14 bytes (the comment said 800 of 10).
- **Fixed:** the workbench's error message for a name over the limit said 'name over 8 characters'; the limit has been 12 since 1.3.

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
