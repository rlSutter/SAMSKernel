"""js99er's "Myarc floppy controller", ported from its source (JS99er-angular, src/app/emulator/classes/myarc-fdc.ts and wd177x.ts,
read 12 November 2026) so that the simulator can run what js99er runs: its own DSR ROM (an 8K Myarc FDC image, header >AA03, DSR list
at >4064: not the DDCC-1's >AA02) on ITS chip, which is simpler than a real WD177x in ways a DSR can notice:
  * a read-sector command never sets busy; DRQ ("ready for data", CRU bit 1) is true until the byte buffer is empty, and reading
    the bit sets it true again; CRU bit 0 returns "not busy" and clears busy, so the command always looks finished;
  * status has only three bits: head loaded (>20), track 0 (>04) and busy (>01), and reading it clears busy: no record-not-found,
    no CRC, no DRQ bit, no lost data;
  * the multiple-sector read (>90) refills the buffer with the next logical sector, forever, until a force interrupt;
  * a write command only empties the write buffer; a sector is written when 256 bytes have arrived;
  * reading past the image gives empty sectors (the buffer runs dry and every read returns 0).
  * **a bug**: setData() counts EVERY write to the data register as a byte of a sector to be written, including the track number
    a seek needs (the DSR writes it there before each seek), and writes a sector into the disk image when 256 have arrived: after
    256 seeks the sector the registers point at is overwritten with track numbers. A program that reads a few hundred sectors
    through this controller has its disk corrupted in js99er's memory (found 12 November 2026: assembling ED/A99, line numbers
    running past the end of the file). JSMYARC(fix=True) is the corrected chip: a data write outside a write command only sets
    the data register, as on a real WD177x.
The ROM (8K, sha256 2d2093f9fa4023b1...) is extracted from the array in myarc-fdc.ts; it is read from JSMYARC_ROM, or
roms/js99er_myarc_fdc.bin, or /home/claude/rom/js99er_myarc_fdc.bin."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tifdc import blank_disk


HERE = os.path.dirname(os.path.abspath(__file__))


def _rom():
    p = os.environ.get('JSMYARC_ROM') or next((x for x in (os.path.join(HERE, '..', 'roms', 'js99er_myarc_fdc.bin'),
                                                          '/home/claude/rom/js99er_myarc_fdc.bin') if os.path.exists(x)), None)
    if not p:
        raise FileNotFoundError('js99er\'s Myarc ROM is not found: set JSMYARC_ROM (see the top of tools/jsmyarc.py)')
    return open(p, 'rb').read()


def available():
    try:
        _rom()
        return True
    except FileNotFoundError:
        return False


class JsWD:
    def __init__(self, fdc):
        self.fdc = fdc
        self.command = self.drive = self.side = self.track = self.sector = 0
        self.direction = 1
        self.data = 0
        self.ready = True
        self.busy = False
        self.head_loaded = False
        self.rb, self.wb = [], []

    def idx(self, side, track, sector):
        img = self.fdc.image
        spt, tps, sides = img[0x0C], img[0x11], img[0x12]
        total = (img[0x0A] << 8) | img[0x0B]
        if side == 0:
            return track * spt + sector
        return total // 2 + (tps - 1 - track) * spt + sector

    def sector_into_buffer(self):
        if self.drive >= 1:
            i = self.idx(self.side, self.track, self.sector)
            self.rb.extend(self.fdc.image[256 * i:256 * i + 256])

    def read_byte(self):
        self.data = self.rb.pop(0) if self.rb else 0
        if not self.rb and (self.command & 0xF0) == 0x90:
            self.sector += 1
            self.sector_into_buffer()

    def get_data(self):
        b = self.data
        if self.rb:
            self.read_byte()
            self.ready = True
        else:
            self.ready = False
        return b

    def set_data(self, b):
        self.data = b
        if self.fdc.fix and (self.command & 0xF0) not in (0xA0, 0xB0):
            return                               # the correction: not sector data
        self.wb.append(b)
        if len(self.wb) == 256:
            if self.drive >= 1:
                i = self.idx(self.side, self.track, self.sector)
                self.fdc.image[256 * i:256 * i + 256] = bytes(self.wb)
            self.wb = []
            if self.command == 0xB0:
                self.sector += 1

    def set_command(self, c):
        self.command = c
        hi = c & 0xF0
        flags = c & 0x0F
        if hi == 0x00:
            self.track = 0
            if flags & 8: self.head_loaded = True
            self.busy = True
        elif hi == 0x10:
            self.track = self.data
            if flags & 8: self.head_loaded = True
            self.busy = True
        elif hi in (0x20, 0x30, 0x40, 0x50, 0x60, 0x70):
            if hi in (0x40, 0x50): self.direction = 1
            if hi in (0x60, 0x70): self.direction = -1
            if hi in (0x20, 0x30, 0x50, 0x70) or c & 0x10:
                self.track = min(self.track + 1, 255) if self.direction > 0 else max(self.track - 1, 0)
            if flags & 8: self.head_loaded = True
            self.busy = True
        elif hi in (0x80, 0x90):
            self.sector_into_buffer()
            self.read_byte()
            self.head_loaded = True
        elif hi in (0xA0, 0xB0):
            self.wb = []
        elif hi == 0xC0:
            self.rb += [self.track, self.side, self.sector, 1, 0, 0]
            self.read_byte()
            self.head_loaded = True
            self.busy = True
        elif hi == 0xD0:
            self.busy = False

    def status(self):
        t0 = self.track == 0 and ((self.command & 0x80) == 0 or (self.command & 0xF0) == 0xD0)
        s = (0x20 if self.head_loaded else 0) | (0x04 if t0 else 0) | (0x01 if self.busy else 0)
        self.busy = False
        return s


class JSMYARC:
    cru_base, cru_bits = 0x880, 8                # CRU >1100

    def __init__(self, image=None, fix=False):
        self.rom = _rom()
        self.fix = fix
        self.rom_on = False
        self.bank = 0
        self.image = image if image is not None else blank_disk(sectors=1440)
        self.ram = bytearray(0x800)
        self.wd = JsWD(self)
        self.writes = 0
        self.log = []

    def cru_write(self, n, v):
        v = 1 if v else 0
        wd = self.wd
        if n == 0:
            self.rom_on = bool(v); self.bank = 0
        elif n == 2: wd.side = v
        elif n == 3: self.bank = v
        elif n in (4, 5, 6, 7):
            d = n - 3
            if v: wd.drive = d
            elif wd.drive == d: wd.drive = 0

    def cru_read(self, n):
        wd = self.wd
        if n == 0:
            b = wd.busy; wd.busy = False
            return not b
        if n == 1:
            r = wd.ready; wd.ready = True
            return r
        if n == 2: return True
        return False

    def read(self, addr):
        if (addr & 0xFF01) == 0x5F01:
            wd = self.wd
            reg = (addr >> 1) & 3
            if reg == 0: return wd.status()
            if reg == 1: return wd.track
            if reg == 2: return wd.sector
            return wd.get_data()
        if 0x5000 <= addr < 0x5800:
            return self.ram[addr - 0x5000]
        if addr < 0x5000:
            return self.rom[(0x1000 if self.bank else 0) | (addr & 0x0FFF)]
        return 0

    def write(self, addr, val):
        if (addr & 0xFF01) == 0x5F01:
            wd = self.wd
            reg = (addr >> 1) & 3
            if reg == 0: wd.set_command(val)
            elif reg == 1: wd.track = val
            elif reg == 2: wd.sector = val
            else: wd.set_data(val)
            return
        if 0x5000 <= addr < 0x5800:
            self.ram[addr - 0x5000] = val
