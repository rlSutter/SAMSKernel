#!/usr/bin/env python3
# Vendored from the TXA project (tools/tiartist.py), MIT, (c) 2026 Rebecca Sutter; tools/skpic.py builds the kernel's picture records on it.
"""tiartist.py - TI Artist pictures for TXA (M6 part 9): the reference the
workbench's import (I) must match byte for byte.

A TI Artist picture is two PROGRAM files of 6144 bytes each, NAME_P (the
pattern table) and NAME_C (the colour table): the 9918A's bitmap mode,
256 x 192 pixels in 8 x 8 cells, two of the TI's 16 colours for each
8-pixel row (foreground in the high nybble).  On a PC they usually carry a
128-byte TIFILES header, which is skipped.

A TXA picture (tools/txpics.py) is format 4: 128 x 96 "fat" pixels, 16
colours, shown in the 96 rows above the text.  So the picture is fitted
one of two ways (Rebecca, 28 October 2026: both, crop the default):
  crop ROW   the 96 rows from ROW (0-96, even), full width: the proportions
             kept, the rest of the picture left out
  squeeze    the whole picture at half height: each pair of rows becomes
             one
Then each pair of pixels becomes one fat pixel.  The rules, simple enough
for the TI:
  two pixels (a pair across, or in squeeze a pair down): the first, unless
  it is background (colours 0 and 1, transparent and black) and the second
  is not; then the second.
The palette is the TI's own 16 colours (12-bit), transparent shown black;
the pixels are packed with tools/rlepack.py.

A picture's choice is kept in NAME_T beside it (a TI file name cannot hold
a full stop), one line: "crop 48" or "squeeze"; with none, crop 48 (the
middle).  On the TI it is a DIS/VAR 80 file; on a PC, plain text.

  python3 tools/tiartist.py NAME [crop ROW | squeeze]   writes NAME.png, the preview
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rlepack import pack

# the TI's 16 colours (9918A), as 12-bit RGB; 0 (transparent) as black
TI_PALETTE = [0x000, 0x000, 0x2C3, 0x5D6, 0x54F, 0x76F, 0xD54, 0x4EF,
              0xF54, 0xF76, 0xDC5, 0xED8, 0x2B3, 0xC5B, 0xCCC, 0xFFF]
DEFAULT = ('crop', 48)

def read_file(path):
    d = open(path, 'rb').read()
    if d[:8] == b'\x07TIFILES':
        d = d[128:]
    if len(d) < 6144:
        raise ValueError(f'{path}: {len(d)} bytes, not a TI Artist file (6144)')
    return d[:6144]

def pixels(pat, col):
    """The 256 x 192 picture as rows of colour numbers (0-15)."""
    rows = [[0] * 256 for _ in range(192)]
    for cell in range(768):
        cx, cy = (cell % 32) * 8, (cell // 32) * 8
        for r in range(8):
            p, c = pat[cell * 8 + r], col[cell * 8 + r]
            fg, bg = c >> 4, c & 15
            row = rows[cy + r]
            for b in range(8):
                row[cx + b] = fg if p & (0x80 >> b) else bg
    return rows

def pick(a, b):
    """Two pixels into one: the first, unless it is background and the
    second is not."""
    return b if a <= 1 and b > 1 else a

def fit(rows, how):
    """96 rows of 128 fat pixels, by ('crop', row) or ('squeeze', 0)."""
    mode, row = how
    if mode == 'crop':
        if not 0 <= row <= 96 or row % 2:
            raise ValueError(f'crop {row}: the band starts at an even row, 0-96')
        band = rows[row:row + 96]
    else:
        band = [[pick(rows[2 * y][x], rows[2 * y + 1][x]) for x in range(256)] for y in range(96)]
    return [[pick(r[2 * x], r[2 * x + 1]) for x in range(128)] for r in band]

def raw(fat):
    """Format 4's 6144 bytes: two pixels a byte, the left in the high nybble."""
    out = bytearray()
    for r in fat:
        for x in range(0, 128, 2):
            out.append((r[x] << 4) | r[x + 1])
    return bytes(out)

def record(pat, col, how=DEFAULT):
    """The TXA picture record (as txpics.record makes from a PNG)."""
    data = raw(fit(pixels(pat, col), how))
    out = bytearray([4, 16])
    for v in TI_PALETTE:
        out += v.to_bytes(2, 'big')
    return bytes(out + pack(data))

def settings(base):
    """NAME_T's choice, or the default."""
    for ext in ('_T', '_t', '-T'):
        p = base + ext
        if os.path.exists(p):
            words = open(p).read().split()
            if words and words[0].lower() == 'squeeze':
                return ('squeeze', 0)
            if len(words) == 2 and words[0].lower() == 'crop':
                return ('crop', int(words[1]))
            raise ValueError(f'{p}: "crop ROW" or "squeeze"')
    return DEFAULT

def find(name, dirs):
    """(NAME_P path, NAME_C path, base) for a TI Artist picture, or None."""
    for d in dirs:
        for cand in (name, name.upper(), name.lower()):
            for sep in ('_', '-'):
                p, c = (os.path.join(d, cand + sep + s) for s in ('P', 'C'))
                if os.path.exists(p) and os.path.exists(c):
                    return p, c, os.path.join(d, cand)
    return None

def preview(pat, col, how):
    """What the TI shows: a PIL image at 4 x 2 (512 x 192)."""
    from PIL import Image
    fat = fit(pixels(pat, col), how)
    im = Image.new('RGB', (128, 96))
    im.putdata([(((TI_PALETTE[c] >> 8) & 15) * 17, ((TI_PALETTE[c] >> 4) & 15) * 17, (TI_PALETTE[c] & 15) * 17)
                for r in fat for c in r])
    return im.resize((512, 192), Image.NEAREST)

if __name__ == '__main__':
    name = sys.argv[1]
    how = ('squeeze', 0) if 'squeeze' in sys.argv[2:] else (('crop', int(sys.argv[3])) if len(sys.argv) > 3 else DEFAULT)
    f = find(os.path.basename(name), [os.path.dirname(name) or '.'])
    if not f:
        sys.exit(f'no {name}_P and {name}_C')
    pat, col = read_file(f[0]), read_file(f[1])
    preview(pat, col, how).save(name + '.png')
    print(f'{name}.png: {how[0]} {how[1] if how[0] == "crop" else ""}; the record is {len(record(pat, col, how))} bytes')
