import os
#!/usr/bin/env python3
"""Headless TMS9900 + TI-99/4A + SAMS + F18A simulator (carried from Press 2.0).

Carried over from The Lantern Coast and extended for Press:
  - F18A Text 80 mode (VR0 bit 2 with M1), the 30-row setting (VR49 bit 6),
    per-position attributes in text mode (VR50 bit 1), status register 14
    (the firmware version), the stop-sprite register (VR51);
  - SAMS of any size up to 1M (--pages N), or none at all (--no-sams: a plain
    32K card, no mapper);
  - keyboard chords: SHIFT, FCTN and CTRL with any key, ALPHA LOCK on CRU
    input 7 while output 21 is low (as js99er), held keys for auto-repeat;
  - key scripts: plain characters type themselves (capitals with SHIFT),
    <C-x> CTRL, <F-x> FCTN, <S-x> SHIFT, <ENTER>, <SPACE>, <ALPHA> toggles
    ALPHA LOCK, <WAIT n> waits n frames, <HOLD n> makes the next key a hold
    of n frames.

The VDP raises status bit 7 every VSYNC_INSNS instructions (a "frame").

Usage: sim9900.py CART.bin [--no-f18a] [--no-sams] [--pages N]
                  [--keys SCRIPT] [--frames N]
"""
import sys

VSYNC_INSNS = 3000
KEY_AT_FRAME = 60      # first scripted key goes down at this frame
KEY_HOLD_FRAMES = 6    # a plain key is held this long ...
KEY_GAP_FRAMES = 6     # ... then released this long
KTAB = ["= \r\0\0\0\0\0", ".LO92SWX", ",KI83DEC", "MJU74FRV", "NHY65GTB", "/;P01AQZ"]

# (column, row) of each key; rows are CRU inputs 3-10 minus 3
KEYPOS = {}
for _c, _col in enumerate(KTAB):
    for _r, _ch in enumerate(_col):
        if _ch not in '\0': KEYPOS[_ch] = (_c, _r)
KEYPOS['ENTER'] = (0, 2); KEYPOS['SPACE'] = (0, 1)
FCTN, SHIFT, CTRL = (0, 4), (0, 5), (0, 6)
MODIFIERS = frozenset([FCTN, SHIFT, CTRL])
# joysticks 1 and 2 are read as keyboard columns 6 and 7; the rows are fire, left, right, down, up (0 = active)
JOYROW = {'FIRE': 0, 'LEFT': 1, 'RIGHT': 2, 'DOWN': 3, 'UP': 4}
SHIFTED = {'!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8',
           '(': '9', ')': '0', '+': '=', '<': ',', '>': '.', ':': ';', '-': '/'}
FCTNED = {'|': 'A', '`': 'C', '{': 'F', '}': 'G', '?': 'I', "'": 'O', '"': 'P', '[': 'R',
          ']': 'T', '_': 'U', '~': 'W', '\\': 'Z'}

def chord_of(ch):
    """The set of keys held to type one character."""
    if ch == ' ': return frozenset([KEYPOS['SPACE']])
    if ch.isalpha() and ch.isupper(): return frozenset([SHIFT, KEYPOS[ch]])
    if ch.isalpha(): return frozenset([KEYPOS[ch.upper()]])
    if ch in SHIFTED: return frozenset([SHIFT, KEYPOS[SHIFTED[ch]]])
    if ch in FCTNED: return frozenset([FCTN, KEYPOS[FCTNED[ch]]])
    if ch in KEYPOS: return frozenset([KEYPOS[ch]])
    raise SystemExit(f"no key {ch!r}")

def parse_keys(script):
    """A key script -> list of events (kind, frames, chord): kind 'key' holds
    the chord for frames then releases for KEY_GAP_FRAMES; 'wait' idles;
    'alpha' toggles ALPHA LOCK."""
    ev, i, hold = [], 0, None
    while i < len(script):
        c = script[i]
        if c == '<':
            j = script.index('>', i)
            tok = script[i + 1:j]; i = j + 1
            if tok.startswith('WAIT '): ev.append(('wait', int(tok[5:]), None)); continue
            if tok.startswith('HOLD '): hold = int(tok[5:]); continue
            if tok == 'ALPHA': ev.append(('alpha', 0, None)); continue
            if len(tok) > 3 and tok[0] == 'J' and tok[1] in '12' and tok[2] == '-':     # a joystick: <J1-LEFT+FIRE>
                chord = frozenset((5 + int(tok[1]), JOYROW[d]) for d in tok[3:].split('+'))
            elif tok in ('ENTER', 'SPACE'): chord = frozenset([KEYPOS[tok]])
            elif len(tok) >= 3 and tok[1] == '-':
                mod = {'C': CTRL, 'F': FCTN, 'S': SHIFT}[tok[0]]
                k = tok[2:]
                k = 'SPACE' if k == 'SPACE' else ('ENTER' if k == 'ENTER' else k.upper())
                chord = frozenset([mod, KEYPOS[k]])
            else:
                raise SystemExit(f"bad key token <{tok}>")
        else:
            chord = chord_of(c); i += 1
        ev.append(('key', hold or KEY_HOLD_FRAMES, chord)); hold = None
    return ev

def schedule(events, start=KEY_AT_FRAME):
    gap = KEY_GAP_FRAMES
    """Events -> list of (first frame, last frame, chord) presses and a list of
    ALPHA LOCK toggle frames; returns (presses, toggles, end frame)."""
    f, presses, toggles = start, [], []
    for kind, n, chord in events:
        if kind == 'wait': f += n
        elif kind == 'alpha': toggles.append(f)
        else:
            presses.append((f, f + n, chord)); f += n + gap
    return presses, toggles, f

class Halt(Exception):
    pass

