# Lantern Kernel: how it works

For people who want to know what happens between power-on and `TICK`, why the kernel is shaped as it is, and what to
change when it must change. Application authors need only the [programmer's guide](PROGRAMMERS-GUIDE.md).

## 1. The parts

| File | Runs at | Is |
| --- | --- | --- |
| `loader.a99` (+ `vdp`, `f18a`, `f18det`, `pager`, `amsinit`) | cartridge bank 0, `>6000` | machine checks, refusal screens, copies the banks into SAMS |
| `kernel.a99` (+ `vdp`, `f18a`, `pager`, `keys`, `text`, `video`, `modules`, `pool`, `files`) | SAMS pages `>0A-0B`, `>A000` | start-up, main loop, exit, and every service |
| `databank.a99` | pages `>10-11`, read through slot B | the font and five colour schemes |
| the application's modules | slot C, `>C000` | the program |
| `kdefs.a99` | (included everywhere) | hardware addresses, memory map, key codes, roles, geometry |
| `macros.a99` | (included everywhere) | `.enter .leave .push .pop .intsvc .callmod` |
| `build/.../appcfg.a99`, `appname.a99`, `appmsg.a99` | (generated) | the application's numbers, name, refusal screens and bank table |

The kernel is about 3.6K of its 8K bank: there is room for roughly 4.5K more services before the bank is full.

## 2. The cartridge image

8K banks, bank *n* selected by writing to `>6000 + 2n` (the "378" scheme: FinalGROM 99 "8" images, js99er, Classic99).

| Bank | Holds | Goes to |
| --- | --- | --- |
| 0 | the loader (and the cartridge header the console's menu reads) | stays at `>6000` |
| 1 | the kernel | `>A000` (pages `>0A-0B`) |
| 2 | the data bank | pages `>10-11` |
| 3... | each module in `app.json` order, then each 8K piece of each data file | the pages `lkbuild` assigned |

The image is padded to a power-of-two number of banks (at least four).

## 3. Start-up

1. The console's menu finds the cartridge header at `>6000` (valid, one program) and runs `START`.
2. `START` (interrupts off, workspace `>8300`): **detect** the mapper (`AMSDET`), clear the kernel's scratchpad variables
   (`>8340-837F`), **identity-map** all 16 windows and switch mapping on (`AMSINI`), **size** the card (`AMSSIZ`), refuse if it
   has fewer than `PGMIN` pages, **clear slot A** (`>2000-3FFF`) and set the stack, **test** every page from `>10` up
   (`AMSTST`), **unlock** and **detect** the F18A, read its version.
3. A refusal ends in `REFUSE`, which shows a 40-column message and spins with interrupts allowed one slice at a time so the
   console's own QUIT key works.
4. **Copy**: the bank copier is moved into scratchpad (`>8380`) because selecting another bank makes the loader vanish from
   `>6000`. Bank 1 goes to `>A000`; then each `(bank, page)` pair in `BANKTB` is copied through slot B (`PAGEB`, then the copier
   into `>E000`). Slot B is put back and the loader branches to `>A000`.
5. `KSTART`: stack, the console ISR's flag byte (`>83C2 = >50`) and its frame-counter increment (`>83FC = 1`), `KINIT`
   (empty key buffer), `T80INI` (Text 80, glyphs, scheme 0, GPU program, DMA test, display on), then the **boot module** is
   switched to as if it had been asked for: `NEXTPG = PGBOOT`, and control joins the main loop at its check.

## 4. The main loop

```
KMAIN  VSYNC            wait for the frame (interrupts on inside, off outside)
       KPOLL            scan the keyboard, buffer a code on a new press or a repeat
       KEYGET           R0 = the next code or 0
       call TICK        the module's entry at >C002
KCHK   QUITF ?          non-zero: KEXIT
       NEXTPG ?         non-zero: switch (below), then KCHK again
       back to KMAIN
```

**Why `GOMOD` is deferred.** The caller is running in slot C. Remapping slot C under it would pull its code away mid-routine.
`GOMOD` therefore only records `NEXTPG` and `GOARG`; the loop does the mapping when the caller has returned. The same
check after the new module's `INIT` lets an `INIT` switch or quit at once.

**Switching** records the outgoing module in `PREVPG`, maps the new one with `PAGEC`, calls its `INIT` with
`R0 = PREVPG` and `R1 = GOARG`, and goes back to `KCHK`.

**`MODCALL`** (a call, not a switch) pushes the current `CURPC`, maps the target module, calls the routine at the entry's address,
saves its `R0` in `MCRET`, maps the caller back from the pushed `CURPC` and returns `R0`. The mapping uses `R0-R4`, `R7`, `R12`, so
extra arguments and results travel in `R5`, `R6`, `R8`, `R9` or in memory.

## 5. SAMS paging

`MAPPG` writes `(page << 8) | page` to the window's register at `>4000 + 2 x window` with the registers exposed (`SBO 0`) and hides them
again. `PAGEC`, `PAGEB`, `MAPE`, `MAPF`, `SETPB` keep `CURPC` / `CURPB` in step. Two different pages in slot B are allowed
(`MAPE` and `MAPF` each set one half of `CURPB`); `PAGEB` sets a consecutive pair; `SETPB` restores both halves of a saved
`CURPB` independently (the Press ancestor restored by remapping a consecutive pair from the first page, which is wrong when
the halves differ).

## 6. Memory maps

### Slot A

| Range | Name | Holds |
| --- | --- | --- |
| `>2000-203F` | `KEYMAP`, `KLAST` ... | keyboard state: columns, last code, hold counter, modifiers, buffer head/tail |
| `>2040-207F` | `KBUF` | the 64-byte key buffer |
| `>2080-209F` | `SCHEME`, `TXTBUF` | current scheme; 16 bytes for number formatting |
| `>20A0-20BF` | `MCENT` ... `PREVPG`, `GPUBUF`, `NODMA` | module system words, the DMA mailbox as built |
| `>20C0-20E7` | `POOLBM` ... `FREECT` | the page pool's bitmap (32 bytes), range, free count |
| `>2100-21BF` | `FHOT` ... `FPAB` | the file service's state: scratchpad save (96), device name, saved words, the PAB (64) |
| `>21C0-21FF` | | free for the kernel's growth |
| `>2200-22FF` | `MODRAM` | scratch for the running module |
| `>2300-3EFF` | `APPRAM`..`APPTOP` | **the application's**: 7,168 bytes |
| `>3F00-3FFF` | stack | R10 starts at `>4000`; 128 words |

### Scratchpad

| Range | Holds |
| --- | --- |
| `>8300-831F` | the workspace `WS`: R0-R15 |
| `>8320-833F` | free (saved and restored around DSR calls) |
| `>8340-834F` | `FRAME CURPA CURPB CURPC F18FLG F18VER NPAGES QUITF` |
| `>8350` | `VDPPIC` (non-zero: PICO9918) |
| `>8352-8353`, `>8358-836F` | free; a DSR changes parts of `>8320-837F` while it runs and the file service puts them back |
| `>8354-8357` | the DSR's name length and pointer (while a call runs) |
| `>8370` | the loader's failing page number (briefly); then the disk controller's "top of VRAM", **kept as it leaves it** |
| `>8379` | the console ISR's frame counter |
| `>8380-83BF` | the loader's bank copier; **free to applications afterwards** |
| `>83C0-83DF` | the console's interrupt workspace; `>83C2` flags, `>83CC-CE` sound list, `>83D4` `VR1CPY`, `>83D6` blank timer |
| `>83E0-83FF` | the GPL workspace, where DSRs run; `>83FC` the ISR's timer increment, `>83FD` the sound-list flag |

### SAMS pages

As in the guide's part 7: `>00-01` unused, `>02-03` slot A, `>04-09` free, `>0A-0B` kernel, `>0C-0F` the default pairs, `>10-11`
data bank, `>12` up modules and data, then your pool from `PGFREE`.

### VRAM

As in the guide's part 5.

## 7. The keyboard in detail

`KSCAN` writes each column number to the 9901's outputs 18-20 and reads the eight rows from inputs 3-10 into `KEYMAP` (0 = down),
then reads ALPHA LOCK (output 21 low, input 7; ignored while FCTN is down because FCTN shares the line). `KDECOD` picks a table by the
highest-precedence modifier (FCTN, then CTRL, then SHIFT) and looks up the first key found, column by column; ALPHA LOCK capitalises
unmodified letters. `KPOLL` sends a code only when a *new key* goes down (`KLKEY` differs), with the modifiers held at that moment;
a held key repeats the first code from frame 24, every 4 frames after. `KPUT` buffers it, clears the blank timer and rewrites VR1
from `VR1CPY` with the display bit set.

## 8. The file service in detail

`FOPEN`/`FDELETE` build the PAB (opcode, flags, VRAM buffer `>3600`, record length, the name) in slot A (`FPAB`) and copy it to VRAM `>3700`.
`FREAD`/`FWRITE` poke the opcode (and, for a write, the character count and the record bytes) into the VRAM PAB and buffer. Every operation
goes through `FCALL`: clear the previous error bits in the PAB's flag byte; save `>8320-837F` into `FHOT`; point `>8356` at the PAB's name
length; `DSRLNK`; restore the scratchpad; restore the frame increment at `>83FC`; put `>8370` back from `FD70`.

`DSRLNK` reads the name length and device name (up to the dot) from the PAB, sets `>8354`/`>8356`, walks the CRU bases `>1000-1F00`
switching each card's ROM on, checking the `>AA` header and the device list at `>4008`, comparing names. On a match it runs the card's
power-up routine once (`>4004` list; `FDPWR` remembers), then calls the device routine in the GPL workspace (`DLGPL`, with `R12`, `R13 = >9800`,
`R15 = >8C02`). The DSR returns to `R11+2` if it handled the call and to `R11` if not; either way the error is read from the PAB flag byte.

## 9. Exit

`KEXIT`: silence the sound chip; wait until all keyboard columns read up, at most 60 frames; `F18OFF` (VR49, VR50, VR51, VR15, palette 0-15);
SAMS mapping off (`SBZ 1`, `SBZ 0`); select cartridge bank 0 (so the console finds the program's header); `BLWP @>0000`. The code runs from
`>A000`, which stays in its own window when mapping is off (identity), so the switch is safe.

## 10. The build

`lkbuild.py`: generate `gen/font.a99` and `gen/keytab.a99`; assign pages (modules, then data files) and write `appcfg.a99` (`PGMIN`,
`PG_<MODULE>`, `PGBOOT`, `PGFREE`, `PD_<FILE>`), `appname.a99`, `appmsg.a99` (refusal messages built from the name and `min_pages`, and `BANKTB`);
assemble the kernel with `-E build/kernel.equ` (every symbol, so modules know the kernel's addresses *and* the application's page equates);
assemble the loader, the data bank and the modules; check each fits in 8K; concatenate; pad to a power of two.

## 11. Design decisions and why

- **Kernel in fixed SAMS pages, application in slot C.** The ancestor (The Lantern Coast) used scene banks in the same window; Press grew into
  modules. 8K per module is tight but forces structure, and `MODCALL`/`GOMOD` make crossing it cheap.
- **The loader copies everything into SAMS at start-up** so that cartridge banks need not be switched while running: the running code never
  disappears from under itself, and slot C's modules are simply pages. The cost is paid once: in the simulator the first screen appears after about
  84,000 instructions for the small examples (more for a bigger image, which copies more banks). Real time on a TI has not been measured.
- **Software stack in slot A, not scratchpad.** Scratchpad is 256 bytes shared with the console; the stack is 256 more in slot A.
- **Interrupts masked except in `VSYNC`.** A TMS9900 interrupt between the two bytes of a VDP address write corrupts the address. Only the frame wait
  allows one, and the main loop is built around that.
- **`GOMOD` deferred, `MODCALL` immediate.** See part 4.
- **One file at a time.** The PAB and buffer live at fixed VRAM addresses so that the controller's own buffers (`>37D8` up) are never disturbed.
- **The role-based colour scheme** puts the colours in 16 palette words, so a scheme change is 32 bytes of I/O.

## 12. Open questions

- Hardware: the kernel as packaged has not run on a real TI. The pieces were proven on real hardware inside Press and The Lantern Coast, but
  `GOMOD`, the page pool, `FCNUM` and the loader's table-driven copy are new.
- Whether a real DSR clears the previous call's error bits itself (the file service clears them regardless; the check is not decisive with TI's controller).
- Whether the console always leaves `>83FC`'s high byte non-zero (the kernel sets it regardless). TI's disk controller DSR was watched and never wrote it.
- Sound: only the console's sound-list player is available; no tests exercise it.
- Cards over 1M, and the PICO9918's quirks beyond what Press found.
