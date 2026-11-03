# Roadmap and decisions

Where the SAMS Kernel project stands after 1.24.0, so that the repository says it and not only the change log.

## Decisions (the owner's, 2 November 2026)

| Question | Decision |
| --- | --- |
| Is a disk-started kernel in scope? | **Yes**, and built (1.25.0). See `docs/DISKSTART.md`. |
| Which music notation is the default? | TXA's `.txm`. Not built yet: the build needs TXA's notation specification and its compiler (`docs/MUSIC.md` notes this); the kernel's own song format and `skmusic.py` stay until it exists. |
| Licence of code taken in from TXA, TIthon and the owner's other projects | **MIT**, each file saying so. |
| The ROM files in `roms/` | **They stay** (see `roms/README.md`). |

## Done from the TXA and TIthon proposals

Code in application RAM (`"appram_code"`, 1.26.0), the disk start and `PRUN` (1.25.0), `.mape`/`.mapf`/`.mapd`, `FLOAD`/`FSAVE`, `LINEIN` to 159 characters and the scrolling field, single-page modules and window `>D000`, common code at `>D000`,
the frame hook, the break flag, the float-safe scratchpad, the faster pool and `PALLOCA`, `lib/float.a99` (`FPCALL`), the cycle model (`tools/cycles.py`).

## Open

- **The disk start and `PRUN`**: built and tested in the simulator (1.25.0, `docs/DISKSTART.md`); steps D1-D5 of the hardware checklist are the open part. Not done: two small modules in one bank, a bootstrap that finds its own name.
- **`.txm` as the default notation and `SFXPLAY`** (needs TXA's specification and compiler).
- **Picture libraries and `BMLON`/`BMLOFF`** (TXA 1.4, 1.5, 2.6).
- Packing two 4K modules in one bank; the second table's float entries other than `XCFI`; the HFDC hard-disk side; a real-TIPI model for the simulator; self-hosting the
  kernel's assembly on the TI (the assembler's 4,096-byte output buffer and 580-name symbol table are the obstacles).
- **Real hardware**: everything since 1.16 has run only in the simulator; `docs/HARDWARE-CHECKLIST.md` lists what to try.
