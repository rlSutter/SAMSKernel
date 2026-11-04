# Assessment: "SAMS Kernel: proposed changes for TIthon" (31 October 2026)

Assessed against kernel **1.20.0**. TIthon's document read 1.16.1; I read the specification as well (below). Where I checked a claim against the kernel's own source I say so; the sizes are
TIthon's estimates unless marked *measured* or *mine*. The kernel is now 6,738 bytes with **942 free** below the pool bitmap (FLOAD and FSAVE took 60
since 1.16.1); a program can buy more room with `"omit"`.

## Status (2 November 2026): K1 to K4 are implemented in kernel 1.21.0

| Item | State | Notes |
| --- | --- | --- |
| K1 float-safe scratchpad | **done, fully tested in 1.23.0** | `F18VER`, `NPAGES`, `QUITF` at `>8342/44/46`; `VDPPIC` at slot A `>20AA` (1.21.0). The dynamic test (group `float`, with the real console ROM in the simulator) measured every scratchpad byte the float routines change: `>834A-8353`, `>8356-8359`, `>835C-8361`, `>8365-8369`, `>8375`, `>8377`, `>837C`. None is a kernel variable. The reserved area is now all of `>834A-836F`, plus `>8374-8377` and `>837C` (1.23.1). |
| K2 frame hook | **done** | `FRMHK` `>20DA`, guard `>20DC`; `KFRAME` replaces the four `MUTICK` calls. Test `framehook`. |
| K3 break flag | **done** | `BRKF` `>20DE`, set in `KPUT` for `KCLEAR` (`>F4`; no new equate). Test `brkflag`. |
| K4 pool | **done** | byte skip in five instructions a byte (2,589 instructions at 3,900 pages used, measured, against about 107,000); `PALLOCA`. Test `poolscan` (random sequences against a model, the cost, the edges, `pool_max_pages`). The hint word was not added. |
| K5 `MAPD` / two-halves `MODCALL` | **done in 1.22.0** | designed with TXA's 4K-module request: a module declares `"size": 4096` and a header flag tells the kernel to map only `>C000`; `MAPD`, `.mapd`; `MODCALL` saves and restores `>C000` and `>D000` separately. `GOMOD` maps the second page only for an 8K module. Test group `slotd`. Kernel 6,888 bytes (+46). |
| K6 `XML` | **not needed** | `XML` is a GPL opcode; the float routines are ordinary console ROM subroutines, called directly by `FPCALL` and run as they are in the simulator |
| K6 cycle model | **done in 1.24.0** | `tools/cycles.py` (`CycleCPU`): the data manual's cycles plus 4 wait cycles for each access outside the console ROM and the scratchpad (1.24.0 said 8: corrected in 1.29.0 from TI's 99/4A technical data); matches the manual on ten instructions; DEC/JNE x 65,535 is 0.437 s in the scratchpad, 0.612 s with the code in expansion RAM, 0.786 s with the workspace there too. Not compared with a real console; use it for ratios. |
| The float call (`FPCALL`) | **done in 1.23.0** | `lib/float.a99`, 82 bytes; `FADD`, `FSUB` (ARG - FAC), `FMUL`, `FDIV` (ARG / FAC), `FCOMP` verified on 240 random operations (relative error under 1e-12) and 120 comparisons; the stack forms (`XSADD` to `XSCOMP`, 1.23.1) verified on 120 more; the second table's conversions and `ROUND` are not covered |

Kernel 6,842 bytes (+104 for the four) in 1.21.0, 6,888 with K5 in 1.22.0. Nothing was taken from the TXA proposal for this release beyond what 1.20.0 already carries (the `.mape`/`.mapf` macros, `FLOAD`/`FSAVE`).

## In short

- **The proposal is sound and small.** Its premises hold where I could check them, it asks for about 130 bytes, and it keeps to the kernel's
  conventions (labels, a test group for each change, optional where it can be).
- **K1 (float-safe scratchpad) is a real latent bug in the kernel, not only a TIthon need.** Any program that calls the console's floating-point routines
  corrupts `NPAGES`, `QUITF`, `F18VER` and `VDPPIC`. I would fix it regardless.
- **Three of TIthon's slot A addresses are already in use** by the file service (K2's `FRMHK` and its guard, K3's `BRKF`, and K1's `VDPPIC`). The fix is to
  pick other free words; there are enough (below).
