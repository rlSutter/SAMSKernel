"""The TI floppy disk controller, for the simulator: its own DSR ROM (TI's
code, not in this repository) on a WD1771, on a 90K single-sided disk image.
Ported from js99er (Rasmus Moustgaard, src/app/emulator/classes/ti-fdc.ts
and wd177x.ts), so the game's save and load can be run against the real
controller's DSR rather than the simulator's stand-in.

The ROM: js99er carries it as TI_FDC_DSR_ROM in ti-fdc.ts.  Extract it with
    python3 tools/tifdc.py --extract path/to/js99er/src/app/emulator/classes/ti-fdc.ts
which writes tools/tifdc_dsr.bin (ignored by git).  TIFDC_ROM may name
another file.

The controller sits at CRU >1100: bit 0 maps its ROM at >4000, bits 4-6
select drives 1-3, bit 7 the side.  The WD1771's registers are memory
mapped through an inverted data bus: read status, track, sector, data at
>5FF0, >5FF2, >5FF4, >5FF6; write command, track, sector, data at >5FF8,
>5FFA, >5FFC, >5FFE."""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROMFILE = os.environ.get('TIFDC_ROM', os.path.join(HERE, 'tifdc_dsr.bin'))


def blank_disk(name=b'SAMSKERNEL', sectors=360):
    """A freshly initialised single-sided, single-density disk: the volume
    information block in sector 0 (name, 360 sectors, 9 a track, 'DSK', 40
    tracks, one side, single density, the allocation bitmap with sectors 0
    and 1 in use) and an empty file index in sector 1."""
    img = bytearray(256 * sectors)
    vib = bytearray(256)
    vib[0:10] = name.ljust(10)[:10]
    vib[10:12] = sectors.to_bytes(2, 'big')
    vib[12] = 9
    vib[13:16] = b'DSK'
    vib[16] = 0x20
    vib[17] = 40
    vib[18] = 1
    vib[19] = 1
    vib[0x38] = 0x03                       # sectors 0 and 1 allocated
    for i in range(0x38 + sectors // 8, 256):
        vib[i] = 0xFF                      # beyond the disk: never free
    img[0:256] = vib
    return img


class WD1771:
    def __init__(self, fdc):
        self.fdc = fdc
        self.command = self.drive = self.side = self.track = self.sector = 0
        self.direction = 1
        self.data = 0
        self.busy = self.head_load_requested = self.head_loaded = False
        self.read_buffer, self.write_buffer = [], []

    def set_drive(self, drive, enabled):
        if enabled:
            self.drive = drive
        elif self.drive == drive:
            self.drive = 0

    def get_data(self):
        b = self.data
        if self.read_buffer:
            self.read_byte()
        return b

    def set_data(self, b):
        self.data = b
        self.write_buffer.append(b)
        if len(self.write_buffer) == 256:
            self.write_sector_out()
            self.write_buffer = []
            if self.command == 0xB0:
                self.sector += 1

    def set_command(self, c):
        self.command = c
        flags = c & 0x0F
        hi = c & 0xF0
        if hi == 0x00:                           # restore
            self.track = 0; self._head(flags); self.busy = True
        elif hi == 0x10:                         # seek
            self.track = self.data; self._head(flags); self.busy = True
        elif hi in (0x20, 0x30):
            self._step(bool(c & 0x10), flags)
        elif hi in (0x40, 0x50):
            self.direction = 1; self._step(bool(c & 0x10), flags)
        elif hi in (0x60, 0x70):
            self.direction = -1; self._step(bool(c & 0x10), flags)
        elif hi in (0x80, 0x90):                 # read sector
            self.read_sector_in(); self.read_byte(); self.load_head()
        elif hi in (0xA0, 0xB0):                 # write sector
            self.write_buffer = []
        elif hi == 0xC0:                         # read ID
            self.read_buffer += [self.track, self.side, self.sector, 1, 0, 0]
            self.read_byte(); self.load_head(); self.busy = True
        elif hi == 0xD0:                         # force interrupt
            self.busy = False

    def _head(self, flags):
        if flags & 0x08:
            self.load_head()

    def _step(self, update, flags):
        if update:
            self.track = min(self.track + 1, 255) if self.direction > 0 else max(self.track - 1, 0)
        self._head(flags)
        self.busy = True

    def status(self):
        track0 = self.track == 0 and ((self.command & 0x80) == 0 or (self.command & 0xF0) == 0xD0)
        s = (0x20 if self.head_loaded else 0) | (0x04 if track0 else 0) | (0x01 if self.busy else 0)
        self.busy = False
        return s

    def load_head(self):
        self.head_load_requested = self.head_loaded = True

    def _index(self):
        if self.side == 0:
            return self.track * 9 + self.sector
        return 180 + (40 - 1 - self.track) * 9 + self.sector

    def read_sector_in(self):
        img = self.fdc.image if self.drive == 1 else None
        if img is not None:
            i = self._index() * 256
            self.read_buffer += list(img[i:i + 256])

    def read_byte(self):
        self.data = self.read_buffer.pop(0) if self.read_buffer else 0
        if not self.read_buffer and (self.command & 0xF0) == 0x90:
            self.sector += 1
            self.read_sector_in()

    def write_sector_out(self):
        img = self.fdc.image if self.drive == 1 else None
        if img is not None:
            i = self._index() * 256
            img[i:i + 256] = bytes(self.write_buffer)
            self.fdc.writes += 1


class TIFDC:
    CRU = 0x880                                 # >1100 / 2

    def __init__(self, image=None, rom=None):
        if rom is None:
            if not os.path.exists(ROMFILE):
                raise FileNotFoundError(f"the TI controller's DSR ROM is not at {ROMFILE}: see tools/tifdc.py")
            rom = open(ROMFILE, 'rb').read()
        self.rom = rom
        self.rom_on = False
        self.motor_strobe = False
        self.image = image if image is not None else blank_disk()
        self.wd = WD1771(self)
        self.writes = 0

    def cru_write(self, n, v):
        if n == 0: self.rom_on = bool(v)
        elif n == 1:
            if v: self.motor_strobe = True
        elif n == 3:
            if v: self.wd.load_head()
        elif n in (4, 5, 6): self.wd.set_drive(n - 3, bool(v))
        elif n == 7: self.wd.side = 1 if v else 0

    def cru_read(self, n):
        if n == 0: return self.wd.head_load_requested
        if n in (1, 2, 3): return self.wd.drive == n
        if n == 4: return not self.motor_strobe
        if n == 5: return False
        if n == 6: return True
        if n == 7: return self.wd.side != 0
        return False

    def read(self, addr):
        """a byte read in >4000->5FFF while the ROM is on"""
        if 0x5FF0 <= addr < 0x5FF8:
            if addr & 1: return 0xFF
            r = {0x5FF0: self.wd.status, 0x5FF2: lambda: self.wd.track,
                 0x5FF4: lambda: self.wd.sector, 0x5FF6: self.wd.get_data}[addr]()
            return (r ^ 0xFF) & 0xFF
        return self.rom[addr - 0x4000]

    def write(self, addr, val):
        if addr & 1: return
        b = (val ^ 0xFF) & 0xFF
        if addr == 0x5FF8: self.wd.set_command(b)
        elif addr == 0x5FFA: self.wd.track = b
        elif addr == 0x5FFC: self.wd.sector = b
        elif addr == 0x5FFE: self.wd.set_data(b)

    def files(self):
        """the files on the disk, as the file index and descriptors record
        them: name -> (type flags, sectors used, bytes in the last sector)"""
        out = {}
        index = self.image[256:512]
        for k in range(0, 256, 2):
            s = (index[k] << 8) | index[k + 1]
            if s == 0: break
            fdr = self.image[s * 256:(s + 1) * 256]
            out[bytes(fdr[0:10]).decode('ascii', 'replace').rstrip()] = (fdr[12], (fdr[14] << 8) | fdr[15], fdr[16])
        return out


def read_file(image, name):
    """A file's records, read straight from a disk image (the file index in
    sector 1, the file descriptor, its chain of sector clusters): a list of
    byte strings, or None if the file is not there.  For the tests: what is
    on the disk, independent of Press and of the controller."""
    index = image[256:512]
    for k in range(0, 256, 2):
        s = (index[k] << 8) | index[k + 1]
        if s == 0:
            return None
        fdr = image[s * 256:(s + 1) * 256]
        if bytes(fdr[0:10]).decode('ascii', 'replace').rstrip() == name:
            break
    else:
        return None
    flags, per, used, eof, reclen = fdr[12], fdr[13], (fdr[14] << 8) | fdr[15], fdr[16], fdr[17]
    nrecs = fdr[18] | (fdr[19] << 8)
    sectors, k = [], 28
    while k + 3 <= 256 and len(sectors) < used:
        b0, b1, b2 = fdr[k], fdr[k + 1], fdr[k + 2]
        start = b0 | ((b1 & 0x0F) << 8)
        last = (b1 >> 4) | (b2 << 4)                    # the file's last sector index so far
        if start == 0 and last == 0:
            break
        for sct in range(start, start + last - len(sectors) + 1):
            sectors.append(sct)
        k += 3
    recs = []
    if flags & 0x80:                                    # variable: length-prefixed, >FF ends a sector
        for i, sct in enumerate(sectors[:used]):
            data = image[sct * 256:(sct + 1) * 256]
            p = 0
            while p < 256 and data[p] != 0xFF:
                n = data[p]
                recs.append(bytes(data[p + 1:p + 1 + n]))
                p += 1 + n
    else:                                               # fixed: `per` records of `reclen` a sector
        for sct in sectors[:used]:
            data = image[sct * 256:(sct + 1) * 256]
            for j in range(per):
                recs.append(bytes(data[j * reclen:(j + 1) * reclen]))
        recs = recs[:nrecs]
    return recs


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--extract':
    s = open(sys.argv[2]).read()
    m = re.search(r'TI_FDC_DSR_ROM\s*=\s*\[(.*?)\]', s, re.S)
    rom = bytes(int(v, 0) for v in re.findall(r'0x[0-9a-fA-F]+|\d+', m.group(1)))
    open(ROMFILE, 'wb').write(rom)
    print(f"wrote {ROMFILE}: {len(rom)} bytes")
