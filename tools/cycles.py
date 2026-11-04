#!/usr/bin/env python3
"""cycles.py - a cycle count for the simulator: how many clock cycles of the TI-99/4A's 3 MHz TMS9900 a program takes.

    import sim9900, cycles
    cpu = cycles.CycleCPU(machine)       # in place of sim9900.CPU(machine)
    ... cpu.step() as usual ...
    cpu.cycles                           # clock cycles so far; cpu.seconds() = cycles / 3,000,000

The simulator itself counts instructions (a frame is VSYNC_INSNS of them) and keeps doing so: this module only MEASURES, it does not
change when interrupts or frames happen.

THE MODEL.  Each instruction costs what the TMS9900 data manual gives for it with no wait states: a base number of clock cycles for the
instruction, plus a number for each operand by addressing mode (register 0; *R 4; *R+ 6 for a byte and 8 for a word; @symbolic and
@indexed 8); shifts add 2 a place; a jump costs 10 if taken and 8 if not.  Then it adds the TI's wait states: **4 cycles for every
memory access outside the console ROM (>0000-1FFF) and the scratchpad (>8000-83FF)**, because everything else is 8 bits wide behind the
console's multiplexer.  (TI's own 99/4A technical data: an external 16-bit read is two 8-bit cycles and the CPU looks at the data in clock cycle 6, against 2
for an access without wait states: four more.  This file once said 8, reading the 4 as per byte; it is per word, as the manual's cycle formula C + W*M has it.)  The accesses counted are the CPU's own: the
instruction fetch (one word, and one more for each address word), the workspace registers the instruction reads and writes (so a
workspace in expansion RAM is slow, which is why programs keep it in the scratchpad), the words an address mode reads, and the operands
(a destination is read and then written, as the 9900 does even for MOV).

WHAT IS CHECKED.  tests/test_kernel.py (group cycles) against numbers from the manual and from well-known measurements: `DEC R2 / JNE`
is 20 cycles a time in the scratchpad (a count of 65,535 takes about 0.44 s) and 36 in expansion RAM (about 0.79 s).  WHAT IS NOT:
the model has not been compared with a real console beyond those, and it leaves out the video chip's and the sound chip's own
access delays, the interrupt's context switch (22 cycles), and the DIV instruction's data-dependent time (a fixed 112 is used; MPY is 52).
Treat a result as an estimate good to a few per cent for loops of ordinary instructions and as a RATIO between two programs more than as
a number of milliseconds.
"""
import sim9900

CLOCK = 3_000_000

# base clock cycles (no operands' addressing costs, no wait states)
SINGLE = {0x0400: 26, 0x0440: 8, 0x0480: 8, 0x04C0: 10, 0x0500: 12, 0x0540: 10, 0x0580: 10, 0x05C0: 10,
          0x0600: 10, 0x0640: 10, 0x0680: 12, 0x06C0: 10, 0x0700: 10, 0x0740: 12}
# the single-operand instructions that read and write their operand (the rest only form an address)
SINGLE_RW = {0x04C0, 0x0500, 0x0540, 0x0580, 0x05C0, 0x0600, 0x0640, 0x06C0, 0x0700, 0x0740}
IMMEDIATE = {0x0200: 12, 0x0220: 14, 0x0240: 14, 0x0260: 14, 0x0280: 14, 0x02A0: 8, 0x02C0: 8, 0x02E0: 10, 0x0300: 16,
             0x0340: 12, 0x0360: 12, 0x0380: 14, 0x03A0: 12, 0x03C0: 12, 0x03E0: 12}
JUMP_FLAGS = {0x10: None, 0x11: lambda c: not c.get('A') and not c.get('E'), 0x12: lambda c: (not c.get('L')) or c.get('E'),
              0x13: lambda c: c.get('E'), 0x14: lambda c: c.get('L') or c.get('E'), 0x15: lambda c: c.get('A'),
              0x16: lambda c: not c.get('E'), 0x17: lambda c: not c.get('C'), 0x18: lambda c: c.get('C'),
              0x19: lambda c: not c.get('O'), 0x1A: lambda c: not c.get('L') and not c.get('E'),
              0x1B: lambda c: c.get('L') and not c.get('E'), 0x1C: lambda c: bin(c.st >> 8 & 0xFF).count('1') % 2 == 1}


def wait(addr):
    """4 wait cycles for an access outside the console ROM and the scratchpad, else 0"""
    a = addr & 0xFFFF
    return 0 if a < 0x2000 or 0x8000 <= a < 0x8400 else 4