- **K5 overlaps TXA's request 2.4** (a third window and a two-halves `MODCALL`). The two should be one design.
- **K6's `XML` is not a TMS9900 instruction**; it is a GPL one. The simulator part is feasible but needs saying differently, and it raises a kernel question
  (how a program calls the console's float routines at all) that the proposal does not answer.
- I would take **K1, K2, K3 and K4 together** as the next release, merge **K5** with TXA 2.4, and do **K6** as tooling in parallel.

## What the specification adds (TIthon exists only as a specification)

I have now read `TIthon_Language_Specification.pdf` (27 October 2026, 35 pages) against kernel 1.20.0. TIthon has no code yet: milestone M0 has not begun, so the
proposal is a set of requests for a design, not for a working program. That changes the **order**, not the answers: kernel changes should arrive when a TIthon milestone needs
them, unless they are cheap and useful to other programs on their own.

**Where the spec and the kernel agree** (checked): application RAM is `>2300-3EFF` (7,168 bytes) with the stack above it; `>8380-83BF` is free once the loader's copier has run; the
loader copies every bank into SAMS at start-up; Graphics II and the file service share VRAM (so files cannot be used while it shows); the page register is written with its bytes
swapped; the pool starts at `PGFREE`; the player takes songs from consecutive pages; the kernel switches the console's sprite motion off; the text routines draw in Text 80,
Text 40 and Graphics I; three file handles; `JOYGET` and `FRAME` exist as described.

**Where the spec needs updating or has a gap:**

1. **The float call itself.** The spec says floats go "through the console ROM's floating-point routines" and in its open questions mixes `GPLLNK` and `XML`. The kernel provides
   neither, and a program running in the kernel's workspace cannot simply call them: the routines are reached by the GPL `XML` dispatch with the GPL workspace (`>83E0`) and status set up,
   which the kernel's DSR calls use for their own purposes. TIthon needs a small, tested call (`FPCALL`, in an optional `lib/float.a99`) before spike B can mean anything. This is
   the most useful thing the kernel could add for M0 after K1, and the proposal does not list it.
2. **The break key.** The spec has the frame service "find FCTN-4 among the keys the kernel has buffered". That is exactly the fragility K3 removes (`KPUT` drops codes when the 64-byte
   buffer is full). The spec should use the break flag instead and drop the scan.
3. **The 64 free bytes at `>8380-83BF` are promised twice**: for the VM's hot variables ("64 free bytes ... for hot variables") and for the speech ROM-read routine ("runs from the 64 free
   scratchpad bytes"). They cannot be both.
4. **Handle misses should use the new macros.** The spec's two-window heap maps a page through `MAPE` or `MAPF` on every miss, the hottest path in the VM. Kernel 1.20.0 has `.mape` and
   `.mapf` (about 10 instructions against about 23 with the call; tested), so the cost of a miss is lower than the spec assumes. Use them; say so in the register plan (they load `R12`).
5. **The bitmap numbers the spec lacks.** `ti.BITMAP`'s size is "limited by free VRAM; M7 measures". It is known: the free run is `>2000-35FF`, **5,632 bytes** (for example 128 x 88
   fat pixels, 16 colours), because the file service's buffer and PAB sit at `>3600-37D7`. TXA has reported working settings for the bitmap layer over Text 80 (js99er only,
   with js99er's horizontal-doubling bug); see VIDEO-MODES part 10.
6. **K2 simplifies the spec.** The spec has the VM check the VDP status flag at every backward jump and call, call `KIDLE`, then run TIthon's own frame service. With K2 the VM
   calls `KIDLE` and the hook runs the frame service, in the same place for built-ins that run long (a sort, a collection, a file read). One mechanism instead of two.
7. **The register plan** uses `R13-R15` (instruction pointer, operand stack, flags) while the spec also says "the kernel advises leaving R13-R15 alone". The advice is only about
   the context-switch registers when something enters the workspace through `BLWP`; nothing in the kernel does that to `>8300` (its only `BLWP` is the reset at quit), so the plan is
   sound, and spike C's check is the right one.
8. **Code speed.** The spec's 5-10x target for a VM whose threaded code and handlers run from 8-bit expansion RAM with the dispatch loop inline is the real risk, and the question is
   where the dispatch should live (a shared `NEXT` in the 64 free scratchpad bytes, which costs a branch, against an inline `NEXT` in every handler, which fetches from slow RAM). K6's cycle
   model exists to answer it, so K6 should be ready **before M2**, not after.

**Ordering by milestone** (what each needs from the kernel):

