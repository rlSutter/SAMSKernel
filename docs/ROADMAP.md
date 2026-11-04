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

Pictures on the bitmap layer (`skpic.py`, `lib/picture.a99`: `PICSHOW`, `BMLON`, `BMLOFF`, 1.30.0), sound effects over the song (`SFXPLAY`, `"sfx": true`, 1.30.0), code in application RAM (`"appram_code"`, 1.26.0), the disk start and `PRUN` (1.25.0), `.mape`/`.mapf`/`.mapd`, `FLOAD`/`FSAVE`, `LINEIN` to 159 characters and the scrolling field, single-page modules and window `>D000`, common code at `>D000`,
the frame hook, the break flag, the float-safe scratchpad, the faster pool and `PALLOCA`, `lib/float.a99` (`FPCALL`), the cycle model (`tools/cycles.py`).

## Open

- **The disk start and `PRUN`**: built and tested in the simulator (1.25.0, `docs/DISKSTART.md`); steps D1-D5 of the hardware checklist are the open part. Not done: two small modules in one bank, a bootstrap that finds its own name.
- **A menu cartridge with an Editor/Assembler option 5 runner** (the owner asked for it, 4 November 2026; not started). What is established (sources: the Editor/Assembler manual, sections 24.5 and 16, and Nouspikel's page on the module as quoted by a search, not fetched: the site blocks fetches):
  the Editor/Assembler module is a **pure GROM** (one GROM, `>6000-7800` in GROM space), not CPU ROM at `>6000`, so nothing of it needs to be reproduced there; an **option 5 image is a chain of PROGRAM files of up to 8K each, the next name being the last character incremented**,
  and **must carry whatever it needs: it cannot rely on the module's utilities** (VSBW, VMBW, KSCAN, DSRLNK and the rest are loaded into low RAM by the module's loader or by CALL INIT, and a program saved from memory contains them only if it saved that range); a program **starts at its first file's load address**
  (the practice on AtariAge: the first instruction of an image is `B @START`; the header's three words are the continuation flag, the length and the load address). What is left to settle: what state a program expects (interrupts, the VDP, the SAMS mapper), best learned by trying real programs; the manual's remark
  that the `SAVE` utility takes `SFIRST` and `SLOAD` separately, which suggests images might start elsewhere than at the load address, which no source seen says. `tools/ea5.py` implements the format as understood.
- Packing two 4K modules in one bank; the second table's float entries other than `XCFI`; the HFDC hard-disk side; a real-TIPI model for the simulator; self-hosting the
  kernel's assembly on the TI (the assembler's 4,096-byte output buffer and 580-name symbol table are the obstacles).
- **Real hardware**: everything since 1.16 has run only in the simulator; `docs/HARDWARE-CHECKLIST.md` lists what to try.