class CycleCPU(sim9900.CPU):
    def __init__(self, m):
        super().__init__(m)
        self.cycles = 0

    def seconds(self):
        return self.cycles / CLOCK

    # ---- operand costs: (clock cycles, [addresses accessed]) for an operand in addressing mode `mode`, register n, with
    # `nacc` accesses to the operand itself; `pc` is where its address word would be; returns also the new pc
    def _operand(self, mode, n, pc, byte, nacc):
        wp = self.wp
        reg = wp + 2 * n
        if mode == 0:
            return 0, [reg] * nacc, pc
        r = self.m.rw(reg)
        if mode == 1:
            return 4, [reg] + [r] * nacc, pc
        if mode == 2:
            addr = (self.m.rw(pc) + (r if n else 0)) & 0xFFFF
            return 8, [pc] + ([reg] if n else []) + [addr] * nacc, pc + 2
        return (6 if byte else 8), [reg] + [r] * nacc + [reg], pc

    def _timing(self, op, pc, fetched):
        """(cycles, accesses) of the instruction op, whose first word was at pc-2 if `fetched` (else it came from an X)"""
        acc = [pc - 2] if fetched else []
        c = 0
        if op in (0x0180, 0x0181):
            return 0, []
        top = op >> 12
        if top >= 4:                                   # two operands
            byte = bool(op & 0x1000)
            code = top & 0xE
            ts, s, td, d = (op >> 4) & 3, op & 15, (op >> 10) & 3, (op >> 6) & 15
            c = 14
            cs, a1, pc = self._operand(ts, s, pc, byte, 1)
            cd, a2, pc = self._operand(td, d, pc, byte, 1 if code == 0x8 else 2)
            return c + cs + cd, acc + a1 + a2
        if top in (2, 3):                              # COC CZC XOR XOP LDCR STCR MPY DIV
            sub = op & 0xFC00
            ts, s, d = (op >> 4) & 3, op & 15, (op >> 6) & 15
            if sub in (0x2000, 0x2400, 0x2800):
                cs, a1, pc = self._operand(ts, s, pc, False, 1)
                return 14 + cs, acc + a1 + [self.wp + 2 * d] * (2 if sub == 0x2800 else 1)
            if sub == 0x2C00:
                return 36, acc + [self.wp] * 7
            if sub in (0x3000, 0x3400):
                cnt = d if d else 16
                cs, a1, pc = self._operand(ts, s, pc, cnt <= 8, 1)
                if sub == 0x3000:
                    return 20 + 2 * cnt + cs, acc + a1
                return {0: 60}.get(d, 42 if d < 8 else 44 if d == 8 else 58) + cs, acc + a1
            cs, a1, pc = self._operand(ts, s, pc, False, 1)
            return (52 if sub == 0x3800 else 112) + cs, acc + a1 + [self.wp + 2 * d] * 3
        if top == 1:                                   # jumps, CRU single-bit
            k = op >> 8
            if k >= 0x1D:
                return 12, acc + [self.wp + 24]
            fn = JUMP_FLAGS.get(k)
            taken = True if fn is None else bool(fn(self))
            return (10 if taken else 8), acc
        if top == 0:
            if 0x0800 <= op < 0x0C00:                  # shifts
                n = (op >> 4) & 15
                reg = self.wp + 2 * (op & 15)
                if n:
                    return 12 + 2 * n, acc + [reg] * 2
                n = (self.m.rw(self.wp) & 15) or 16
                return 20 + 2 * n, acc + [self.wp, reg, reg]
            if 0x0200 <= op < 0x0400:                  # immediate
                base = op & 0xFFE0
                reg = self.wp + 2 * (op & 15)
                words = [pc]                           # the immediate word
                regs = {0x0200: [reg], 0x0220: [reg] * 2, 0x0240: [reg] * 2, 0x0260: [reg] * 2, 0x0280: [reg],
                        0x02A0: [reg], 0x02C0: [reg], 0x02E0: [], 0x0300: [], 0x0380: [self.wp + 26] * 3}
                if base in (0x0340, 0x0360, 0x03A0, 0x03C0, 0x03E0):
                    return IMMEDIATE[base], acc
                return IMMEDIATE.get(base, 12), acc + (words if base not in (0x02A0, 0x02C0, 0x0380) else []) + regs.get(base, [])
            base = op & 0xFFC0                         # single operand
            ts, s = (op >> 4) & 3, op & 15
            cs, a1, pc = self._operand(ts, s, pc, False, 2 if base in SINGLE_RW else 0)
            extra = [self.wp + 22] if base == 0x0680 else [self.wp + 26] * 3 if base == 0x0400 else []
            return SINGLE.get(base, 8) + cs, acc + a1 + extra
        return 8, acc

    def step(self):
        pend = self.pending_op
        op = pend if pend is not None else self.m.rw(self.pc)
        pc = self.pc + (0 if pend is not None else 2)
        try:
            c, accs = self._timing(op, pc, pend is None)
        except Exception:                              # an odd state (a fault in the simulated program): count nothing
            c, accs = 0, []
        self.cycles += c + sum(wait(a) for a in accs)
        return super().step()
