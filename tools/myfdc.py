"""The Myarc DDCC-1 disk controller card, for the simulator: its own DSR ROM (ddcc1.u3, 8K, in
roms/) on the same WD177x chip model as the other cards (fdc.py), on a double-density disk image.

The card's hardware, as MAME describes it (src/devices/bus/ti99/peb/myarcfdc.cpp, by Michael Zapf;
this model is written from that description, not copied from it):
  ROM      the 8K EPROM is two banks of 4K, both appearing at >4000-4FFF; bank 0 is the file's lower
           half, bank 1 its upper half (so what a listing shows at >5000-5FFF is bank 1 and runs at
           >4000-4FFF); the DSR switches banks with the trampoline it builds in the workspace
           registers: SBO 3, MOV @>4000(R5),R5, B *R5
  RAM      2K at >5000-57FF, always
  chip     a WD1770 or WD1772 at the odd addresses >5F01, >5F03, >5F05, >5F07 (any odd address of
           >5F00-5FFF: register (address / 2) mod 4): status / command, track, sector, data
  CRU out  an LS259 latch: 0 card enable, 1 chip reset (0 = reset), 2 side select, 3 ROM bank
           and double density (DDEN), 4-7 drive select 1-4
  CRU in   an LS251 multiplexer: 0 INTRQ, 1 DRQ, 2 the Turbo switch, 4-7 the step-rate switches
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fdc import WD177x
from tifdc import blank_disk

HERE = os.path.dirname(os.path.abspath(__file__))


def _rom():
    p = os.environ.get('MYFDC_ROM') or next((x for x in (os.path.join(HERE, '..', 'roms', 'ddcc1.u3'), '/home/claude/rom/ddcc1.u3') if os.path.exists(x)), None)
    if not p:
        raise FileNotFoundError('the Myarc ROM ddcc1.u3 is not found: set MYFDC_ROM')
    return open(p, 'rb').read()


def available():
    try:
        _rom()
        return True
    except FileNotFoundError:
        return False


class MYFDC:
    cru_base, cru_bits = 0x880, 8                # CRU >1100

    def __init__(self, image=None):
        self.rom = _rom()
        self.rom_on = False
        self.image = image if image is not None else blank_disk(sectors=1440)
        self.ram = bytearray(0x800)
        self.wd = WD177x(self)
        self.writes = 0
        self.cru = [0] * 8
        self.cru[3] = 0
        self.intrq = False
        self.xfer = 0                            # bytes the chip still has to give or take (DRQ while > 0)
        self.log = []

    def density(self):
        """the density the chip is set to: DDEN is latch bit 3, high = single, low = double (the DSR clears
        it for a drive it has found to be double density, and sets it again after each command)"""
        return 1 if self.cru[3] else 2

    def cru_write(self, n, v):
        v = 1 if v else 0
        self.log.append(('w', n, v))
        self.cru[n] = v
        wd = self.wd
        if n == 0: self.rom_on = bool(v)
        elif n == 1 and not v:                   # the chip's reset line
            wd.busy = False; wd.read_buffer = []; wd.write_buffer = []; wd.track = 0; wd.command = 0
            self.xfer = 0; self.intrq = False
        elif n == 2: wd.side = v
        elif n in (4, 5, 6, 7):
            # the DSR selects the new drive first, then unselects the old one: the drive is the lowest
            # of the set lines, and none is selected when no line is set
            on = [i for i in (4, 5, 6, 7) if self.cru[i]]
            wd.drive = (on[0] - 3) if on else 0

    def cru_read(self, n):
        self.log.append(('r', n, 0))
        if n == 0: return self.intrq
        if n == 1: return self.xfer > 0
        return False                             # the Turbo and step-rate switches: all open

    def _took_byte(self):
        if self.xfer > 0:
            self.xfer -= 1
            if self.xfer == 0:
                self.intrq = True

    def read(self, addr):
        if (addr & 0xFF01) == 0x5F01:
            wd = self.wd
            reg = (addr >> 1) & 3
            if reg == 0:
                self.intrq = False
                return wd.status()
            if reg == 1: return wd.track
            if reg == 2: return wd.sector
            b = wd.get_data()
            self._took_byte()
            return b
        if 0x5000 <= addr < 0x5800:
            return self.ram[addr - 0x5000]
        if addr < 0x5000:
            return self.rom[(0x1000 if self.cru[3] else 0) | (addr & 0x0FFF)]
        return 0xFF

    def write(self, addr, val):
        if (addr & 0xFF01) == 0x5F01:
            wd = self.wd
            reg = (addr >> 1) & 3
            if reg == 0:
                self.intrq = False
                wd.set_command(val)
                hi = val & 0xF0
                if hi in (0x80, 0x90, 0xA0, 0xB0): self.xfer = 256
                elif hi == 0xC0: self.xfer = 6
                else:
                    self.xfer = 0
                    self.intrq = True            # types I and IV: done (the model has no seek time)
                if wd.rnf:
                    self.xfer = 0
                    self.intrq = True            # the wrong density: the chip gives up (record not found)
            elif reg == 1: wd.track = val
            elif reg == 2: wd.sector = val
            else:
                wd.set_data(val)
                self._took_byte()
            return
        if 0x5000 <= addr < 0x5800:
            self.ram[addr - 0x5000] = val
