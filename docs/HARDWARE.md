# SAMS Kernel: hardware notes

What the kernel does with each piece of hardware, and why. The F18A facts were taken from
js99er's source (`src/app/emulator/classes/f18a.ts`, the reference emulator) and the keyboard
facts from its `cru.ts` and `key-mapper.ts`; the code in this kernel is the code that ran The
Lantern Coast and Press on real machines, but **the kernel as packaged here has been run only
in the simulator** (with and without TI's real console interrupt routine). Treat the first run on a
real machine as a test: run `examples/diag` and press CTRL T.

## Boot: the loader's four checks

The loader (cartridge bank 0, `loader.a99`) runs these before it loads anything:

1. **SAMS present.** `AMSDET` writes and reads back a mapper register.
2. **SAMS size.** `AMSSIZ` writes a marker to page `>10`, then a different value to page `>10` + 32,
   + 64 and + 128; the first write that lands on page `>10`'s marker shows how many page bits the card
   decodes. With no alias at +128 the card is used as 256 pages (1M); larger cards are used as 1M.
   The probe comes *before* any full test because writing every page of a too-small card would go
   through an alias into the kernel's own pages. The count must be at least `min_pages`.
3. **Page test.** `AMSTST` writes a page-specific word to the first and last word of every page from
   `>10` to the top, then checks them. A failure names the page. (Pages below `>10` are slot A, the
   kernel's and slot B/C's defaults, and the free pages `>04-09`; they are not tested.)
4. **F18A.** The lock-safe `F18UNL` (an unlock sequence sent to an *unlocked* F18A locks it: so
   first ask by reading status register 1), then `F18DET` (status register 1 reads `111xxxxx`). A
   PICO9918 (ID `>E8`) is accepted as F18A-compatible and flagged in `VDPPIC`. The firmware version
   is read from status register 14.

A failed check shows a refusal screen in 40-column text with the console's own font (copied from
GROM) and leaves the console interrupt routine's QUIT working, so FCTN = returns to the title. The
refusal code is a leaf that needs no expansion RAM, because with no memory card there may be none.

Then slot A and the kernel's scratchpad variables are cleared (real RAM powers up random), the
banks are copied into SAMS and the kernel starts.

## Video: the F18A's modes

The boot mode is Text 80 at 30 rows with an attribute per position; `VMODE` sets any other (VIDEO-MODES.md is the reference, with pictures of each). The registers of the boot mode:

| Register | Value | Meaning |
| --- | --- | --- |
| VR0 | `>04` | M4: Text 80 (with VR1's M1) |
| VR1 | `>F0` | 16K, display on, interrupts on, M1 |
| VR2 | `>00` | name table at `>0000` (unlocked F18A: (VR2 AND `>0F`) x `>400`) |
| VR3 | `>28` | position-attribute table at `>0A00` (VR3 x `>40`) |
| VR4 | `>03` | pattern table at `>1800` ((VR4 AND 7) x `>800`) |
| VR5 | `>28` | sprite attribute table at `>1400` (VR5 x `>80`) |
| VR6 | `>06` | sprite patterns at `>3000` ((VR6 AND 7) x `>800`) |
| VR7 | `>21` | text colours (role 2 on role 1) and the backdrop (role 1) |
| VR29 | `>80` | extra pattern planes `>800` apart for tiles, `>200` apart for sprites |
| VR49 | `>40` | 30 rows; no enhanced colour |
| VR50 | `>02` | attributes per position |
| VR51 | `>00` | stop sprite 0: no sprites. With 30 rows the F18A ignores the `>D0` sprite-list terminator, and an unlocked F18A draws sprites in text modes, so they are stopped this way |

Each cell's attribute byte names the foreground (high nibble) and background (low nibble) palette
entry. Entry 0 draws nothing (the backdrop shows); the border is 16 pixels each side in Text 80, 8 in Text 40, drawn in the backdrop colour.

**The modes, as the registers select them** (js99er's F18A emulation, from the F18A documentation):

| Mode | VR0 | VR1 bits | Notes |
| --- | --- | --- | --- |
| Graphics I | `>00` | M1 = M2 = 0 | |
| Text 40 | `>00` | M1 (`>10`) | |
| Text 80 | `>04` | M1 | VR0 bit 2 |
| Multicolor | `>00` | M2 (`>08`) | |
| Graphics II (bitmap) | `>02` | M1 = M2 = 0 | VR0 bit 1 (M3); VR3 bit 7 / VR4 bit 2 pick the tables, their low bits mask the thirds |

Enhanced colour for tiles is VR49 bits 5-4, for sprites bits 1-0; VR50 bit 1 puts the attribute table per position; VR49 bit 6 is 30 rows, bit 7 tile layer 2, bit 2 sprite linking, bit 3 real sprite Y.
The F18A accepts registers 8-63 only when unlocked (below); a locked F18A masks writes above 7 when Text 80 is off.

**Quit** (`F18OFF`, then `BLWP @>0000`): every register `VMODE` and `VREG` can change goes back to its power-up value (VR10, VR11, VR19, VR24-VR31 to 0, VR48 to 1, VR49 and VR50 to 0, VR51 to 32), VR15 to 0, palette entries 0-15 to the standard
colours, SAMS mapping off. The console's reset sets only VR0-VR7, so without this the TI title screen comes up wrong.

**Unlocking.** The F18A stays unlocked through a console reset, and any write to VR57 while it is
unlocked locks it again. On a stock 9918A the unlock write lands on VR1 and blanks the screen; the
kernel never gets that far because the loader has refused a machine without an F18A.

**Palette.** 64 entries of 12 bits (`>0RGB`), written through VR47 (`>C0` + index: palette data mode
with auto-increment, two data-port writes per entry). The kernel loads 0-15 (the colour scheme); VR24 and the attribute
bytes select which entries each layer uses.

**DMA and the GPU.** `VSHIFT` writes an 8-byte mailbox to VRAM `>0960`, points the GPU at its program at
`>0970` (VR54/55), and waits on status register 2 bit 7. The kernel tests the DMA engine once at boot
(`DMATST`: copy 80 bytes, read them back) and sets `NODMA` if the copy did not arrive.

## Colour roles and schemes

See the programmer's guide, part 5. A scheme is 16 palette words; the five built in follow TI-Writer's
Screen Color order. Changing scheme rewrites 16 palette entries and nothing on the screen.

## Glyphs

256 patterns of 6 x 8 (Text 80 shows bits 7-2 of each byte): UI glyphs 0-31, ASCII 32-126, the Latin-1
marker 127, underlined ASCII 128-222 (code + 96), more UI 223-255. [GLYPHS.md](GLYPHS.md) has the chart.

## The keyboard

The matrix: columns on the 9901's outputs 18-20, rows on inputs 3-10; row r is bit r of a column's
byte (a 0 bit is a key down).

| Column | Row 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | = | SPACE | ENTER | | FCTN | SHIFT | CTRL | |
| 1 | . | L | O | 9 | 2 | S | W | X |
| 2 | , | K | I | 8 | 3 | D | E | C |
| 3 | M | J | U | 7 | 4 | F | R | V |
| 4 | N | H | Y | 6 | 5 | G | T | B |
| 5 | / | ; | P | 0 | 1 | A | Q | Z |

**ALPHA LOCK** is read on input 7 while output 21 is low. Input 7 is also FCTN's row line, so the scanner
keeps output 21 high while scanning, reads ALPHA LOCK with column 0 selected, and ignores the reading
while FCTN is held (keeping the last state).

**Codes.** FCTN takes precedence over CTRL over SHIFT. The four chord tables (generated by
`tools/keytab.py`; blank = no code):

| Key | Col | Row | plain | SHIFT | FCTN | CTRL |
| --- | --- | --- | --- | --- | --- | --- |
| = | 0 | 0 | `3D` | `2B` | `FD` | `BD` |
| SPACE | 0 | 1 | `20` | `20` | `E0` | `A0` |
| ENTER | 0 | 2 | `0D` | `0D` | `0D` | `8D` |
| . | 1 | 0 | `2E` | `3E` | `EE` | `AE` |
| L | 1 | 1 | `6C` | `4C` | `CC` | `8C` |
| O | 1 | 2 | `6F` | `4F` | `27` | `8F` |
| 9 | 1 | 3 | `39` | `28` | `F9` | `B9` |
| 2 | 1 | 4 | `32` | `40` | `F2` | `B2` |
| S | 1 | 5 | `73` | `53` | `D3` | `93` |
| W | 1 | 6 | `77` | `57` | `7E` | `97` |
| X | 1 | 7 | `78` | `58` | `D8` | `98` |
| , | 2 | 0 | `2C` | `3C` | `EC` | `AC` |
| K | 2 | 1 | `6B` | `4B` | `CB` | `8B` |
| I | 2 | 2 | `69` | `49` | `3F` | `89` |
| 8 | 2 | 3 | `38` | `2A` | `F8` | `B8` |
| 3 | 2 | 4 | `33` | `23` | `F3` | `B3` |
| D | 2 | 5 | `64` | `44` | `C4` | `84` |
| E | 2 | 6 | `65` | `45` | `C5` | `85` |
| C | 2 | 7 | `63` | `43` | `60` | `83` |
| M | 3 | 0 | `6D` | `4D` | `CD` | `8D` |
| J | 3 | 1 | `6A` | `4A` | `CA` | `8A` |
| U | 3 | 2 | `75` | `55` | `5F` | `95` |
| 7 | 3 | 3 | `37` | `26` | `F7` | `B7` |
| 4 | 3 | 4 | `34` | `24` | `F4` | `B4` |
| F | 3 | 5 | `66` | `46` | `7B` | `86` |
| R | 3 | 6 | `72` | `52` | `5B` | `92` |
| V | 3 | 7 | `76` | `56` | `D6` | `96` |
| N | 4 | 0 | `6E` | `4E` | `CE` | `8E` |
| H | 4 | 1 | `68` | `48` | `C8` | `88` |
| Y | 4 | 2 | `79` | `59` | `D9` | `99` |
| 6 | 4 | 3 | `36` | `5E` | `F6` | `B6` |
| 5 | 4 | 4 | `35` | `25` | `F5` | `B5` |
| G | 4 | 5 | `67` | `47` | `7D` | `87` |
| T | 4 | 6 | `74` | `54` | `5D` | `94` |
| B | 4 | 7 | `62` | `42` | `C2` | `82` |
| / | 5 | 0 | `2F` | `2D` | `EF` | `AF` |
| ; | 5 | 1 | `3B` | `3A` | `FB` | `BB` |
| P | 5 | 2 | `70` | `50` | `22` | `90` |
| 0 | 5 | 3 | `30` | `29` | `F0` | `B0` |
| 1 | 5 | 4 | `31` | `21` | `F1` | `B1` |
| A | 5 | 5 | `61` | `41` | `7C` | `81` |
| Q | 5 | 6 | `71` | `51` | `D1` | `91` |
| Z | 5 | 7 | `7A` | `5A` | `5C` | `9A` |

**Repeat and buffer.** `KPOLL` runs once a frame. A new chord gives one code; held, it repeats from the
24th frame and then every 4. Codes go into a 64-entry ring buffer (63 usable): when it is full, new codes
are dropped. A key clears the console's screen-blank timer and rewrites VR1.

## The console's interrupt routine

Interrupts are allowed only inside `VSYNC`, long enough for the console routine (at `>0900`, workspace
`>83C0`) to run once. It reads the VDP status (clearing the frame flag), adds the byte at `>83FC` to the frame
counter at `>8379`, plays a sound list if one is running, and advances the screen-blank timer at `>83D6`,
blanking the screen when it wraps. `>83C2` = `>50` turns off its sprite motion and its QUIT handling.

**Found by running TI's real routine** (against a console ROM image in the simulator): the counter at `>8379`
advances by the *high byte of `>83FC`* (R14 of the GPL workspace), not by one. The console leaves that byte
non-zero, which is why programs written against a real console always worked, but nothing guarantees it
survives a DSR (which runs in that workspace). The kernel therefore sets it to 1 at start-up and again after
every DSR call. If you write your own DSR calls, do the same.

## Sound

The TMS9919 (SN76489 family) has three tone voices and a noise voice, written a byte at a time at `>8400`; MUSIC.md has the byte formats, the divider table and the player. The console's interrupt routine also plays *sound lists* from
VDP RAM or GROM (pointer `>83CC`, duration `>83CE`, flag bit 0 of `>83FD`); `>83C2` = `>50` does not turn that off, so both can drive the chip. The kernel silences it on quit (four attenuation bytes `>9F >BF >DF >FF`).

## SAMS

**Cards of more than 1M (a 16M SAMS).** The kernel numbers pages 0-255 (it keeps them in a byte), so it uses the first 1M of such a card and ignores the rest; `AMSSIZ` reports 256. Page registers are 12 bits on a big card (as js99er models it:
the even byte is the low 8 bits, the odd byte bits 8-11), and `MAPPG` and `AMSINI` write the page in *both* bytes. On a 1M card the extra bits are ignored; on a 16M card they turn page *p* into the physical page `(p AND >F) * 256 + p`, a
different but still one-to-one choice, so every page the kernel uses is still a separate page of RAM. In the simulator's model of a 16M card (test group `sams16`) the kernel boots and its self-test passes. **Not tried on a real 16M card or in
js99er's 16M setting.** If it fails there, the first things to look at are those register writes (`MAPPG`, `AMSINI` in kernel/pager.a99 and amsinit.a99) and `AMSSIZ`.

Registers are words at `>4000 + 2 x window` while CRU `>1E00` bit 0 is set; each latches one byte, so a word
is written as (page << 8) | page. CRU bit 1 turns mapping on. The loader maps the identity (page n at window n)
so the kernel at `>A000` is on pages `>0A-0B` and nothing moves. Registers share space with DSR ROMs: they are
hidden again (`SBZ 0`) after each access.

## Devices (the file service)

A DSR is found by walking the CRU bases `>1000-1F00`, checking each ROM's header and device list for the name
before the first dot. It runs in the GPL workspace with `R12` the card's base, `R13 = >9800`, `R15 = >8C02`;
`>8354` holds the device name's length and `>8356` points at the PAB's name length byte; the controller's power-up
routine runs once. The DSR returns to R11+2 when it handled the call (the error, if any, is in the PAB flag byte's top
three bits) and to R11 when the device was not its own.