class Machine:
    def __init__(self, cart, f18a=True, pages=128, sams=True, f18a_version=0x19):
        self.cart = cart
        self.nbanks = len(cart) // 0x2000
        self.bank = 0
        self.scratch = bytearray(256)
        self.sams = sams
        self.dvfiles = {}       # the stand-in drive's files: name -> records
        self.prints = {}        # printer devices (PIO..., PI.PIO...): full name -> bytes written, in order
        self.pi_clock = None    # PI.CLOCK's reply (a string), or None: no clock
        self.ftypes = {}        # name -> (variable?, internal?, record length); DIS/VAR 80 if absent
        self.bad_pages = set()
        self.console_rom = None  # the user's own 8K console ROM (bytes): the real interrupt routine runs
        self.isr_count = 0
        self.f18a_version = f18a_version
        self.ams = bytearray(4096 * max(pages, 128))
        if os.environ.get('SIM_RANDOM_RAM'):              # as at a real power-up: RAM is not zeroed
            import random as _r
            _g = _r.Random(int(os.environ['SIM_RANDOM_RAM']))
            self.ams[:] = bytes(_g.randrange(256) for _ in range(len(self.ams)))
        self.pages = pages           # physical pages actually present
        self.map = list(range(16))   # window -> page
        self.ams_regs_visible = False
        self.wide_regs = False       # True: the card's registers are 12 bits (a 16M SAMS)
        self.ams_mapping = False
        self.f18a = f18a
        self.vram = bytearray(16384)
        self.vregs = [0] * 64
        self.vaddr = 0
        self.vlatch = None
        self.vstatus = 0
        self.unlock = 0
        self.unlocked = False
        self.palette = {}
        self.pal_mode = None
        self.grom_addr = 0
        self.grom_latch = None
        self.grom = bytearray(0x2000)
        try:                                   # a readable stand-in for the console font
            from simfont import FONT
            for n, rows in enumerate(FONT):
                for y, b in enumerate(rows):
                    self.grom[0x6B4 + n * 7 + y] = b
        except ImportError:
            for i in range(0x6B4, 0x6B4 + 64 * 7):
                self.grom[i] = 0x7E if (i - 0x6B4) % 7 else 0x3C
        self.insns = 0
        self.presses = []       # scripted presses: (first frame, last frame, chord)
        self.toggles = []       # frames at which ALPHA LOCK is toggled
        self.held = None        # a chord (set of (col,row)) held directly by a driver script
        self.alpha = True       # ALPHA LOCK down (as js99er starts)
        self.cru21 = 0          # 9901 output 21: low selects ALPHA LOCK onto input 7
        self.vint = False       # VDP interrupt pending (level-triggered until serviced)
        self.blanked = False    # set if the console ISR ever blanked the screen
        self.sound_log = []     # bytes written to the sound chip by the ISR's list player
        self.cpu_sound = []     # bytes the game itself writes to the sound chip (effects)
        self.chip_log = []      # both, in order: (source, instruction count, byte)
        # a fake disk controller DSR at CRU >1100: ROM header, a DSR list
        # entry "DSK1" whose code is the trap opcode >0180, and a no-op
        # power-up routine.  File I/O goes to disk_dir/DSK1/<name>.
        self.dsr_on = False
        self.disk_dir = None
        self.tifdc = None       # a tools/tifdc.TIFDC: the real TI controller's DSR in place of the stand-in
        # a second card at CRU >1000, a MODEL of a TIPI (not its DSR): the device "PI", a power-up routine that
        # sets pi_powered, and (pi_files) PI.<path> as files, kept in dvfiles under "PI:<path>"; PI.CLOCK and
        # PI.PIO as for the stand-in.  Set pi_card = True to put it in the machine.
        self.pi_card = False
        self.pi_on = False
        self.pi_powered = False
        self.pi_files = False
        pirom = bytearray(0x2000)
        pirom[0:4] = b'\xAA\x01\x00\x00'
        pirom[4:6] = (0x4040).to_bytes(2, 'big'); pirom[8:10] = (0x4010).to_bytes(2, 'big')
        pirom[0x10:0x12] = b'\x00\x00'; pirom[0x12:0x14] = (0x4050).to_bytes(2, 'big'); pirom[0x14:0x17] = b'\x02PI'
        pirom[0x40:0x42] = b'\x00\x00'; pirom[0x42:0x44] = (0x4060).to_bytes(2, 'big')
        for i, w in enumerate((0x0180, 0x1302, 0x05CB, 0x045B, 0x045B)):
            pirom[0x50 + 2 * i: 0x52 + 2 * i] = w.to_bytes(2, 'big')
        for i, w in enumerate((0x0181, 0x045B)):
            pirom[0x60 + 2 * i: 0x62 + 2 * i] = w.to_bytes(2, 'big')
        self.pirom = pirom
        rom = bytearray(0x2000)
        rom[0:4] = b'\xAA\x01\x00\x00'
        rom[4:6] = (0x4020).to_bytes(2, 'big'); rom[8:10] = (0x4010).to_bytes(2, 'big')
        rom[0x10:0x12] = (0x4050).to_bytes(2, 'big'); rom[0x12:0x14] = (0x4030).to_bytes(2, 'big'); rom[0x14:0x19] = b'\x04DSK1'
        # printer devices for M4: "PIO" (the parallel port) and "PI" (TIPI: PI.PIO,
        # PI.CLOCK), the same trap; what is written to them is kept in self.prints
        rom[0x50:0x52] = (0x4060).to_bytes(2, 'big'); rom[0x52:0x54] = (0x4030).to_bytes(2, 'big'); rom[0x54:0x58] = b'\x03PIO'
        rom[0x60:0x62] = b'\x00\x00'; rom[0x62:0x64] = (0x4030).to_bytes(2, 'big'); rom[0x64:0x67] = b'\x02PI'
        rom[0x20:0x22] = b'\x00\x00'; rom[0x22:0x24] = (0x4040).to_bytes(2, 'big'); rom[0x24] = 0
        for i, w in enumerate((0x0180, 0x1302, 0x05CB, 0x045B, 0x045B)):
            rom[0x30 + 2 * i: 0x32 + 2 * i] = w.to_bytes(2, 'big')
        rom[0x40:0x42] = (0x045B).to_bytes(2, 'big')
        self.dsrrom = rom

    # ---- memory ------------------------------------------------------
    def page_of(self, addr):
        w = addr >> 12
        if not self.sams: return w
        p = self.map[w] if self.ams_mapping else w
        return p % self.pages

    def rb(self, addr):
        addr &= 0xFFFF
        if addr < 0x2000 and self.console_rom is not None:
            return self.console_rom[addr]
        if addr < 0x2000:
            # the console ROM is not distributed: a filler stands in, never zero,
            # so code that reads here by mistake sees junk as on a real TI (a
            # zero filler hid the help screen's lost pointer, 23 October 2026)
            return 0x80 | ((addr * 37) & 0x7F)
        if addr < 0x4000 or addr >= 0xA000:
            return self.ams[self.page_of(addr) * 4096 + (addr & 0xFFF)]
        if addr < 0x6000:
            if self.sams and self.ams_regs_visible and addr < 0x4020:
                return self.map[(addr - 0x4000) >> 1]
            if self.pi_on:
                return self.pirom[addr - 0x4000]
            if self.tifdc is not None and self.tifdc.rom_on:
                return self.tifdc.read(addr)
            if self.dsr_on:
                return self.dsrrom[addr - 0x4000]
            return 0
        if addr < 0x8000:
            off = self.bank * 0x2000 + (addr - 0x6000)
            return self.cart[off] if off < len(self.cart) else 0
        if 0x8300 <= addr < 0x8400:
            return self.scratch[addr - 0x8300]
        if addr == 0x8800:                       # VDP read data
            v = self.vram[self.vaddr]
            self.vaddr = (self.vaddr + 1) & 0x3FFF
            return v
        if addr == 0x8802:                       # VDP status
            if self.f18a and self.unlocked and self.vregs[15] == 1:
                return 0xEA if getattr(self, 'pico', False) else 0xE0   # a PICO9918: >E8, blanking bit live
            if self.f18a and self.unlocked and self.vregs[15] == 14:
                return 0x1A if getattr(self, 'pico', False) else self.f18a_version
            if self.f18a and self.unlocked and self.vregs[15] == 2:
                return 0x00                       # GPU status: idle (it runs to IDLE at once)
            s = self.vstatus
            self.vstatus = 0
            return s
        if addr == 0x9800:                       # GROM read
            v = self.grom[self.grom_addr & 0x1FFF]
            self.grom_addr = (self.grom_addr + 1) & 0xFFFF
            return v
        return 0

    def wb(self, addr, val):
        addr &= 0xFFFF
        val &= 0xFF
        if addr < 0x2000:
            return
        if addr < 0x4000 or addr >= 0xA000:
            pg = self.page_of(addr)
            if pg in self.bad_pages:                 # a test: a page that does not hold what is written
                return
            self.ams[pg * 4096 + (addr & 0xFFF)] = val
            return
        if addr < 0x6000:
            if self.sams and self.ams_regs_visible and addr < 0x4020:
                i = (addr - 0x4000) >> 1
                if self.wide_regs:       # a card of more than 1M: 12 bits, the even byte the low 8, the odd byte bits 8-11 (as js99er)
                    self.map[i] = (self.map[i] & 0x0FF) | ((val & 0x0F) << 8) if addr & 1 else (self.map[i] & 0xF00) | val
                elif not addr & 1:       # a card of 1M: the even byte is the page; the odd byte is ignored
                    self.map[i] = val
            elif self.tifdc is not None and self.tifdc.rom_on:
                self.tifdc.write(addr, val)
            return
        if addr < 0x8000:
            b = (addr - 0x6000) >> 1
            if b < self.nbanks:
                self.bank = b
            return
        if 0x8300 <= addr < 0x8400:
            self.scratch[addr - 0x8300] = val
            return
        if addr == 0x8C00:                       # VDP write data
            if self.pal_mode is not None:
                idx, hi = self.pal_mode
                if hi is None:
                    self.pal_mode = (idx, val)
                else:
                    self.palette[idx] = (hi << 8) | val
                    self.pal_mode = (idx + 1, None)
                return
            self.vram[self.vaddr] = val
            self.vaddr = (self.vaddr + 1) & 0x3FFF
            self.vlatch = None
            return
        if addr == 0x8C02:                       # VDP address / register
            if self.vlatch is None:
                self.vlatch = val
                return
            lo, hi = self.vlatch, val
            self.vlatch = None
            if hi & 0x80:
                reg = hi & 0x3F if (self.f18a and self.unlocked) else hi & 0x07
                if self.f18a and (hi & 0x3F) == 57:
                    # as js99er's F18A (and the real one): locked, two writes in a
                    # row with >1C set unlock it; unlocked, ANY write to VR57 locks
                    # it again (an unlock sequence sent to an unlocked F18A locks it)
                    if not self.unlocked:
                        old = self.vregs[57]
                        self.vregs[57] = lo
                        if (old & 0x1C) == 0x1C and (lo & 0x1C) == 0x1C:
                            self.unlocked = True
                    else:
                        self.vregs[57] = 0
                        self.unlocked = False
                    return
                self.vregs[reg] = lo
                # every register write kept (the tests look for stray ones: a VRAM
                # address past >3FFF looks like one to a real VDP, while this
                # simulator would otherwise wrap it quietly)
                self.__dict__.setdefault('regwrites', []).append((reg, lo))
                if reg == 1:
                    self.__dict__.setdefault('vr1_writes', []).append((self.vregs[0], lo))
                if reg == 47 and self.f18a and self.unlocked:
                    self.pal_mode = ((lo & 0x3F), None) if lo & 0x80 else None
                if reg == 55 and self.f18a and self.unlocked:
                    self.run_gpu((self.vregs[54] << 8) | lo)
            else:
                self.vaddr = ((hi & 0x3F) << 8) | lo
            return
        if addr == 0x9C02:                       # GROM address, high first
            if self.grom_latch is None:
                self.grom_latch = val
            else:
                self.grom_addr = (self.grom_latch << 8) | val
                self.grom_latch = None
            return
        if 0x8400 <= addr < 0x8600:              # the sound chip: the CPU's own writes
            self.cpu_sound.append(val); self.chip_log.append(('cpu', self.insns, val))
            return
        # others: ignore

    def rw(self, addr):
        addr &= 0xFFFE
        return (self.rb(addr) << 8) | self.rb(addr + 1)

    def ww(self, addr, val):
        addr &= 0xFFFE
        self.wb(addr, val >> 8)
        self.wb(addr + 1, val & 0xFF)

    # ---- CRU ---------------------------------------------------------
    def console_isr(self, cpu):
        """What the console's level-1 routine at >0900 does that matters here,
        modelled faithfully enough to catch mistakes with it:
        - reads the VDP status (clears the flag and resets the address latch);
        - advances the timer at >8379;
        - plays the sound list at >83CC one block per frame when >83CE counts
          down to zero: from VDP RAM when bit 0 of >83FD is set (it sets the VDP
          read address to do so, which clobbers any transfer in progress), from
          GROM otherwise.  A size byte of >00 (or >FF, which also switches memory)
          is a branch: the next two bytes become the list address and nothing
          sounds until the next frame.  A duration of 0 ends the list
          (after Nouspikel, TI-99/4A Tech Pages, "Interrupts");
        - adds 2 to the screen timer at >83D6 and blanks the display (VR1 from
          the copy at >83D4, display bit cleared) when it wraps to zero."""
        self.vstatus &= 0x7F
        self.vlatch = None
        self.scratch[0x79] = (self.scratch[0x79] + 1) & 0xFF
        dur = self.scratch[0xCE]
        if dur:
            dur -= 1
            if dur == 0:
                ptr = (self.scratch[0xCC] << 8) | self.scratch[0xCD]
                in_vram = self.scratch[0xFD] & 1
                def rd(a):
                    if in_vram:
                        self.vaddr = (a + 1) & 0x3FFF       # the ISR's own VDP read
                        return self.vram[a & 0x3FFF]
                    return self.grom[a & 0x1FFF]
                n = rd(ptr); ptr += 1
                if n in (0x00, 0xFF):                    # a branch order: the next two bytes are the new
                    ptr = (rd(ptr) << 8) | rd(ptr + 1)   # address; no sounds change until the next frame
                    if n == 0xFF: self.scratch[0xFD] ^= 1       # (>FF also switches VDP <-> GROM)
                    dur = 1
                else:
                    for i in range(n):
                        b = rd(ptr); ptr += 1
                        self.sound_log.append(b); self.chip_log.append(('isr', self.insns, b))
                    dur = rd(ptr); ptr += 1              # a duration of 0 ends the list
                self.scratch[0xCC] = (ptr >> 8) & 0xFF; self.scratch[0xCD] = ptr & 0xFF
            self.scratch[0xCE] = dur
        t = ((self.scratch[0xD6] << 8) | self.scratch[0xD7]) + 2
        t &= 0xFFFF
        self.scratch[0xD6] = t >> 8; self.scratch[0xD7] = t & 0xFF
        if t == 0:
            self.vregs[1] = self.scratch[0xD4] & 0xBF
            self.blanked = True

    def cru_write(self, bit, v):
        if self.tifdc is not None and 0x880 <= bit < 0x888:
            self.tifdc.cru_write(bit - 0x880, v)
            return
        if bit == 0xF00:          # >1E00 / 2
            self.ams_regs_visible = bool(v)
        elif bit == 0xF01:
            self.ams_mapping = bool(v)
        elif bit == 0x880:        # >1100 / 2: the fake disk controller ROM
            self.dsr_on = bool(v)
        elif bit == 0x800 and self.pi_card:     # >1000 / 2: the model of a TIPI
            self.pi_on = bool(v)
        elif bit == 21:           # 9901 output 21: ALPHA LOCK select (active low)
            self.cru21 = v

    def dsr_trap(self, cpu):
        """Perform the PAB operation that the fake DSK1 DSR was called for.
        Returns True when it handled the call (the DSR then returns to R11+2),
        which may still carry an error code in the PAB's flag byte, as a missing
        file does on a real controller; False (return to R11) when the device is
        not its own."""
        # A real DSR is GPL-called code: it runs in the GPL workspace (>83E0) and
        # reaches the VDP and GROM through that workspace's R15 (>8C02) and R13
        # (>9800). Called any other way its VDP traffic goes astray: it does
        # nothing useful, yet still returns as if it had handled the call.
        if getattr(self, 'dsr_strict_ws', True) and (cpu.wp != 0x83E0 or self.rw(0x83FE) != 0x8C02 or self.rw(0x83FA) != 0x9800):
            return True
        import os
        # as a real DSR finds it: >8356 points at the '.' after the device name
        # (DSRLNK moves it there) and >8354 holds the device name's length
        pab = self.rw(0x8356) - self.rw(0x8354) - 10
        op = self.vram[pab]; buf = (self.vram[pab + 2] << 8) | self.vram[pab + 3]
        count = (self.vram[pab + 6] << 8) | self.vram[pab + 7]
        nlen = self.vram[pab + 9]
        name = bytes(self.vram[pab + 10: pab + 10 + nlen]).decode('ascii', 'replace')
        dev, _, fname = name.partition('.')
        def fail(code):
            self.vram[pab + 1] = (self.vram[pab + 1] & 0x1F) | (code << 5)
            if getattr(self, 'dsr_silent', False):          # a DSR that fails without saying so
                self.vram[pab + 1] &= 0x1F
            return False
        # a DSR may move the name pointer on while it parses the rest of the name:
        # a caller must not find the PAB through >8356 afterwards
        if getattr(self, 'dsr_moves_ptr', True):
            p = self.rw(0x8356) + 1; self.scratch[0x56] = (p >> 8) & 0xFF; self.scratch[0x57] = p & 0xFF
        if op in (0, 1, 2, 3, 7) and dev == 'DSK1':
            return self.record_op(pab, op, buf, fname, fail)
        if dev == 'PI' and self.pi_files and fname.split('.')[0] not in ('CLOCK', 'PIO') and op in (0, 1, 2, 3, 7):
            return self.record_op(pab, op, buf, 'PI:' + fname, fail)
        if dev in ('PIO', 'PI'):
            return self.printer_op(pab, op, buf, count, name, fname, fail)
        if self.disk_dir is None or dev != 'DSK1':
            return fail(0)
        path = os.path.join(self.disk_dir, 'DSK1', fname)
        if op == 6:                                   # SAVE
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = bytearray(self.vram[buf: buf + count])
            if getattr(self, 'dsr_corrupt', False) and len(data) > 20:
                data[20] ^= 0xFF; self.dsr_corrupt = False   # a test: spoil one save
            open(path, 'wb').write(bytes(data))
            return True
        if op == 5:                                   # LOAD
            if not os.path.exists(path):              # as a real controller does: it handled
                fail(7)                               # the call (the skip return) and reports
                return True                           # the error in the PAB's flag byte
            data = open(path, 'rb').read()[:count]
            self.vram[buf: buf + len(data)] = data
            return True
        return fail(0)

    def run_gpu(self, pc):
        """The F18A GPU, started by a write to VR55: a TMS9900 whose memory is
        VRAM (>0000->3FFF), GPU RAM, and the DMA registers at >8000 (a write to
        >8008 starts a DMA copy or fill, as js99er does it).  Runs to IDLE."""
        m = self
        class GPUMem:
            def __init__(g):
                g.ram = bytearray(0x10000); g.insns = 0; g.vregs = [0] * 64; g.vint = False
                g.tifdc = None; g.dsr_on = False
            def rb(g, a):
                a &= 0xFFFF
                return m.vram[a] if a < 0x4000 else g.ram[a]
            def wb(g, a, v):
                a &= 0xFFFF; v &= 0xFF
                if a < 0x4000:
                    m.vram[a] = v
                else:
                    g.ram[a] = v
                    if a == 0x8008:
                        g.dma()
            def rw(g, a):
                a &= 0xFFFE
                return (g.rb(a) << 8) | g.rb(a + 1)
            def ww(g, a, v):
                a &= 0xFFFE
                g.wb(a, v >> 8); g.wb(a + 1, v & 0xFF)
            def cru_read(g, b): return 1
            def cru_write(g, b, v): pass
            def dma(g):
                if getattr(m, 'no_dma', False):           # a test: an F18A without the DMA engine
                    return
                r = g.ram
                src = (r[0x8000] << 8) | r[0x8001]; dst = (r[0x8002] << 8) | r[0x8003]
                width = r[0x8004] or 0x100; height = r[0x8005] or 0x100; stride = r[0x8006]
                d = 1 if (r[0x8007] & 2) == 0 else -1
                wm1 = width - 1
                diff = ((((stride - wm1) if d == 1 else (wm1 - stride)) & 0xFF) ^ 0x80) - 0x80
                pitch = wm1 * d + diff
                copy = (r[0x8007] & 1) == 0
                fillb = m.vram[src & 0x3FFF]
                for y in range(height):
                    s_, d_ = src, dst
                    for x in range(width):
                        m.vram[d_ & 0x3FFF] = m.vram[s_ & 0x3FFF] if copy else fillb
                        s_ += d; d_ += d
                    src += pitch; dst += pitch
                m.dma_count = getattr(m, 'dma_count', 0) + 1
        gm = GPUMem()
        gpu = CPU(gm)
        gpu.wp = 0xF000
        gpu.pc = pc
        for _ in range(100000):
            if gm.rw(gpu.pc) == 0x0340:          # IDLE
                return
            gpu.step()
        raise Halt('GPU did not reach IDLE')

    def printer_op(self, pab, op, buf, count, name, fname, fail):
        """A printer device (PIO, PI.PIO) or TIPI's clock (PI.CLOCK).  OPEN for
        output starts a capture under the full name; WRITE appends the record's
        bytes (the device options, .CR and so on, are part of the name and are
        not acted on: the tests compare raw bytes); CLOSE ends it.  PI.CLOCK
        opened for input reads one record, self.pi_clock, if set."""
        if not hasattr(self, 'phandles'):
            self.phandles = {}
        if name.startswith('PI.') and fname.split('.')[0] == 'CLOCK':
            if op == 0:
                if self.pi_clock is None:
                    return fail(7)
                self.phandles[pab] = 'clock'
                return True
            if op == 2:
                data = self.pi_clock.encode()
                self.vram[buf:buf + len(data)] = data
                self.vram[pab + 5] = len(data)
                return True
            if op == 1:
                self.phandles.pop(pab, None)
                return True
            return fail(3)
        if name.startswith('PI.') and fname.split('.')[0] != 'PIO':
            return fail(0)
        if op == 0:
            self.phandles[pab] = name
            self.prints.setdefault(name, bytearray())
            return True
        if op == 3:
            n = self.vram[pab + 5]
            self.prints.setdefault(self.phandles.get(pab, name), bytearray()).extend(self.vram[buf:buf + n])
            return True
        if op == 1:
            self.phandles.pop(pab, None)
            return True
        return fail(3)

    def record_op(self, pab, op, buf, fname, fail):
        """OPEN / CLOSE / READ / WRITE / DELETE on the stand-in drive's files
        (self.dvfiles: name -> records; self.ftypes: name -> (variable?,
        internal?, record length), DIS/VAR 80 when absent), as a TI disk
        controller does them: wrong attributes on OPEN are error 2, a missing
        file for input error 7, reading past the end error 5.  OPEN of the
        device alone ("DSK1.") for input as INT/FIX 38 reads the catalog.
        Errors go in the PAB's flag byte with the skip return."""
        flags = self.vram[pab + 1]
        handles = self.__dict__.setdefault('dvopen', {})
        var, internal = bool(flags & 0x10), bool(flags & 0x08)
        if op == 0:                                   # OPEN
            mode = (flags >> 1) & 3                   # 0 update, 1 output, 2 input, 3 append
            reclen = self.vram[pab + 4]
            if fname == '':                           # the catalog
                if mode != 2 or var or not internal or reclen not in (0, 38):
                    fail(2); return True
                self.vram[pab + 4] = 38
                handles[pab] = {'name': None, 'mode': 'in', 'pos': 0, 'recs': self.catalog()}
                return True
            if mode == 2:
                if fname not in self.dvfiles:
                    fail(7); return True
                fv, fi, fl = self.ftypes.get(fname, (True, False, 80))
                if (fv, fi) != (var, internal) or (reclen and reclen != fl):
                    fail(2); return True
                self.vram[pab + 4] = fl
                handles[pab] = {'name': fname, 'mode': 'in', 'pos': 0, 'recs': self.dvfiles[fname]}
            elif mode == 1:
                if not reclen:
                    reclen = 80
                    self.vram[pab + 4] = reclen
                handles[pab] = {'name': fname, 'mode': 'out', 'recs': [], 'type': (var, internal, reclen)}
            else:
                fail(3); return True
            return True
        if op == 7:                                   # DELETE
            if fname not in self.dvfiles:
                fail(7); return True
            del self.dvfiles[fname]
            self.ftypes.pop(fname, None)
            return True
        h = handles.get(pab)
        if h is None:
            fail(7); return True
        if op == 1:                                   # CLOSE
            if h['mode'] == 'out':
                self.dvfiles[h['name']] = h['recs']
                self.ftypes[h['name']] = h['type']
            del handles[pab]
            return True
        if op == 2:                                   # READ
            recs = h['recs']
            if h['pos'] >= len(recs):
                fail(5); return True
            r = recs[h['pos']]; h['pos'] += 1
            n = len(r)
            if not h['name'] is None:
                fv, fi, fl = self.ftypes.get(h['name'], (True, False, 80))
                if not fv:                            # fixed records come back full length
                    r = r.ljust(fl, b'\0'); n = fl
            self.vram[buf:buf + len(r)] = r
            self.vram[pab + 5] = n
            return True
        if op == 3:                                   # WRITE
            var_, int_, rl = h['type']
            n = self.vram[pab + 5] if var_ else rl
            r = bytes(self.vram[buf:buf + n])
            if getattr(self, 'corrupt_write', None) == len(h['recs']) and r:
                r = bytes([r[0] ^ 1]) + r[1:]              # a test: this record goes bad on the disk
            h['recs'].append(r)
            return True
        return fail(3)

    def catalog(self):
        """The catalog as INT/FIX 38 records: the disk, then each file (name,
        type, sectors, record length as radix-100 numbers), then an empty
        name."""
        def num(v):
            if v == 0:
                return bytes([8]) + bytes(8)
            neg, v = v < 0, abs(v)
            digits = []
            while v:
                digits.insert(0, v % 100); v //= 100
            b = bytearray([0x40 + len(digits) - 1] + digits + [0] * (8 - 1 - len(digits)))
            if neg:
                w = (b[0] << 8) | b[1]
                w = (-w) & 0xFFFF
                b[0], b[1] = w >> 8, w & 0xFF
            return bytes([8]) + bytes(b)
        def rec(name, a, b, c):
            n = name.encode()
            return (bytes([len(n)]) + n + num(a) + num(b) + num(c)).ljust(38, b'\0')
        out = [rec('PRESSDISK', 0, 1440, 1440 - 2 - sum(1 + (sum(len(r) + 1 for r in rs) + 255) // 256
                                                         for rs in self.dvfiles.values()))]
        for name in sorted(self.dvfiles):
            fv, fi, fl = self.ftypes.get(name, (True, False, 80))
            t = (2 if fv else 1) + (2 if fi else 0)
            size = 1 + (sum(len(r) + 1 for r in self.dvfiles[name]) + 255) // 256
            out.append(rec(name, t, size, fl))
        out.append(rec('', 0, 0, 0))
        return out

    def frame(self):
        return self.insns // VSYNC_INSNS

    def chord_now(self):
        if self.held is not None:
            return self.held
        f = self.frame()
        held = set()
        for a, b, chord in self.presses:
            if a - 1 > f:
                break
            mods = chord & MODIFIERS
            if a <= f < b:
                held |= chord                       # the key and its modifiers
            elif mods and a - 1 <= f < b + 1:
                held |= mods                        # modifiers down a frame early, up a frame late
        return frozenset(held)

    def alpha_now(self):
        f = self.frame()
        return self.alpha ^ (sum(1 for t in self.toggles if t <= f) & 1)

    def cru_read(self, bit):
        if bit == 2 and self.console_rom is not None:      # 9901 input 2: the VDP interrupt line, low while it is asserted
            return 0 if (self.vstatus & 0x80) and (self.vregs[1] & 0x20) else 1
        if self.tifdc is not None and 0x880 <= bit < 0x888:
            return 1 if self.tifdc.cru_read(bit - 0x880) else 0
        # keyboard rows on inputs 3-10; the column was written to outputs 18-20.
        # With output 21 low, input 7 reads ALPHA LOCK instead (0 = down), as js99er.
        if 3 <= bit <= 10:
            if bit == 7 and not self.cru21:
                return 0 if self.alpha_now() else 1
            return 0 if (self.keycol, bit - 3) in self.chord_now() else 1
        return 1

    keycol = 0

