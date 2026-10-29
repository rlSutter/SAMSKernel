# SAMS Kernel: conventions

The rules the kernel's code follows and an application should. Each exists because breaking it has already cost a debugging
session in The Lantern Coast or Press. The programmer's guide explains them for application authors; this is the compact
list for people changing the kernel.

## Memory

- Fixed windows: slot A (`>2000-3FFF`, pages `>02-03`) is never remapped; the kernel (`>A000-BFFF`, pages `>0A-0B`) is never
  remapped; slot C (`>C000-DFFF`) is remapped only by `PAGEC`, called only from the kernel's main loop and `MODCALL`; slot B
  (`>E000-FFFF`) by `PAGEB`, `MAPE`, `MAPF`, `SETPB`, which keep `CURBE`/`CURBF`.
- Code never remaps the window it runs in.
- Every kernel variable is declared once, in `kdefs.a99`. An application declares its own as offsets from `APPRAM`, once,
  in a file its modules share.
- The stack is `>3F00-3FFF` (R10 from `>4000`).

## Registers and calling

- R0-R9 free; each routine's header lists every register it can change, **including through what it calls**.
- R10 stack (only `.enter`, `.leave`, `.push`, `.pop` change it); R11 return (`BL` overwrites it); R12 CRU (load before use);
  R13-R15 untouched (context switch and GPL workspace).
- A routine that calls another saves R11 (`.enter`/`.leave`). A leaf may `RT`, or tail-call with `B`.
- Results are in registers, never in flags, from any routine that ends with `.leave` (`.leave` is a `MOV` and sets the flags from R11).
- A value needed after a call lives in a register the callee does not use, or in memory.
- A routine's header comment is `* NAME - what it does`, then its inputs and results, then `Uses ...`. `tools/docindex.py --check`
  fails if a public routine has no header; `docs/ROUTINES.md` is generated from the headers.

## Modules

- A module starts with its entry table (`INIT`, `TICK`, `REDRAW`, reserved, then its own). Entry numbers never move.
- A module cannot call another's routines (they are not mapped): `MODCALL` (mapping in, calling, mapping back) or `GOMOD`
  (switching).
- Modules share state only through slot A addresses agreed in a shared file.
- A module may not reuse a name `kernel.equ` exports: the routines in `kernel/public.txt` and the equates in `kdefs.a99`. Every other kernel label is private (`skbuild.py` filters `kernel.equ`), so adding an internal label to the kernel cannot break an application.

## The VDP and the keyboard

- Interrupts are allowed only inside `VSYNC`; everything else runs with `LIMI 0`.
- `KPOLL`, `KIDLE`, `KPFR` may write VR1 (a key turns the display back on): call them between VDP transfers only.
- `VSHIFT` waits for the GPU; no VRAM access overlaps a DMA.
- Never write an F18A register the program does not use; `F18OFF` restores what the kernel changes. Check before unlocking.
- `VR1CPY` must hold the current mode's VR1 with the display bit set (`VMODE` sets it).
- Anything that changes an F18A register `F18OFF` does not restore must be added to `F18OFF`'s list (`OFFREG`).
- A routine added to the kernel that an application may call goes in `kernel/public.txt` and has a header comment.

## Assembly

- `xas99` evaluates expressions strictly left to right (`A+2*3` = `(A+2)*3`): parenthesise or write the constant.
- `EVEN` after byte data.
- Length-prefixed strings: use `STRI`.
- `MOVB` sets only the high byte: `CLR R0` before `MOVB` if the whole word is compared, or use `CB`.
- R0 cannot index; `XOR`/`CZC` need a register destination; `SLA Rn,0` shifts by R0's low four bits.
- A `JMP` reaches about 128 words: invert the condition around a `B @label`.
- `LI`, `MOV`, `A`, etc. set the flags: a `JEQ` after `LI R1,x` tests the `LI`.

## DSRs

- One call: GPL workspace, `>8356` at the PAB's name length, `>8354` the device name's length, the scratchpad `>8320-837F`
  saved and restored, `>8370` kept as the controller left it, the frame increment at `>83FC` restored, the previous call's error
  bits cleared, R6-R9 changed.
- The controller's power-up runs once, before the first call.

## Changing the kernel

1. `python3 tools/skbuild.py examples/diag` (and the others): no assembly errors, the kernel under 8K.
2. `python3 tests/test_kernel.py` (set `TI_CONSOLE_ROM` to your own console ROM to include the real-interrupt group).
3. `python3 tools/docindex.py --check`, then `python3 tools/docindex.py`.
4. Update the documents, `CHANGES.md`, and `VERSION` for anything an application can see.
