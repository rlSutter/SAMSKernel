"""The Myarc HFDC (Hard and Floppy Disk Controller) card, for the simulator: its own DSR ROM
(hfdc_dsr.u34, 16K, in roms/).  WORK IN PROGRESS: the card's glue is modelled from MAME's
description of it (src/devices/bus/ti99/peb/hfdc.cpp, Michael Zapf; LGPL-2.1+; this is written from
that description, not copied); the disk controller chip, an SMC HDC9234, is modelled at the level of
sectors for FLOPPY disks only (hard disks are not modelled), from the card's own DSR source, which the
project owner supplied (an archive of Myarc's assembly source: the chip's registers and commands are in
SECTORIOF, FORM345, SAVFAC and EQUATES), and from the ROM, which then runs.

The card:
  ROM      16K = four 4K pages, one at a time at >4000-4FBF; the page is CRU latch bits 3 (value 2)
           and 4 (value 1)
  chip     the HDC9234's ports: read >4FD0,4,8,C (register (address / 4) mod 2: 0 data, 1 status);
           write >4FD2,6,A,E (0 data, 1 command)
  clock    an MM58274 real-time clock at >4FE0-4FFF (here: reads 0)
  RAM      32K in 1K pages (the buffer the chip does its DMA to): >5000-53FF page 8 always;
           >5400, >5800, >5C00: any of 32 pages, chosen by CRU latch bits 9-13, 14-18, 19-23
  DMA      the chip, driving its auxiliary bus: byte-wide transfers shifted into a DMA address,
           then it reads or writes the RAM at that address, incrementing
  CRU out  latch: 0 select card (maps the ROM), 1 chip reset (0 = reset), 2 motor on (and clock divider
           bit 0), 3 ROM page bit 1 (clock divider bit 1), 4 ROM page bit 0 and 'show the switches'
           (CRU input select), 9-23 RAM page selects
  CRU in   bits 0-7: with the select bit (latch 4) 1 the drive-configuration switches, else
           bit 0 IRQ, bit 1 DMA in progress, bit 2 motor running
  aux bus  output 1 (drive select: low nibble floppy DSK4..DSK1, bit 4 'a floppy', bits 5-7 hard
           disks), output 2 (head, step, direction), input (drive status: index, track 0, ...)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tifdc import blank_disk

HERE = os.path.dirname(os.path.abspath(__file__))


def _rom():
    p = os.environ.get('HFDC_ROM') or next((x for x in (os.path.join(HERE, '..', 'roms', 'hfdc_dsr.u34'), '/home/claude/rom/hfdc_dsr.u34') if os.path.exists(x)), None)
    if not p:
        raise FileNotFoundError('the HFDC ROM hfdc_dsr.u34 is not found: set HFDC_ROM')
    return open(p, 'rb').read()


def available():
    try:
        _rom()
        return True
    except FileNotFoundError:
        return False


class StubChip:
    """An HDC9234 that does nothing and says what it was asked (kept for working things out)."""
    def __init__(self, card):
        self.card = card
        self.log = []                 # ('cmd'|'data'|'read0'|'read1', value)

    def read(self, reg):
        self.log.append(('read%d' % reg, 0))
        return 0

    def write(self, reg, val):
        self.log.append(('cmd' if reg else 'data', val))


class HDC9234:
    """The SMC HDC9234, for floppy disks, at the level of sectors.

    The DSR (Myarc's source: SECTORIOF, FORM345, SAVFAC) drives it like this.  Port 1 written is a COMMAND,
    port 0 written is DATA, port 1 read is the STATUS (reading it clears the interrupt), port 0 read is a
    register read.  Commands used:
      >01        deselect the drive
      >02,>03    restore (cylinder 0)
      >04 / >06  step in / step out one cylinder (>05, >07 likewise)
      >20-2F     select the drive named by register 7's low nibble (1 DSK1, 2 DSK2, 4, 8) and its step rate
      >40-47     set the register POINTER to 0-7: each data written then goes to that register and the
                 pointer moves on (registers: 0,1,2 DMA address, low byte first, into the card's RAM;
                 3 sector; 4 head (and the cylinder's high bits); 5 cylinder; 6 sector count; 7 drive)
      >48,>49    the next port-0 read gives: >48 the termination status, >49 the drive status
                 (bit 1 ready, bit 2 write protected, bit 4 track 0, bit 5 seek complete)
      >5C-5F     read sectors (the DSR sends >5D: an implied seek to cylinder 5, head 4, sector 3, 6 of them)
      >B0-B3     write sectors (the DSR sends >B0 or >B2)
      >70        format a track (not modelled: reported done)
    After the waited-for commands (the ones above except the pointer settings) the interrupt line (CRU
    input 0) goes high; the DSR waits for it, reads the status and keeps bits >08 and >10 as 'error'.
    The density the chip is working in is not in a register: the card's clock-divider bits (CRU outputs 2
    and 3, set by the DSR around each command) say it: CD0=0, CD1=1 single, CD0=1, CD1=0 double, 0,0 high.
    A command on a disk of the other density finds no record (error)."""
    def __init__(self, card):
        self.card = card
        self.regs = [0] * 16
        self.ptr = 0
        self.rmode = 0
        self.irq = False
        self.status = 0
        self.cyl = 0
        self.drive = 0               # 0: none, 1..4
        self.cmds = []

    def reset(self):
        self.regs = [0] * 16
        self.ptr = 0
        self.irq = False
        self.status = 0

    def _geo(self):
        from fdc import Geometry
        return Geometry(self.card.image)

    def drive_status(self):
        if self.drive != 1:
            return 0
        s = 0x22                      # ready, seek complete
        if self.cyl == 0:
            s |= 0x10                 # track 0
        return s

    def read(self, reg):
        if reg == 1:
            self.irq = False
            return self.status
        if self.rmode == 0x49:
            return self.drive_status()
        return 0

    def write(self, reg, val):
        if reg == 0:
            self.regs[self.ptr & 15] = val
            self.ptr += 1
            return
        self.command(val)

    def _density_matches(self):
        cd0, cd1 = self.card.cru[2], self.card.cru[3]
        want = 1 if (cd1 and not cd0) else (2 if (cd0 and not cd1) else 0)
        return want == self._geo().density

    def command(self, c):
        self.cmds.append(c)
        if 0x40 <= c < 0x48:
            self.ptr = c & 7
            return
        if 0x48 <= c < 0x50:
            self.rmode = c
            return
        self.irq = False
        self.status = 0
        r = self.regs
        if c == 0x01:
            self.drive = 0
        elif c in (0x02, 0x03):
            self.cyl = 0
        elif (c & 0xFC) == 0x04:
            self.cyl = max(0, self.cyl + (1 if not (c & 2) else -1))
        elif 0x20 <= c < 0x30:
            self.drive = {1: 1, 2: 2, 4: 3, 8: 4}.get(r[7] & 0x0F, 0)
        elif (c & 0xFC) == 0x5C or (c & 0xFC) == 0xB0:
            self._sectors((c & 0xFC) == 0xB0)
        elif c == 0x70:
            pass                       # format: not modelled
        self.irq = True

    def _sectors(self, write):
        r = self.regs
        if self.drive != 1 or not self._density_matches():
            self.status = 0x08          # no drive, or no record of this density
            return
        cyl = r[5]
        head = r[4] & 0x0F
        sector = r[3]
        count = r[6] or 1
        dma = r[0] | r[1] << 8 | r[2] << 16
        geo = self._geo()
        for k in range(count):
            self.card.sector_log['w' if write else 'r'].append((head, cyl, sector + k))
            i = geo.index(head, cyl, sector + k) * 256
            if i + 256 > len(self.card.image):
                self.status = 0x08
                return
            for n in range(256):
                a = (dma + k * 256 + n) & 0x7FFF
                if write:
                    self.card.image[i + n] = self.card.ram[a]
                else:
                    self.card.ram[a] = self.card.image[i + n]
            if write:
                self.card.writes += 1
        self.cyl = cyl


class HFDC:
    cru_base, cru_bits = 0x880, 24                # CRU >1100, bits 0-23

    def __init__(self, image=None, chip=None):
        self.rom = _rom()
        self.rom_on = False
        self.image = image if image is not None else blank_disk(sectors=1440)
        self.ram = bytearray(0x8000)
        self.ram_page = [8, 0, 0, 0]
        self.rom_page = 0
        self.see_switches = False
        self.motor = False
        self.irq = False
        self.dip = False
        self.dma_address = 0
        self.output1 = self.output2 = 0
        self.writes = 0
        self.sector_log = {'r': [], 'w': []}        # (head, cylinder, sector) of every sector moved, for the tests
        self.cru = [0] * 24
        self.log = []
        self.chip = chip or HDC9234(self)

    # ---- CRU
    def cru_write(self, n, v):
        v = 1 if v else 0
        self.log.append(('w', n, v))
        self.cru[n] = v
        if 9 <= n < 24:
            page = (n - 4) // 5
            bit = 1 << ((n - 9) % 5)
            if v: self.ram_page[page] |= bit
            else: self.ram_page[page] &= ~bit
            return
        if n == 0: self.rom_on = bool(v)
        elif n == 1 and not v and hasattr(self.chip, 'reset'): self.chip.reset()
        elif n == 2: self.motor = bool(v)
        elif n == 3: self.rom_page = (self.rom_page | 2) if v else (self.rom_page & 1)
        elif n == 4:
            self.see_switches = bool(v)
            self.rom_page = (self.rom_page | 1) if v else (self.rom_page & 2)

    def cru_read(self, n):
        self.log.append(('r', n, 0))
        if n < 8:
            if self.see_switches:
                return not ((0x00 >> n) & 1) if False else True    # all switches off (40 tracks, 16 ms)
            return {0: getattr(self.chip, 'irq', False), 1: self.dip, 2: self.motor}.get(n, False)
        return False

    # ---- memory
    def read(self, addr):
        if 0x4FD0 <= addr < 0x4FE0 and (addr & 0x1FF3) == 0x0FD0:
            return self.chip.read((addr >> 2) & 1)
        if 0x4FC0 <= addr < 0x5000:
            return 0
        if addr < 0x5000:
            return self.rom[(self.rom_page << 12) | (addr & 0xFFF)]
        bank = (addr & 0x0C00) >> 10
        return self.ram[(self.ram_page[bank] << 10) | (addr & 0x3FF)]

    def write(self, addr, val):
        if 0x4FD0 <= addr < 0x4FE0 and (addr & 0x1FF3) == 0x0FD2:
            self.chip.write((addr >> 2) & 1, val)
            return
        if addr >= 0x5000:
            bank = (addr & 0x0C00) >> 10
            self.ram[(self.ram_page[bank] << 10) | (addr & 0x3FF)] = val
