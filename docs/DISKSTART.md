# Starting the kernel from disk, and `PRUN`

Status: **built and tested in the simulator** (1.25.0, 3 November 2026); **not run on real hardware**. The owner decided a disk-started kernel is in scope (`docs/ROADMAP.md`).

## What it is for

A kernel application was a cartridge: a FinalGROM image whose bank 0 checks the machine, copies every bank into SAMS and starts the kernel. That excludes anyone without a FinalGROM, and a program
that *builds* programs (TXA's workbench, the kernel's own) could not hand the result to a user as something to run. A **disk start** lets a kernel application be a disk: Editor/Assembler option 5,
`DSK1.HELLO`. **`PRUN`** lets a running kernel application replace itself with another disk-started one, which is what a workbench's "run the game" needs.

## Using it

    python3 tools/skbuild.py myapp --disk                 # build/myapp/MYAPP.dsk (double density, 360K)
    python3 tools/skbuild.py myapp --disk --geometry sssd # 90K single density: for a stock TI's own controller

`app.json` may add `"disk_name": "GAME"` (1 to 6 capitals and digits; the default is the application's name cut to 6) and `"prun": true` (puts `PRUN` in the kernel: 206 bytes). The disk holds:

| File | Type | What |
| --- | --- | --- |
| `GAME` | PROGRAM, one option 5 image for `>C000` (about 4.3K) | the **bootstrap**: what you select in option 5 |
| `GAME/B01` ... `GAME/Bnn` | PROGRAM, 8,192 bytes each | the cartridge's banks after bank 0 (bank 1 is the kernel), in the cartridge's order |

A program is on one disk or volume: the bootstrap looks for `DSK1.`, `DSK2.` and `DSK3.` in turn for `GAME/B01`, or goes straight to the device it was **handed** by `PRUN`. A stock TI controller
reads single-density disks only (about 80K of files: a small application), so a real stock TI needs the `sssd` build and a small program; the CorComp, Myarc and HFDC cards, a CF7+ and a TIPI take the
double-density disk.

## How the bootstrap works (`kernel/loader.a99` assembled with `-D DISKBOOT`, and `kernel/dskboot.a99`)

It is the cartridge loader with the bank source changed, so the checks are the same code: `LIMI 0`, a mapper answers, it has `PGMIN` pages, every page from `PGDATA` up holds what is written to it, an F18A answers,
with the same refusal screens. Then, instead of copying banks from the cartridge, `DSKBOOT` reads each bank file with the kernel's own file service (`files.a99` is included in the bootstrap: `FSEL`,
`FLOAD`, the DSR lookup and the power-up of every card), which puts a PROGRAM file's bytes in VRAM; the 8K is copied to `>A000` (the kernel) or through window `>E000` into the bank table's page pair. Then
slot B goes back to its default and the bootstrap branches to `>A000`. It loads at **`>C000`** because nothing it needs lives there: the kernel goes to `>A000`, the module pages to `>E000`, and the kernel does not
need `>C000` once it has started. The 8K bank file is loaded to VRAM `>1000-2FFF`, below the file service's own buffers at `>3600`. A file that cannot be read gives a refusal screen.

The bootstrap powers up every card's DSR itself (the console did so before E/A started; the bootstrap does not rely on it, because the kernel's `DSRPWR` does the same and rebuilds the controller's buffers anyway).

## `PRUN` (`"prun": true`)

`PRUN` (R2 = a path such as `DSK2.GAME`, length-prefixed) loads the target's bootstrap file into VRAM `>2000-35FF` with `FLOAD`, checks that it is a one-file option 5 image for `>C000`, leaves a **handoff block** in the
scratchpad (`>8320-833F`: `>A55A`, the length of the device prefix (everything up to the last `.`), the prefix, `>5AA5` at `>833E`), maps the identity pages `>0C-0D` into slots C and D, copies the image to `>C000` and
jumps to it. The target's bootstrap sees the handoff block, takes its device from it instead of probing, and loads its own banks over everything: the old program is gone, the SAMS pool is rebuilt and nothing is shared (a
program that wants to pass data to its successor writes a file). If the file is not there or is not that kind of image, `PRUN` returns R0 = the DSR's error (7: not found; >FF: no such device) or >FE and the running
program goes on, its VRAM touched only in `>2000-35FF`.

## Tested (simulator, with the real DSR ROMs of the TI, CorComp, Myarc DDCC-1 and HFDC controllers)

Test groups `ea5` (an Editor/Assembler option 5 emulation, `tools/ea5.py`, and the PROGRAM-file writer and reader), `diskboot` (hello boots from a disk image through each of the four controllers; a disk without the
banks shows the refusal screen) and `prun` (ALPHA runs from disk, `G` runs BETA from the same disk; `X` tries a missing program and ALPHA goes on with the error). **Not tested: a real machine.**

## Assumed, not known (to be tried on a real TI: `docs/HARDWARE-CHECKLIST.md`)

- Option 5 runs a one-file image from its load address with the console ROM, a 32K RAM, a SAMS card with its mapper off (or left in any state: the bootstrap's `AMSINI` sets the identity map first) and a disk controller.
- With the mapper off the 32K RAM at `>A000-FFFF` is the same RAM that SAMS pages `>0A-0F` show under the identity map (the cartridge loader already depends on this for its kernel copy).
- The DSR LOAD of an 8K PROGRAM file works on every controller the kernel's file service supports; the simulator runs four of them. A TIPI and a CF7+ have not been tried even in the simulator.
- The time to read a program from a floppy is not known; the simulator does not model the drive's speed.

## What is not done

- Two small modules in one bank (a program is the cartridge's banks, one file each).
- A bootstrap that finds its own name, so the device probing is DSK1 to DSK3 only (a device the program is not on, such as a TIPI path, works only through `PRUN`'s handoff).
- Passing data to the successor program other than through files.
