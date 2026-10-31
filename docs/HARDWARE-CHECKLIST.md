# SAMS Kernel: what has been run on real hardware, and how to try the rest

Everything in this project is verified in a simulator (a TMS9900, the F18A, SAMS, a keyboard, joysticks, TI's own console and disk controller ROMs, a model of the sound chip). That finds almost every programming mistake and
none of the hardware's surprises. This list is the honest boundary, in the order I would walk it on a real machine or in js99er (F18A and SAMS on). Each step says what to do, what you should see, and what to tell me if you do not.

## Run on real hardware before (by Press and The Lantern Coast, the kernel's ancestors)

SAMS paging with a 1M-or-smaller card, the keyboard decode, the F18A 80-column text screen and colour roles, files through TI's disk controller, the FinalGROM "8" image format and bank switching. **Not** run on real hardware in this
form: the loader as rewritten, the module system, the page pool, and everything below. js99er with a 16M SAMS has run the kernel (which found the QUIT bug in 1.3.0, fixed in 1.3.1). **31 October 2026:** the project owner reports that the workbench and every example of release 1.15.0 run correctly in js99er, with its F18A setting and with its PICO9918 setting (the SAMS size and the disk setting were not recorded; 1.15.0 has `LINEIN` and resident code but not `pool_max_pages`, which came in 1.16.0). That is an emulator, not a TI: it does not show real timing, a real F18A or PICO9918, a real SAMS card or a real FinalGROM.

**Routes.** Steps 1-8 run prebuilt images (`images/`), which need a **[PC]** only to have been made: copy them to the cartridge and the disk and you can do them with no PC. Step 9 has two forms below: **[PC]** builds `tests/apps/files2`;
**[TI]** runs `COPY/A99` from the workbench disk (the same test, two files open at once). Steps 10 and 11 are **[TI]** by nature (the workbench itself).

## The walk

| # | Do | You should see | If not, tell me |
| --- | --- | --- | --- |
| 1 | Load `images/hello8.bin`. Type. FCTN = | a blue screen, a title bar, your typing echoed; FCTN = returns to the console's title screen with the display normal | which message (a refusal screen names its reason), a blank screen, or garbled colours |
| 2 | `images/skdiag8.bin`, CTRL T | eight rows, all **PASS**; the first shows the page count (128 for 512K, 256 for 1M, 512 / 1024 / ... / 4096 for bigger cards); a disk in drive 1 for the last row | which row failed; the step and error on the files row |
| 3 | Leave diag with FCTN = (**with a card above 1M if you have one**) | the console title screen; the card's mapping must be off | a hang or blank screen at the reset |
| 4 | In diag, press keys and chords | each shows its code and modifiers; CTRL 3 cycles the colour schemes | a chord with the wrong code (name it) |
| 5 | `images/videomodes8.bin`, keys `1-9 0 A-E`; FCTN = | fifteen screens, one for each display mode and option; each matches `docs/VIDEO-MODES.md` | which mode, and what it looked like; PICO9918 or F18A, and its firmware |
| 6 | `images/music8.bin`: `1`, SPACE, SPACE, `S`, `2`, `B`, `W` | the tune (three voices and a beat, about 16 s, looping), silent while paused and then the same note, an A (440 Hz), a beep, and the tune playing through a two-second "work" loop | the tune is too fast or slow, a wrong note, a hiss or click, or the noise voice too loud (a PAL console needs `"fps": 50`) |
| 7 | `images/joystick8.bin`, each joystick in each direction, and fire | the matching label goes bold; the fire count rises once a press; `1`, `2`, `3` make joystick 1, 2 or both type keys (the "Keys typed" count and the last code change; UP, DOWN, LEFT, RIGHT, ENTER are `C5 D8 D3 C4 0D`) | the wrong direction or joystick, a key that sticks, ghosting with a key held |
| 8 | `images/diskbrowser8.bin` with a disk in DSK1 | the catalog; ENTER on a text file shows it; scroll; FCTN 9 back | a hang, a wrong size or type, a garbled name |
| 9 | Several files, **[TI]**: in the workbench (the disk has a sample `SRC`), N `DSK1.COPY/A99` ENTER, A, R, ENTER; the disk then holds `DST`. **[PC]**: build `tests/apps/files2` (`python3 tools/skbuild.py tests/apps/files2`) and make a disk from two text files named `src` and `src2` (`python3 tools/skdisk.py d.dsk src src2`), then load `build/files2/files28.bin` with that disk in DSK1 | nothing on the screen; afterwards the disk holds `DST`, a copy of `SRC` (check it in your usual disk manager) | the disk controller or TIPI in use; whether `DST` is complete |
| 10 | `images/workbench8.bin` with `images/workbench.dsk` in DSK1: N `DSK1.HELLO/A99` ENTER, A, then R | "Assembled: 194 bytes at >C000", then the hello program; **time the assembly with a watch and tell me** (the simulator ran 1.9 million instructions); then restart (hello has no way back) and `BEEP/A99`: A, R, keys 1-8 play a scale, FCTN 9 returns to the workbench | the time; any error list; a hang |
| 11 | In the workbench: E on `HELLO/A99`, type a line, CTRL S, CTRL A | the edit saves and re-assembles; a mistyped mnemonic is reported with its line | an editor key that does the wrong thing |
| 12 | Cards above 1M, if you have one: step 2 again, then 6 and 10 | the page count is right and everything else as before | the first thing that differs |
| 12a | In the workbench: N `DSK1.ASK/A99` ENTER, A, R; type `ann` ENTER, `bob` ENTER, then FCTN E | `Hello, ANN`, `Hello, BOB`; FCTN E puts BOB back in the field; the arrows, FCTN 1, CTRL H and FCTN 2 edit; FCTN 9 returns | a key that does the wrong thing (name it), a field that does not redraw cleanly |

**TIPI steps** (if you have one; each is **[TI]**):

| # | Do | You should see | If not, tell me |
| --- | --- | --- | --- |
| 13 | `images/diskbrowser8.bin` with `DSK1.` mapped to a directory on the TIPI | the directory's catalog; a text file opens | whether the catalog request is answered at all |
| 14 | the workbench on the TIPI: a source in the mapped directory (or `PI.` paths), N, A, R | assembles and runs, as from a disk; includes found | the first failing name, and its error |
| 15 | `COPY/A99` with `SRC` on `DSK1.` (TIPI) and, if you also have a TI disk controller, the copy going between them | `DST` appears; with both cards present nothing hangs, whichever device is used first | which direction fails |
| 16 | `CLOCK/A99` from the workbench disk, ENTER | today's date and the time | "no clock" with a TIPI attached, or a wrong date |

## js99er's TIPI emulation and a frozen machine

js99er's TIPI setting has three values (read from its source, `tipi.ts`): **No TIPI emulation**; **Mouse** (a TIPI at CRU `>1200`, no network); **Full** (a TIPI at `>1000` whose Pi is a **websocket server**, by default `ws://localhost:9901/tipi`). In Full, js99er suspends the whole CPU whenever that websocket is closed or cannot be opened, and retries every two seconds: with nothing listening the machine freezes at start-up, before the console's menu, whatever cartridge is loaded (it was reported once for this kernel, on 31 October 2026, before the menu appeared, so it is not this software). The TIPI's own power-up pulses its reset line, which makes the proxy close the connection, so a freeze of a couple of seconds at each reset is also normal. If a machine freezes with Full emulation: set the setting to No TIPI emulation (it should run), check that the websocket server is reachable at the URI in js99er's options, and look in the browser's developer console for "TIPI websocket opened" or "closed". Mouse needs no server: **the project owner reports (31 October 2026) that the workbench runs correctly in js99er with Mouse emulation**, which puts the real TIPI DSR in the machine at `>1200` (the kernel version was not recorded; the latest delivered was 1.16.1). That shows the real TIPI DSR does not disturb the kernel; it does not show files on a TIPI, which need a Pi behind a Full-emulation websocket. The websocket URI's default is `ws://localhost:9901/tipi`; the owner's setting was thought to be a different port with nothing listening, which would freeze Full emulation as described.

## What each unverified claim rests on

| Claim | Rests on | Where it could be wrong |
| --- | --- | --- |
| a 12-bit SAMS register is the page with its bytes swapped (even byte the low 8 bits) | js99er's `ams.js` | a real card above 1M might lay the odd byte out differently |
| joysticks are keyboard columns 6 and 7, rows fire / left / right / down / up | my knowledge of the console's scan, and the simulator's model of it | the row order, or a joystick that needs a different column select |
| three files at once through the controller's three buffers; the controller finds a file by its PAB's address | TI's own disk controller ROM, running in the simulator (it did so correctly) | TIPI, CF7+ and other devices may differ |
| the music player writes the right bytes at the right frames | tests against a model of the sound chip | how it sounds; the noise model is an approximation |
| the workbench's assembler is right | byte-identical to xas99 for every example and two probe sources | an instruction or directive the examples do not use |
| TIPI: the device names, the clock record, the power-up of every card, includes in the main file's directory | the TIPI wiki as Press's design used it (Press's file speed was measured on a TIPI); a model of a TIPI in the simulator | a real TIPI's DSR, its open-file limit and its catalog |
| the page tests at power-up take about a second on a 16M card | 0.25 million instructions in the simulator | an estimate; I have not timed it |

## How to report

A short note per step is enough: the step number, what you saw, the machine (console, F18A or PICO9918 with its firmware, SAMS size and brand, disk controller or TIPI), and for emulators the version and settings. A photograph of a refusal
screen or the self-test is the best evidence there is.
