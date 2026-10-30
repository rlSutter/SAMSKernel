"""Disk geometry and the WD177x floppy disk controller chip, shared by the controller
models of the simulator (tifdc.py: TI, ccfdc.py: CorComp, myfdc.py: Myarc).

A disk image is the sectors in the order of the V9T9 format (the one xdm99 writes):
side 0 track 0 up to track T-1, then side 1 from track T-1 back down to track 0, so
the logical sector number the disk system uses is the position in the file.  The
geometry (sectors a track, tracks, sides) is read from the volume information block
in sector 0.  Ported from js99er's wd177x.ts for the single-density TI controller and
extended to double density (18 sectors a track) and two sides.  The chip models
sectors, not the stream of bits: the density bit and MFM change only how many
sectors a track holds."""


class Geometry:
    def __init__(self, image):
        v = image[0:256]
        self.spt = v[12] if v[12] in (9, 16, 18, 36) else 9
        self.tracks = v[17] if v[17] in (35, 40, 80) else 40
        self.sides = v[18] if v[18] in (1, 2) else 1
        if len(image) == 92160:                  # an uninitialised or old image: 90K
            self.spt, self.tracks, self.sides = 9, 40, 1

    def index(self, side, track, sector):
        """the sector's position in the image (in sectors)"""
        if side == 0 or self.sides == 1:
            return track * self.spt + sector
        return self.tracks * self.spt + (self.tracks - 1 - track) * self.spt + sector


class WD177x:
    """The chip: command, track, sector and data registers, status; on a disk image
    of the geometry above in drive 1 (a single drive: the models say which of the
    CRU drive-select lines they have)."""
    def __init__(self, fdc):
        self.fdc = fdc
        self.command = self.drive = self.side = self.track = self.sector = 0
        self.direction = 1
        self.data = 0
        self.busy = self.head_load_requested = self.head_loaded = False
        self.read_buffer, self.write_buffer = [], []

    def geo(self):
        return Geometry(self.fdc.image)

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
        return self.geo().index(self.side, self.track, self.sector)

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
