# Roadmap and decisions

Where the SAMS Kernel project stands after 1.24.0, so that the repository says it and not only the change log.

## Decisions (the owner's, 2 November 2026)

| Question | Decision |
| --- | --- |
| Is a disk-started kernel in scope? | **Yes**, and built (1.25.0). See `docs/DISKSTART.md`. |
| Which music notation is the default? | TXA's `.txm`: **built** (1.27.0): `skmusic.py` compiles it through TXA's reference compiler; the kernel's song format is unchanged (`docs/MUSIC.md`). |
| Licence of code taken in from TXA, TIthon and the owner's other projects | **MIT**, each file saying so. |
| The ROM files in `roms/` | **They stay** (see `roms/README.md`). |

## Done from the TXA and TIthon proposals

The option 5 runner and a cartridge menu with two programs (`"ea5": true`, 1.31.0), pictures on the bitmap layer (`skpic.py`, `lib/picture.a99`: `PICSHOW`, `BMLON`, `BMLOFF`, 1.30.0), sound effects over the song (`SFXPLAY`, `"sfx": true`, 1.30.0), code in application RAM (`"appram_code"`, 1.26.0), the disk start and `PRUN` (1.25.0), `.mape`/`.mapf`/`.mapd`, `FLOAD`/`FSAVE`, `LINEIN` to 159 characters and the scrolling field, single-page modules and window `>D000`, common code at `>D000`,
the frame hook, the break flag, the float-safe scratchpad, the faster pool and `PALLOCA`, `lib/float.a99` (`FPCALL`), the cycle model (`tools/cycles.py`).

## Open

- **The disk start and `PRUN`**: built and tested in the simulator (1.25.0, `docs/DISKSTART.md`); steps D1-D5 of the hardware checklist are the open part. Not done: two small modules in one bank, a bootstrap that finds its own name.
- **Option 5 runner: built in 1.31.0** (`"ea5": true`, `kernel/ea5run.a99`; see the workbench manual); what follows is how it was derived and what is open. Open: real programs and a real TI (checklist R1-R4); module-only disk programs (the cartridge supplying the kernel). What is established (sources: the Editor/Assembler manual, sections 24.5 and 16, and Nouspikel's page on the module as quoted by a search, not fetched: the site blocks fetches):
  the Editor/Assembler module is a **pure GROM** (one GROM, `>6000-7800` in GROM space), not CPU ROM at `>6000`, so nothing of it needs to be reproduced there; an **option 5 image is a chain of PROGRAM files of up to 8K each, the next name being the last character incremented**,
  and **must carry whatever it needs: it cannot rely on the module's utilities** (VSBW, VMBW, KSCAN, DSRLNK and the rest are loaded into low RAM by the module's loader or by CALL INIT, and a program saved from memory contains them only if it saved that range); a program **starts at its first file's load address**
  (the practice on AtariAge: the first instruction of an image is `B @START`; the header's three words are the continuation flag, the length and the load address). **The Editor/Assembler's own utility addresses** (read from the REF/DEF table of the EA-Prom ROM image the owner supplied, `edas4_v44.zip`, 4 November 2026; a reimplementation of the module in a 32K banked EPROM: **its code is derived from TI's and is not copied into this repository**, only facts are taken from it): `GPLLNK >2100`, `XMLLNK >2104`, `KSCAN >2108`, `VSBW >210C`, `VMBW >2110`, `VSBR >2114`, `VMBR >2118`, `VWTR >211C`, `DSRLNK >2120`, `LOADER >2124`
  (vectors in low RAM), `UTLTAB >2022`, and the predefined symbols `PAD >8300`, `GPLWS >83E0`, `SOUND >8400`, `VDPRD >8800`, `VDPSTA >8802`, `VDPWD >8C00`, `VDPWA >8C02`, `SPCHRD >9000`, `SPCHWT >9400`, `GRMRD >9800`, `GRMRA >9802`, `GRMWD >9C00`, `GRMWA >9C02`, `SCAN >000E`. (The cheat sheet's `VSBW >2020`, `VMBW >2024`, `VWTR >2030` are Extended BASIC's, set by `CALL INIT`.)
  So a memory image that calls a utility through the module's vectors needs `>2100-2127` loaded as the module loaded it, which an image carries only if its saved range includes them.
**What the module's option 5 does, traced in the EA-Prom ROM (facts only, no code copied):** it prompts for a file name; builds a PAB in VRAM at `>1300` for the DSR's **LOAD** (opcode 5, buffer `>1380`, up to `>2100` bytes) and calls its own DSRLNK; reads the file's six header bytes
  from VRAM into `>834A-834F` (continuation flag, length, load address); copies the data to the load address (VRAM to CPU RAM); **keeps the first file's load address as the entry address (in `>8348`, which it clears first and sets only if still 0)**; while the flag word is non-zero it **increments the
  last character of the name** and loads the next file the same way; then, for option 5, **`LWPI >83E0` (the GPL workspace) and `BL *entry`**, so **R11 holds a return address into the module** (a program ends with `RT` to come back to the menu) and the mapper is whatever the console left (plain 32K). It does not change the interrupt mask on the way (the module runs under the console's, which is enabled), clear
  memory, or reset VDP registers first. So a runner entered from the console's own menu (a second entry in the cartridge's program list, before anything touches the scratchpad) can do the same with a small DSR LOAD routine of its own: no kernel is involved and no state needs rebuilding.
What is left to settle: what state a program expects (interrupts, the VDP, the SAMS mapper), best learned by trying real programs; the manual's remark
  that the `SAVE` utility takes `SFIRST` and `SLOAD` separately, which suggests images might start elsewhere than at the load address, which no source seen says. `tools/ea5.py` implements the format as understood.
- Packing two 4K modules in one bank; the second table's float entries other than `XCFI`; the HFDC hard-disk side; a real-TIPI model for the simulator; self-hosting the
  kernel's assembly on the TI (the assembler's 4,096-byte output buffer and 580-name symbol table are the obstacles).
- **Real hardware**: everything since 1.16 has run only in the simulator; `docs/HARDWARE-CHECKLIST.md` lists what to try.
