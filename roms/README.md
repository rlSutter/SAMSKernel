# roms/

| File | Size | SHA-256 | What |
| --- | --- | --- | --- |
| `cf7a+.bin` | 8,192 bytes | `4696dbc973eac2bc97eabd27e01152f17acebbd905a8da2451b1f626f09eadce` | the CF7+ DSR ROM: the device service routines of the CF7+ / nanoPEB compact-flash disk system |

**What it is.** A peripheral card's DSR ROM, mapped at `>4000-5FFF` when the card's CRU bit is set (the CF7+ sits at CRU `>1100`, the
same place as the TI disk controller). Its header (`>AA`, version 7) lists the power-up routine at `>4066` and the DSR list at `>406C`:
devices `DSK`, `DSK1`, `DSK2`, `DSK3`; and subprograms `>10-16` and `FILES`. It keeps its disk volumes on a CompactFlash card as 400K
images in its own format (2 sides, 20 sectors a track, 80 tracks), reached through ATA-style registers, not a WD1771.

**Where it came from.** `roms/cf7a+.bin` in ti99sim 0.16.0's source tree, which ships it with a descriptor (`cf7+.dat`) and an emulation of the
card (`src/core/cf7+.cpp`, `disk-serializer-cf7+.cpp`). Its author and licence are not stated in what I was given (ti99sim's README
only says it supplies the ROM); you added it to this project on 28 October 2026 and it is yours to keep or remove.

**What the kernel project does with it.** Nothing yet. The file service is written against the DSR calling convention, which the CF7+
follows (device names `DSKn`, the same PAB), so an application using `FOPEN` and friends reaches a CF7+ volume exactly as it reaches a floppy.
No test runs it: that needs the card's registers and a CF7+ disk image emulated in `tools/` (ti99sim's source is the reference). The TI
disk controller's and the console's ROMs are TI's and are deliberately **not** here; see the project README for how the tests find them.
