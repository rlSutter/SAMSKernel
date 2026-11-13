# Object files to RUN PROGRAM FILE (`tools/obj2ea5.py`)

`tools/obj2ea5.py` links Editor/Assembler object files into an option 5 image: PROGRAM files that the cartridge's RUN
PROGRAM FILE (and Editor/Assembler's option 5) loads and starts. It is for programs written for E/A's option 3 ("LOAD AND
RUN") that carry their own routines, and for anyone who assembles with the TI Assembler and wants a program file.

## Using it

    python3 tools/obj2ea5.py prog.obj --disk prog.dsk --name PROG            a disk with PROG, PROH, ...
    python3 tools/obj2ea5.py main.obj lib.obj -o build/PROG                   raw image files, named as E/A names them
    python3 tools/obj2ea5.py --from-disk old.dsk MAINO LIBO --disk new.dsk --name MAIN

- **Input**: object files as the TI Assembler and xas99 write them (DIS/FIX 80, the tagged format in the Editor/Assembler
  manual), plain or compressed (option C), from the PC or read off a TI disk image (`--from-disk` with the files' names).
  Several modules are loaded in the order given.
- **Placement**: absolute code (`AORG`) where it says; relocatable code from `--base` (default `>A000`, where E/A's
  loader puts it), one module after another.
- **Names**: REFs are resolved against the modules' DEFs and the console's fixed addresses that E/A also predefines
  (`VDPRD VDPSTA VDPWD VDPWA SOUND SPCHRD SPCHWT GRMRD GRMRA GRMWD GRMWA PAD GPLWS FAC ARG STATUS`).
- **Entry**: the END label. RUN PROGRAM FILE calls it with `BL`, the workspace at `>83E0`, R11 the way back to its prompt.
- **Output**: the files (`-o`) and/or a new single-density disk image with them (`--disk`, `--name`, default PROG).

## What it refuses

- **E/A's utilities** (`VSBW VMBW VSBR VMBR VWTR KSCAN GPLLNK XMLLNK DSRLNK LOADER UTLTAB`): code the Editor/Assembler
  cartridge copies into low memory. RUN PROGRAM FILE does not provide it, so a program that REFs them is refused with
  their names. `--allow-ea-utilities` links them to E/A's addresses anyway, for a machine where they will be there.
- A name nothing defines, a name defined twice, a damaged record (its checksum; `--no-checksum` loads it anyway), a tag
  it does not know, and a program with no entry (`--entry` gives one).

## The image's layout, and why

An option 5 file is a six-byte header (more files follow or not; the length; the load address) and the bytes. The
length counts the header too (xas99 writes it so), and the loader copies that many bytes: every file lays **six bytes of
whatever follows its data past its end**. So the files are written in rising address order: each one's six extra bytes
land where the next file then loads, or past the end of the program. A file is at most 8,192 bytes (8,186 of data). Gaps
of up to 256 bytes between pieces are filled with zeros; longer gaps start a new file.

The image starts where its **first** file loads. When the entry is not the program's lowest address, the first file is
a four-byte stub, `B @entry`, put where no later file's six extra bytes reach: just below the program if that is still
RAM, otherwise above the program's end and those six bytes. (Putting the file that holds the entry first, cut at the
entry, does not work: the lower part, loaded after it, lays its six extra bytes over the entry. That was the linker's
first version; the runner's test caught it.)

## Tested (simulator)

Two relocatable modules with DEFs and REFs give the same memory as xas99's own linker, in either order; compressed
objects give the same image; an absolute program the same as `xas99 -i`; the fixed names resolve; the refusals above;
a 20,002-byte program in three files; objects read off a TI disk image; and a linked program (with its start stub) run
from the cartridge's RUN PROGRAM FILE in the simulator (groups `obj2ea5` and `ea5run`).

## Not known

- That the Editor/Assembler cartridge's own option 5 runs an image with a stub file first (it should: the image is
  ordinary option 5 files; checklist L1).
- Programs that need E/A's utilities: a later version could link in replacements for the simple ones (VSBW, VMBW, VSBR,
  VMBR, VWTR); KSCAN, GPLLNK, XMLLNK and DSRLNK need the console's GROMs, which the simulator does not have.