| Milestone | Needs | So |
| --- | --- | --- |
| M0 Foundations (spikes B and C) | K1 (float-safe), the float call, K6's `XML`/GPL dispatch for the simulator | **now** |
| M1 Reference implementation | nothing | none |
| M2 VM core on the TI | K6 cycle model, K2, K3, K5 (`MAPD`, two-halves `MODCALL`) | before M2 starts |
| M3 Heap and collector | K4 (`PALLOCA`, the byte skip) | before M3 |
| M4-M9 | `FLOAD`/`FSAVE` for pictures and files (done in 1.20.0), the macros (done) | already there |

Everything cheap and independently useful (K1, K3, K4, K2) I would do in the next kernel release regardless, because it helps other programs (the workbench's abort, a hook for any
long-running program, a faster pool). K5 waits for the TXA decision on `GOMOD`; K6's tooling goes in step with TIthon's schedule.

## What I checked

| Claim | Checked against | Result |
| --- | --- | --- |
| FAC (`>834A-8351`) overlaps `F18VER`, `NPAGES`, `QUITF`, `VDPPIC` | `kdefs.a99`: `HOT` is `>8340`; `F18VER` HOT+10 (`>834A`), `NPAGES` HOT+12 (`>834C`), `QUITF` HOT+14 (`>834E`), `VDPPIC` `>8350` | **true** |
| `HOT+2`, `+4`, `+6` are free | `kdefs.a99` says so ("they held the packed slot words before 1.4.0") | **true** |
| The kernel steps the music in four places | `MUTICK` is called at `kernel.a99:64` and `keys.a99:375, 394, 412` | **true** |
| `KPUT` drops a code when the key buffer is full | `keys.a99`: `JEQ KPU9` on a full buffer | **true** |
| FCTN-4 arrives as `>F4` | `kdefs.a99`: `KCLEAR EQU >F4` | **true; and the equate already exists** |
| `MODCALL` saves only `CURCC` and restores with `PAGEC` (two consecutive pages) | `modules.a99` | **true** |
| `>20D0`, `>20D2`, `>20D4`, `>20D6` are free | `kdefs.a99` | **false**: `FRBUF`, `FRLEN`, `FEXN`, `FCRB` (the file service's scratch words, since 1.8.0) |

## Item by item

### K1. Float-safe scratchpad (about 0 bytes; **do**)
The overlap is real. The plan (`F18VER`, `NPAGES`, `QUITF` into `HOT+2/+4/+6`; `VDPPIC` out of the scratchpad) is right and costs nothing. Three notes:
- `VDPPIC` cannot go to `>20D4` (that is `FEXN`). Free slot A words today: `>20AA`, `>20AC`, `>20AE`, `>20BA`, `>20BC`, `>20BE`, `>20DA`, `>20DC`,
  `>20DE`, `>20E6`, and `>20F6-20FE`. `VDPPIC` is read by every DSR-call wrapper (the DSR calls keep it), so a slot A word is fine.
- FAC and ARG may not be all the scratchpad the float package uses. TIthon's own test (floats through the real console ROM, every other scratchpad byte
  unchanged) is the right check and I would insist on it; it is what finds a fifth variable.
- Programs and `KERNEL/EQU` files built before the change break, as with every address move; the workbench disks carry the matching `KERNEL/EQU`.
  Update the two tests that read `>834C`, `>8348` and `>834A` directly, and part 7 of the guide.

### K2. Frame hook (about 30 bytes; **do**, with other addresses)
Sound. One registered routine called from one place (`KFRAME`) in place of the four `MUTICK` calls, with a re-entrancy guard, and a hook that must be
resident (the `"resident"` of 1.15.0 exists for this). Use `>20DA` and `>20DC` for the hook and the guard. It pairs naturally with TXA's request 2.8
(a program that never returns): a hook is the clean way to keep the song, a sprite or a clock going. A note: the hook runs wherever `KIDLE` does,
including right after a DSR call and inside `KWAIT`, so it must not touch the VDP address register unless it saves it; say so in the guide.

### K3. Break flag (about 10 bytes; **do**)
`KPUT` sets `BRKF` for `>F4` before the full-buffer test and still buffers the code. Use `>20DE`, and use the existing `KCLEAR` rather than a new
`KBREAK` equate (or define `KBREAK` as an alias). The workbench's assembler (which takes up to a minute and a half on Reversi) would benefit, as TIthon says.

