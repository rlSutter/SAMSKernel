# roms/

| File | Size | SHA-256 | What |
| --- | --- | --- | --- |
| `cf7a+.bin` | 8,192 bytes | `4696dbc973eac2bc97eabd27e01152f17acebbd905a8da2451b1f626f09eadce` | the CF7+ DSR ROM: the device service routines of the CF7+ / nanoPEB compact-flash disk system |
| `ccdcc_v89.u3` | 8,192 bytes | `a38aea29ddfa54f667934a40f3ed4161af48a6484d3ecb8d3cf34be40abc87be` | the CorComp Disk Controller card, version 89: ROM u3, the DSR proper |
| `ccdcc_v89.u4` | 8,192 bytes | `65275417e2aa2038627f91cd58c8f95b61c165a1b33027c880219b23e86ab9a1` | the same card's ROM u4: the low-level disk I/O layer |
| `ddcc1.u3` | 8,192 bytes | `125f84a721c270c7c068a32e1d372070461df0a80e2336a886bd9bd0ae725613` | the Myarc DDCC-1 disk controller card's DSR ROM (two 4K banks): used by the tests |
| `hfdc_dsr.u34` | 16,384 bytes | `140a8890f566bf5c555af5342ceef77ec3b57f48f276368bacd09e395d7dbc43` | the Myarc HFDC (hard and floppy disk controller) DSR, two 8K halves joined: **not used yet**, no model |

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

## The CorComp and Myarc controller ROMs (added 30 and 31 October 2026)

**CorComp (`ccdcc_v89.u3`, `ccdcc_v89.u4`).** A double-density controller card for the TI. The two 8K ROMs are two banks of one 16K ROM,
both mapped at `>4000-5FFF`; CRU bit 11 selects the bank (u3: device names `DSK`, `DSK1` to `DSK4` and lowercase `dsk1`, the disk subprograms
`>10-16`, `FILES` and the CorComp utilities; u4: the disk I/O layer, which alone touches the chip, plus a table of its routines at `>4080`).
Bank 1 has 128 bytes of RAM at `>4000-407F`, the blank start of u4. The chip's registers are at `>5FF0-5FFE` (a WD177x), not inverted. The
tests run the file service against this ROM on a 360K double-sided double-density disk image (`tools/ccfdc.py`, `tools/fdc.py`): that is what these
files are for. What the CRU bits do (0 ROM, 1 motor, 3 head load, 4-6 and 8 drive select, 7 side, 11 bank) was worked out from the ROM's code.

**Myarc DDCC-1 (`ddcc1.u3`).** A double-density, double-sided controller on a WD1770 or WD1772. The 8K EPROM is two banks of 4K that both appear at
`>4000-4FFF` (bank 0 the file's lower half, bank 1 its upper half; what a listing shows at `>5000-5FFF` is bank 1, linked to run in RAM); 2K of RAM sits at `>5000-57FF`,
into which the DSR copies the routines that touch the chip (they switch banks, so they cannot run from ROM). The chip's registers are at the odd addresses `>5F01`, `>5F03`,
`>5F05`, `>5F07`. CRU outputs (a latch): 0 card enable, 1 chip reset, 2 side, 3 ROM bank and density line (high = single), 4-7 drive select; CRU inputs: 0 INTRQ, 1 DRQ. The tests run the file
service against this ROM on a 360K disk (`tools/myfdc.py`). I first tried to model it from the ROM alone and was stuck on its bank-switch trampoline; the hardware description
that unstuck it is from MAME's source for the card (`myarcfdc.cpp`, Michael Zapf; LGPL-2.1+), which you supplied; the model here is written from that description, not copied from it.
The DSR first tries single density, and the model answers 'record not found' when the density asked for is not the disk's, which is how the DSR finds a double-density disk.

**Myarc HFDC (`hfdc_dsr.u34`).** A different card: a hard and floppy disk controller (devices `DSK` and `WDS`), header version `>0B`, 16K in two halves, with a controller chip
that drives both kinds of disk. Not modelled. It does not supply anything the DDCC-1 lacked (that was my misreading of the DDCC-1's bank-switching, not a missing ROM).

**Where they came from, and what you may do with them.** You supplied them on 30 October 2026 as `ti99_ccdcc.zip`, `ti99_ddcc1.zip` and `ti99_hfdc.zip`; the
archives say nothing about their authors or licence. They are the firmware of commercial cards (CorComp, Myarc) whose makers are no longer
trading; whether they may be redistributed I do not know, and **the MIT licence of this project covers the kernel's own code, not these files**. They
are here at your request so that the tests run out of the box. If a rights holder objects, delete the four files: the tests that use them
skip themselves when they are absent (`CCFDC_U3`, `CCFDC_U4` and `MYFDC_ROM` may name copies kept elsewhere), and nothing else depends on them.
