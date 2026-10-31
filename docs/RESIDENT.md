# Resident code: code every module can call

**[PC] only.** (The workbench's programs are assembled on the TI against a kernel that is already built; there is
nothing to assemble resident code into. A program for the TI route that wants a routine includes it:
`COPY "linein.a99"`.)

## The problem

A program of several modules (part 8 of the guide) often has code more than one module wants: a line editor, a
table lookup, a sort, a record formatter. A module cannot call another module's routine directly: only one module is
mapped at a time, in slot C (`>C000-DFFF`). Until now there were two ways round that, and a third is added here.

| Way | What it costs | What it cannot do |
| --- | --- | --- |
| `COPY` the source into every module that needs it | its size, once per module (LINEIN is about 930 bytes) | nothing: but the copies are separate, and a fix has to rebuild them all (the build does) |
| a **library module** and `MODCALL` | a call that maps two pages and back (the mapping changes `R0-R4`, `R7`; arguments go in `R5 R6 R8 R9` or slot A) | the routine runs with *its* module in slot C, so it cannot read the caller's tables or strings or call back into the caller's code |
| **resident code**, assembled into the kernel's pages | kernel space, shared by the whole program (about 1,050 bytes: 7,680 allowed, 6,626 used by the kernel alone) | exceed that space; and it is `[PC]` only |

Resident code is plain code in the pages that are always mapped (`>A000-BDFF`, with the kernel). A module reaches
it with an ordinary `BL @NAME` from any module, with any registers, and the routine runs while the caller's module is
still mapped: it may read the caller's tables (`RSUM` over a table in the caller's code), and call back into the
caller's code (`RCALL` with a callback in the caller's module), which `MODCALL` cannot.

## How to use it

In `app.json`:

```json
"resident": {
  "source":  "resident.a99",
  "exports": ["RSUM", "RCALL", "LINEIN"]
}
```

`resident.a99` is an ordinary source file with **no `AORG` and no `END`** (the build assembles it with the kernel, after
the kernel's own code, which `EVEN`s it). It may `COPY` the optional includes in `lib/` (`COPY "linein.a99"` carries the
line editor once for the whole program), the application's own files (`COPY "shared.a99"` for the constants the modules
share) and anything else on the kernel's include path. Every label that is listed in `exports` is added to
`kernel.equ`, so each module can `BL @RSUM`; nothing else in it is visible to the modules, so the resident code's
own labels (`RSU1`, the helper routines) cannot collide with a module's. The build reports the size:

```
kernel 7588 bytes (ends >BDA4, 92 free below the page-pool bitmap at >BE00)
  of which resident code 962 bytes (exports: RSUM RCALL LINEIN)
```

An application without `"resident"` builds exactly as before.

## Writing resident routines

- **Registers and stack** are the kernel's: `R0-R9` scratch, `R10` the software stack (256 bytes, shared with the
  caller), `R11` the return address, `R12` the CRU base; `.enter` / `.leave` / `.push` / `.pop` as in the kernel. Say in the
  routine's header comment which registers carry what and which it changes, as the kernel's routines do.
- **Labels share the kernel's namespace**: the same assembly. A label that is also a kernel label is an assembler
  error (a duplicate), so give resident labels a prefix of your own (the test uses `RS`, `RC`; `lib/linein.a99` uses
  `LN`). You may use the kernel's labels, including the ones `kernel.equ` does not export (the kernel's internal
  routines): that is a coupling to this kernel version, so prefer the public ones.
- **Data**: the code is in RAM (the kernel's pages are SAMS pages) but is loaded afresh each time the machine starts;
  keep variables in `APPRAM` (slot A: put their addresses in a `shared.a99` that the resident code and the modules both
  `COPY`).
- **Callbacks into a module** work because the caller's module is mapped. Call a module's routine only from a resident
  routine that a module of the same program called, and only a routine in that same module: another module may be mapped
  in another call.
- **Quitting, `GOMOD`, `MODCALL`**: a resident routine may call them like any routine (`MODCALL` maps another module into
  slot C, so a callback into the first module is not possible during it).

## The budget, and what to do when it runs out

The kernel may be 7,680 bytes (`>A000-BDFF`); the page-pool bitmap is at `>BE00-BFFF`. The kernel itself is 6,626 bytes:
**about 1,050 bytes for resident code**, shared with every other thing you put there. `skbuild` refuses a kernel that runs
into the bitmap and says how much of it is resident. The levers, in the order I would pull them (none is built):

1. **A smaller bitmap.** It has one bit per page for all 4,096 pages of a 16M card: 512 bytes. A program that declares the
   most pages it will ever pool (`"pool_max_pages": 256` for a 1M card) needs 32 bytes and the other 480 are resident code's.
   This changes `POOLBM` from a constant to a build-time value and `PINIT` would clamp to it.
2. **A common page.** Give every module 4K at `>C000` and a shared 4K at `>D000` that is the same page for all of them:
   4K of shared code, but modules of at most 4K (the workbench's assembler, 5,542 bytes, would not fit; Reversi, 3,392,
   would). An all-or-nothing choice per application.
3. **Trim the kernel** of what the program does not use (the music engine, the F18A modes): a per-application kernel build.

## Testing

`python3 tests/test_kernel.py resident` builds `tests/apps/resident` (two modules, `ma` and `mb`; the resident code has
`RSUM`, `RCALL` and `LINEIN`) and checks that each module gets the right answers from tables and callbacks in *its own*
code, that module B reads a line with the one resident `LINEIN`, that the exports (and nothing else) reach the modules,
and that a build refuses an export that is not a label, a resident source that is missing and a resident that does not
fit.