### K4. Faster page pool and `PALLOCA` (about 60 bytes, in the pool: omittable with it; **do**)
The slowness is real (the pool scans bit by bit from the start). The byte skip keeps the "lowest free page" result, so existing programs see no difference. Two
suggestions: make `PALLOC` a tail call into the same scan as `PALLOCA` with `R0 = POOLLO`, so the net cost is lower than 60; and say what `PALLOCA` does when `R0`
is below the pool's first page (clamp to it) or at or above its end (answer 0). The hint word can wait, as TIthon proposes.

### K5. `MAPD` and a two-halves `MODCALL` (about 30 bytes; **do, as one design with TXA 2.4**)
`MODCALL` does save one window and restore it through `PAGEC`, so a cold call overwrites `>D000`; a forgotten re-map is silent corruption, as TIthon says. TXA asked for
nearly the same thing from the other side: modules of at most 4K (`"module_size": 4096`) and a window D with `MAPD`. The two proposals disagree on one point and
must be settled once: **what does `GOMOD` do to `>D000`?** TIthon accepts that it maps the new module's pair; TXA wants only `>C000` touched. My proposal: for a program that
declares `"module_size": 4096`, `GOMOD` and `MODCALL` map only `>C000` and save and restore only that window, so window D belongs to the program; for the default 8K modules
nothing changes. `MAPD`, `.mapd` and the `CURCD` record serve both.

### K6. Simulator: cycle model and `XML` (tools, no kernel bytes; **do, reworded**)
- **Cycle model:** feasible. The simulator counts instructions; adding the data manual's cycles per instruction and wait states for accesses outside the scratchpad and the console
  ROM (a word on the 8-bit bus being two byte accesses) means hooking the memory loads and stores, a medium job. Keep the instruction count as the default, as TIthon says.
  Validation is the hard part: js99er's timing is itself a model, so a stopwatch run on a real machine is the only real check.
- **`XML`:** it is not a TMS9900 instruction. It is a GPL opcode, and an assembly program reaches the console's float routines by setting up the GPL environment (workspace
  `>83E0`, status at `>837C`) and dispatching through the console ROM's XML table (this is what the E/A cartridge's `XMLLNK` does). The simulator can dispatch it for a test, since the
  console ROM is already supported. But **someone has to provide the call from a kernel program**: a small optional include (say `lib/float.a99`, with `FPCALL`) that saves the GPL
  workspace, sets the status and dispatches. K1 makes it safe; this makes it possible. I would add it to the proposal.

## Interactions with the TXA proposal

| TIthon | TXA | One design |
| --- | --- | --- |
| K5 `MAPD`, two-halves `MODCALL` | 2.4 `"module_size"`, window D, `MAPD` | yes: settle `GOMOD` first (above) |
| K2 frame hook, `KIDLE` | 2.8 a pattern for a blocking interpreter | the hook is the mechanism, the pattern is its documentation |
| K3 break flag | 2.8 (quit handling in a VM) | a VM polls `BRKF` |
| K4 `PALLOCA` | 2.2 code in application RAM (a heap of pages) | independent |
| K1 float-safe | (none) | independent, do first |

## Order, and TIthon's open questions

Order: K1; then K2 and K3 together (same polling sites); then K4; K5 with TXA 2.4 once `GOMOD` is settled; K6 in parallel. Together K1-K4 add about 100 bytes, so a program is left
about 840 free by default; much more with `"omit"`.

TIthon's defaults, with my answers:
1. **K1 breaks old `KERNEL/EQU` files:** acceptable. Say so in `CHANGES.md` and bump the minor version.
2. **K2 one hook or a chain:** one hook; the program chains its own.
3. **K4 the hint word:** only if measurement after the byte skip demands it.
4. **K5 take it:** yes, as the shared design above.
5. **K6 fidelity:** the data manual's timings, validated by a stopwatch run on a real machine where possible; js99er as a cross-check, not an authority.
6. **Who writes the patches:** I do, against the current kernel, each with its test group, and the suite before a release.

## What I could not check

- There is no TIthon code to check: I read the proposal and, afterwards, the specification. The cost figures are TIthon's estimates except where I say otherwise.
- That FAC and ARG are all the console's float package touches: that needs the test.
- Any timing claim (the 5x target, the 90-instruction call): none has been measured against a real machine.

*Release 1.28.0 (4 November 2026): nothing in this table changed; see `CHANGES.md` for what was added since (the workbench manual, the rationale document, Press's `DSRLNK` fix and expression checker).*
