"""The CorComp disk controller card, for the simulator: its own DSR ROM (two 8K EPROMs, u3
and u4, not in this repository) on the same WD177x chip as the TI's card, on a double-sided
double-density disk image (see fdc.py for the image format).

The ROM is 16K in two banks that both appear at >4000 (bank 1 also has 128 bytes of RAM at
>4000-407F, the part of u4 that is blank: the DSR's variables and sector buffer): u3 (the DSR proper: device names, file
system) and u4 (the disk I/O layer, which alone touches the chip); the DSR switches with CRU
bit 11.  Environment: CCFDC_U3 and CCFDC_U4 name the ROM files (default: the repository's roms/).  The chip's registers are memory mapped at >5FF0 (status / command), >5FF2
(track), >5FF4 (sector), >5FF6 (data), written at >5FF8-5FFE.
What the card's CRU bits do is worked out from the ROM (the card's own documentation was not
available): see the CRU map in the class."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fdc import WD177x
from tifdc import blank_disk

HERE = os.path.dirname(os.path.abspath(__file__))


def _rom(env, name):
    p = os.environ.get(env) or next((x for x in (os.path.join(HERE, '..', 'roms', name), os.path.join('/home/claude/rom', name), os.path.join(HERE, name)) if os.path.exists(x)), None)
    if not p or not os.path.exists(p):
        raise FileNotFoundError('the CorComp ROM %s is not found: set %s' % (name, env))
    return open(p, 'rb').read()


class CCFDC:
    cru_base, cru_bits = 0x880, 32               # CRU >1100

    def __init__(self, image=None, inverted=False, u3=None, u4=None):
        self.rom = [u3 or _rom('CCFDC_U3', 'ccdcc_v89.u3'), u4 or _rom('CCFDC_U4', 'ccdcc_v89.u4')]
        self.bank = 0
        self.ram = bytearray(128)                # bank 1 (u4) has 128 bytes of RAM at >4000-407F, where u4 is blank
        self.rom_on = False
        self.image = image if image is not None else blank_disk(sectors=1440)
        self.inverted = inverted                 # data bus inverted, as on the TI card?
        self.wd = WD177x(self)
        self.writes = 0
        self.motor = False
        self.cru = [0] * 32
        self.log = []                            # (kind, bit, value): what the ROM did, for working it out

    def cru_write(self, n, v):
        v = 1 if v else 0
        self.log.append(('w', n, v))
        self.cru[n] = v
        if n == 0: self.rom_on = bool(v)
        elif n == 11: self.bank = v
        elif n == 1:
            if v: self.motor = True
        elif n == 3:
            if v: self.wd.load_head()
        elif n in (4, 5, 6, 8): self.wd.set_drive({4: 1, 5: 2, 6: 3, 8: 4}[n], bool(v))     # drive select, as on the TI's card (8: a fourth)
        elif n == 7: self.wd.side = v

    def cru_read(self, n):
        self.log.append(('r', n, 0))
        if n == 9: return not self.motor          # 1 = the motor is not running (TB 9 then makes the ROM wait for spin-up)
        return bool(self.cru[n])

    def _x(self, b):
        return (b ^ 0xFF) & 0xFF if self.inverted else b

    def read(self, addr):
        if 0x5FF0 <= addr < 0x5FF8:
            if addr & 1: return 0xFF
            r = {0x5FF0: self.wd.status, 0x5FF2: lambda: self.wd.track,
                 0x5FF4: lambda: self.wd.sector, 0x5FF6: self.wd.get_data}[addr]()
            return self._x(r)
        if self.bank == 1 and addr < 0x4080:
            return self.ram[addr - 0x4000]
        return self.rom[self.bank][addr - 0x4000]

    def write(self, addr, val):
        if self.bank == 1 and addr < 0x4080:
            self.ram[addr - 0x4000] = val
            return
        if addr & 1 or addr < 0x5FF8: return
        b = self._x(val)
        if addr == 0x5FF8: self.wd.set_command(b)
        elif addr == 0x5FFA: self.wd.track = b
        elif addr == 0x5FFC: self.wd.sector = b
        elif addr == 0x5FFE: self.wd.set_data(b)


def available():
    """are the card's ROMs to be found (the repository's roms/, or CCFDC_U3 and CCFDC_U4)?"""
    try:
        _rom('CCFDC_U3', 'ccdcc_v89.u3'); _rom('CCFDC_U4', 'ccdcc_v89.u4')
        return True
    except FileNotFoundError:
        return False