# ---- CPU --------------------------------------------------------------
class CPU:
    def __init__(self, m):
        self.m = m
        self.wp = 0x83E0
        self.pc = 0
        self.st = 0   # bits: 15 LGT,14 AGT,13 EQ,12 C,11 OV
        self.limi = 0 # interrupt mask
        self.trace = False

    def reg(self, n): return self.m.rw(self.wp + 2 * n)
    def setreg(self, n, v): self.m.ww(self.wp + 2 * n, v & 0xFFFF)

    def flag(self, name, on):
        b = {'L': 15, 'A': 14, 'E': 13, 'C': 12, 'O': 11}[name]
        if on: self.st |= 1 << b
        else: self.st &= ~(1 << b)
    def get(self, name):
        b = {'L': 15, 'A': 14, 'E': 13, 'C': 12, 'O': 11}[name]
        return bool(self.st & (1 << b))

    def cmp0(self, v, byte):
        mask = 0xFF if byte else 0xFFFF
        v &= mask
        sign = 0x80 if byte else 0x8000
        self.flag('L', v != 0)
        self.flag('A', v != 0 and not (v & sign))
        self.flag('E', v == 0)

    def cmp(self, a, b, byte):
        mask = 0xFF if byte else 0xFFFF
        a &= mask; b &= mask
        bits = 8 if byte else 16
        sa = a - (1 << bits) if a >> (bits - 1) else a
        sb = b - (1 << bits) if b >> (bits - 1) else b
        self.flag('L', a > b)
        self.flag('A', sa > sb)
        self.flag('E', a == b)

    def fetch(self):
        v = self.m.rw(self.pc)
        self.pc = (self.pc + 2) & 0xFFFF
        return v

    # returns address for Ts/S, handling autoinc; register mode returns ('r', n)
    def ea(self, mode, n, byte):
        if mode == 0:
            return ('r', n)
        if mode == 1:
            return ('m', self.reg(n))
        if mode == 2:
            off = self.fetch()
            if n:
                return ('m', (off + self.reg(n)) & 0xFFFF)
            return ('m', off)
        a = self.reg(n)
        self.setreg(n, a + (1 if byte else 2))
        return ('m', a)

    def load(self, ea, byte):
        k, a = ea
        if k == 'r':
            v = self.reg(a)
            return (v >> 8) if byte else v
        return self.m.rb(a) if byte else self.m.rw(a)

    def store(self, ea, v, byte):
        k, a = ea
        if k == 'r':
            if byte:
                self.setreg(a, (v << 8) | (self.reg(a) & 0xFF))
            else:
                self.setreg(a, v)
        else:
            if byte: self.m.wb(a, v)
            else: self.m.ww(a, v)

    def step(self):
        m = self.m
        m.insns += 1
        if m.insns % VSYNC_INSNS == 0:
            m.vstatus |= 0x80
            if m.vregs[1] & 0x20: m.vint = True
        if m.vint and self.limi >= 1:
            m.vint = False
            if m.console_rom is not None:         # the real level-1 interrupt: a context switch through >0004
                st = (self.st & 0xFFF0) | (self.limi & 0xF)
                nwp = (m.rb(4) << 8) | m.rb(5); npc = (m.rb(6) << 8) | m.rb(7)
                old_wp, old_pc = self.wp, self.pc
                self.wp, self.pc, self.limi = nwp, npc, 0
                self.setreg(13, old_wp); self.setreg(14, old_pc); self.setreg(15, st)
                m.isr_count += 1
            else:
                m.console_isr(self)
        op = self.fetch()
        pc0 = self.pc - 2
        if self.trace:
            print(f"{pc0:04X} {op:04X} R0={self.reg(0):04X} R1={self.reg(1):04X} R5={self.reg(5):04X}")
        if op == 0x0180:                       # simulator trap: fake DSR
            self.flag('E', not m.dsr_trap(self))
            return
        if op == 0x0181:                       # simulator trap: the TIPI model's power-up routine ran
            m.pi_powered = True
            return
        top = op >> 12
        # ---- dual operand: A AB C CB S SB SOC SOCB SZC SZCB MOV MOVB
        if top >= 0x4:
            byte = bool(op & 0x1000)
            ts, s = (op >> 4) & 3, op & 0xF
            td, d = (op >> 10) & 3, (op >> 6) & 0xF
            sea = self.ea(ts, s, byte)
            sv = self.load(sea, byte)
            dea = self.ea(td, d, byte)
            code = top & 0xE
            if code == 0xC:      # MOV
                self.store(dea, sv, byte); self.cmp0(sv, byte)
            elif code == 0x8:    # C
                self.cmp(sv, self.load(dea, byte), byte)
            elif code == 0xA:    # A
                dv = self.load(dea, byte)
                r = sv + dv
                mask = 0xFF if byte else 0xFFFF
                sign = 0x80 if byte else 0x8000
                self.flag('C', r > mask)
                r &= mask
                self.flag('O', bool((sv & sign) == (dv & sign) and (r & sign) != (sv & sign)))
                self.store(dea, r, byte); self.cmp0(r, byte)
            elif code == 0x6:    # S
                dv = self.load(dea, byte)
                mask = 0xFF if byte else 0xFFFF
                sign = 0x80 if byte else 0x8000
                r = dv + ((~sv) & mask) + 1
                self.flag('C', r > mask)
                r &= mask
                self.flag('O', bool((sv & sign) != (dv & sign) and (r & sign) != (dv & sign)))
                self.store(dea, r, byte); self.cmp0(r, byte)
            elif code == 0xE:    # SOC
                r = self.load(dea, byte) | sv
                self.store(dea, r, byte); self.cmp0(r, byte)
            elif code == 0x4:    # SZC
                r = self.load(dea, byte) & ~sv
                self.store(dea, r, byte); self.cmp0(r, byte)
            else:
                raise Halt(f"unimplemented dual op {op:04X} at {pc0:04X}")
            return
        # ---- XOP/XOR/MPY/DIV/COC/CZC: 0x2xxx
        if top == 0x2:
            sub = (op >> 10) & 3
            ts, s = (op >> 4) & 3, op & 0xF
            d = (op >> 6) & 0xF
            sea = self.ea(ts, s, False)
            sv = self.load(sea, False)
            if sub == 2:        # XOR
                r = self.reg(d) ^ sv
                self.setreg(d, r); self.cmp0(r, False)
            elif sub == 0:      # COC
                self.flag('E', (self.reg(d) & sv) == sv)
            elif sub == 1:      # CZC
                self.flag('E', (self.reg(d) & sv) == 0)
            else:
                raise Halt(f"unimplemented 2xxx op {op:04X} at {pc0:04X}")
            return
        if top == 0x3:
            sub = (op >> 10) & 3
            ts, s = (op >> 4) & 3, op & 0xF
            d = (op >> 6) & 0xF
            if sub == 2:        # MPY
                sea = self.ea(ts, s, False)
                r = self.reg(d) * self.load(sea, False)
                self.setreg(d, r >> 16); self.setreg(d + 1, r & 0xFFFF)
            elif sub == 3:      # DIV
                sea = self.ea(ts, s, False)
                sv = self.load(sea, False)
                dividend = (self.reg(d) << 16) | self.reg(d + 1)
                if sv == 0 or self.reg(d) >= sv:
                    self.flag('O', True)
                else:
                    self.flag('O', False)
                    self.setreg(d, dividend // sv); self.setreg(d + 1, dividend % sv)
            elif sub == 0:      # LDCR
                cnt = d or 16
                sea = self.ea(ts, s, cnt <= 8)
                v = self.load(sea, cnt <= 8)
                base = (self.reg(12) >> 1) & 0xFFF
                for i in range(cnt):
                    bit = (v >> i) & 1
                    b = base + i
                    if b in (18, 19, 20):
                        m.keycol = (m.keycol & ~(1 << (b - 18))) | (bit << (b - 18))
                    elif b == 21:
                        m.cru_write(b, bit)
                    else:
                        m.cru_write(b, bit)
            elif sub == 1:      # STCR
                cnt = d or 16
                sea = self.ea(ts, s, cnt <= 8)
                base = (self.reg(12) >> 1) & 0xFFF
                v = 0
                for i in range(cnt):
                    v |= m.cru_read(base + i) << i
                if cnt <= 8:
                    old = self.load(sea, True)
                    v |= old & ~((1 << cnt) - 1) & 0xFF
                self.store(sea, v, cnt <= 8)
            return
        # ---- jumps and CRU single bit: 0x1xxx
        if top == 0x1:
            kind = (op >> 8) & 0xF
            disp = op & 0xFF
            if disp >= 0x80: disp -= 0x100
            L, A, E, C, O = (self.get(x) for x in 'LAECO')
            cond = {0: True, 1: not A and not E, 2: not L or E, 3: E, 4: L or E,
                    5: A, 6: not E, 7: not C, 8: C, 9: not O,
                    0xA: not L and not E, 0xB: L and not E, 0xC: True}
            if kind <= 0xC:
                if kind == 0xC:
                    raise Halt(f"unimplemented op {op:04X}")
                if cond[kind]:
                    self.pc = (self.pc + 2 * disp) & 0xFFFF
                return
            base = (self.reg(12) >> 1) & 0xFFF
            b = (base + disp) & 0xFFF
            if kind == 0xD: m.cru_write(b, 1)
            elif kind == 0xE: m.cru_write(b, 0)
            else: self.flag('E', bool(m.cru_read(b)))
            return
        # ---- shifts: 0x0Axx
        if 0x08 <= (op >> 8) <= 0x0B:
            kind = (op >> 8) & 3
            r = op & 0xF
            cnt = (op >> 4) & 0xF
            if cnt == 0:
                cnt = self.reg(0) & 0xF or 16
            v = self.reg(r)
            c = 0
            for _ in range(cnt):
                if kind == 0:   # SRA
                    c = v & 1; v = (v >> 1) | (v & 0x8000)
                elif kind == 1: # SRL
                    c = v & 1; v >>= 1
                elif kind == 2: # SLA
                    c = v >> 15; v = (v << 1) & 0xFFFF
                else:           # SRC
                    c = v & 1; v = (v >> 1) | (c << 15)
            self.setreg(r, v); self.cmp0(v, False); self.flag('C', bool(c))
            return
        # ---- immediates: 0x02xx
        if op >> 8 == 0x02 or op >> 8 == 0x03:
            sub = (op >> 5) & 0xF
            r = op & 0xF
            if op == 0x0340:       # IDLE
                raise Halt("IDLE")
            if op == 0x0380:       # RTWP: status, PC and workspace back from R15, R14, R13
                st, pc, wp = self.reg(15), self.reg(14), self.reg(13)
                self.st = st & 0xFFF0; self.limi = st & 0xF; self.pc = pc; self.wp = wp
                return
            if op == 0x0300:       # LIMI
                self.limi = self.fetch() & 0xF; return
            if op == 0x02E0:       # LWPI
                self.wp = self.fetch(); return
            if 0x02A0 <= op <= 0x02AF:  # STWP: the workspace pointer into R
                self.setreg(r, self.wp); return
            if 0x02C0 <= op <= 0x02CF:  # STST: the status register into R
                self.setreg(r, (self.st & 0xFFF0) | (self.limi & 0xF)); return
            imm = self.fetch()
            if sub == 0:           # LI
                self.setreg(r, imm); self.cmp0(imm, False)
            elif sub == 1:         # AI
                v = self.reg(r); s = v + imm
                self.flag('C', s > 0xFFFF); s &= 0xFFFF
                self.setreg(r, s); self.cmp0(s, False)
            elif sub == 2:         # ANDI
                v = self.reg(r) & imm; self.setreg(r, v); self.cmp0(v, False)
            elif sub == 3:         # ORI
                v = self.reg(r) | imm; self.setreg(r, v); self.cmp0(v, False)
            elif sub == 4:         # CI
                self.cmp(self.reg(r), imm, False)
            else:
                raise Halt(f"unimplemented imm op {op:04X}")
            return
        # ---- single operand: 0x04xx-0x07xx
        if 0x0400 <= op < 0x0800:
            kind = (op >> 6) & 0xF
            ts, s = (op >> 4) & 3, op & 0xF
            ea = self.ea(ts, s, False)
            if kind == 0:          # BLWP
                if ea[0] == 'm' and ea[1] == 0x0000:
                    # BLWP @>0000: the console's reset (as FCTN-QUIT).  There is no
                    # console ROM here, so do what matters: scratchpad cleared, the
                    # cartridge port back to bank 0, and the menu's choice of the
                    # cartridge's first program (expansion RAM and the cards keep
                    # their state, as they do on a real console)
                    self.m.at_reset = (list(self.m.vregs), dict(self.m.palette), self.m.ams_mapping)   # for the tests
                    # the cartridge bank selected as the reset came: the console reads
                    # the cartridge's header (and so finds Press for its menu) in the
                    # bank selected, which must be bank 0 (a real console does not
                    # reselect it; this simulator does, below, so it is kept here)
                    self.m.bank_at_reset = self.m.bank
                    for i in range(0x100): self.m.scratch[i] = 0
                    self.m.bank = 0
                    self.m.console_resets = getattr(self.m, 'console_resets', 0) + 1
                    self.wp = 0x83E0
                    self.pc = self.m.rw(self.m.rw(0x6006) + 2)
                    return
                # any other vector: the context switch (new WP and PC from the
                # vector; the old WP, PC and status into the new R13-R15)
                v = ea[1] if ea[0] == 'm' else (self.wp + 2 * ea[1]) & 0xFFFF
                nwp, npc = self.m.rw(v), self.m.rw(v + 2)
                if getattr(self.m, 'blwp_log', None) is not None and len(self.m.blwp_log) < 20:
                    self.m.blwp_log.append((v, nwp, npc))
                owp, opc, ost = self.wp, self.pc, self.st
                self.wp = nwp
                self.setreg(13, owp); self.setreg(14, opc); self.setreg(15, (ost & 0xFFF0) | (self.limi & 0xF))
                self.pc = npc
                return
            if kind == 1:          # B
                self.pc = ea[1] if ea[0] == 'm' else self.reg(ea[1]); return
            if kind == 2:          # X
                raise Halt("X unimplemented")
            if kind == 3:          # CLR
                self.store(ea, 0, False); return
            if kind == 4:          # NEG
                v = (-self.load(ea, False)) & 0xFFFF; self.store(ea, v, False); self.cmp0(v, False); return
            if kind == 5:          # INV
                v = (~self.load(ea, False)) & 0xFFFF; self.store(ea, v, False); self.cmp0(v, False); return
            if kind == 6:          # INC
                v = self.load(ea, False); s2 = v + 1; self.flag('C', s2 > 0xFFFF); s2 &= 0xFFFF
                self.store(ea, s2, False); self.cmp0(s2, False); return
            if kind == 7:          # INCT
                v = (self.load(ea, False) + 2) & 0xFFFF; self.store(ea, v, False); self.cmp0(v, False); return
            if kind == 8:          # DEC
                v = self.load(ea, False); s2 = (v - 1) & 0xFFFF; self.flag('C', v != 0)
                self.store(ea, s2, False); self.cmp0(s2, False); return
            if kind == 9:          # DECT
                v = (self.load(ea, False) - 2) & 0xFFFF; self.store(ea, v, False); self.cmp0(v, False); return
            if kind == 0xA:        # BL
                self.setreg(11, self.pc)
                self.pc = ea[1] if ea[0] == 'm' else self.reg(ea[1]); return
            if kind == 0xB:        # SWPB
                v = self.load(ea, False); self.store(ea, ((v << 8) | (v >> 8)) & 0xFFFF, False); return
            if kind == 0xC:        # SETO
                self.store(ea, 0xFFFF, False); return
            if kind == 0xD:        # ABS
                v = self.load(ea, False); self.cmp0(v, False)
                if v & 0x8000: self.store(ea, (-v) & 0xFFFF, False)
                return
        raise Halt(f"unimplemented op {op:04X} at {pc0:04X}")

TILECH = {0x80: '~', 0x81: ',', 0x88: '.', 0x89: 'T', 0x8A: 'w', 0x90: 'h', 0x91: 'M',
          0x92: '=', 0x93: ':', 0x94: '#', 0x95: '#', 0x96: '.', 0x98: 'O', 0x99: 'C',
          0x9A: 'D', 0x9B: 'r', 0x9C: '^', 0x20: ' ', 0xA0: '#', 0xA8: 'x'}

def text_geometry(m):
    """(columns, rows, name table, attribute table or None, pattern table) for a
    text mode, or None when the VDP is not in one."""
    m1 = (m.vregs[1] >> 4) & 1
    if not m1:
        return None
    t80 = bool(m.vregs[0] & 0x04)
    cols = 80 if t80 else 40
    rows = 30 if (m.f18a and m.unlocked and m.vregs[49] & 0x40) else 24
    nt = (m.vregs[2] & (0x0F if (not t80 or m.unlocked) else 0x0C)) << 10
    at = (m.vregs[3] << 6) if (m.f18a and m.unlocked and m.vregs[50] & 0x02) else None
    pt = (m.vregs[4] & 7) << 11
    return cols, rows, nt, at, pt

def to_char(code):
    """A name-table byte as text: ASCII, underlined ASCII (128-222) as the
    letter itself, UI glyphs as '#'."""
    if 32 <= code < 127: return chr(code)
    if 128 <= code < 223: return chr(code - 96)
    return '#'

def screen(m):
    """The screen as text lines (text modes), or a note when not in one."""
    g = text_geometry(m)
    if g is None:
        return '(not a text mode: VR0=%02X VR1=%02X)' % (m.vregs[0], m.vregs[1])
    cols, rows, nt, at, pt = g
    return '\n'.join(''.join(to_char(m.vram[(nt + r * cols + c) & 0x3FFF]) for c in range(cols))
                     for r in range(rows))

def attrs(m):
    """The position attributes as rows of bytes, or None."""
    g = text_geometry(m)
    if g is None or g[3] is None:
        return None
    cols, rows, nt, at, pt = g
    return [bytes(m.vram[(at + r * cols + c) & 0x3FFF] for c in range(cols)) for r in range(rows)]

def load_console_rom(path):
    """The user's own console ROM as 8192 bytes: a raw dump, or an EA5 image (a
    6-byte header FFFF, length, address) as Nouspikel's ROM loaders make.  TI's code:
    never copy it into a project; take the path from the user."""
    d = open(path, 'rb').read()
    if len(d) == 8198 and d[:2] == b'\xff\xff':
        d = d[6:]
    if len(d) != 8192:
        raise ValueError('a console ROM is 8192 bytes')
    return d

def run(cart, keys='', frames=None, f18a=True, sams=True, pages=128, setup=None, version=0x19, rom=None):
    """Boot the cartridge as the console menu would and run the key script;
    returns (machine, cpu, halt message or None)."""
    m = Machine(cart, f18a=f18a, pages=pages, sams=sams, f18a_version=version)
    rom = rom or os.environ.get('TI_CONSOLE_ROM')
    if rom:
        m.console_rom = load_console_rom(rom)
    m.presses, m.toggles, end = schedule(parse_keys(keys))
    if setup: setup(m)
    if frames is None: frames = end + 30
    cpu = CPU(m)
    prog = m.rw(0x6006)                  # the menu's choice: the cart's first program
    cpu.pc = m.rw(prog + 2)
    halt = None
    try:
        while m.insns < frames * VSYNC_INSNS:
            cpu.step()
    except Halt as e:
        halt = f"{e} at PC={cpu.pc:04X} after {m.insns} insns"
    return m, cpu, halt

def main():
    args = sys.argv[1:]
    path = args[0]
    opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d
    cart = open(path, 'rb').read()
    m, cpu, halt = run(cart, keys=opt('--keys', ''), frames=int(opt('--frames')) if opt('--frames') else None,
                       f18a='--no-f18a' not in args, sams='--no-sams' not in args,
                       pages=int(opt('--pages', 128)))
    if halt: print("HALT:", halt)
    print(f"ran {m.insns} instructions ({m.frame()} frames), bank={m.bank}, mapping={m.ams_mapping}, "
          f"f18a_unlocked={m.unlocked}, palette entries={len(m.palette)}")
    print("VDP regs:", ' '.join(f"{v:02X}" for v in m.vregs[:8]),
          " VR49=%02X VR50=%02X VR51=%02X" % (m.vregs[49], m.vregs[50], m.vregs[51]))
    lines = screen(m).split('\n')
    w = max(len(l) for l in lines)
    print('+' + '-' * w + '+')
    for line in lines:
        print('|' + line + '|')
    print('+' + '-' * w + '+')

if __name__ == '__main__':
    main()
