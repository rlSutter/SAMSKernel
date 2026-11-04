#!/usr/bin/env python3
"""skpic.py - pictures for the SAMS Kernel: a PNG or a TI Artist picture into a picture record the library lib/picture.a99 shows on the F18A's bitmap layer.

    python3 tools/skpic.py picture.png    -o picture.skp [--rows N] [--preview out.png]
    python3 tools/skpic.py NAME           -o picture.skp [--rows N]      (a TI Artist picture: NAME_P and NAME_C beside it)
    app.json data entry:  {"file": "harbour.skp", "from": "pics/harbour.png"}   (or "pics/HARBOUR" for TI Artist's HARBOUR_P and HARBOUR_C)

THE RECORD (all words big-endian):
    word   >5350 ('SP')                      the magic
    byte   format: 2 = 256 x rows, 4 colours (2 bits a pixel); 4 = 128 x rows "fat" pixels, 16 colours (4 bits a pixel, each two columns wide)
    byte   colours: 4 or 16
    byte   rows: 1-96 (a row is 64 bytes in both formats; the data is rows x 64 bytes)
    byte   0
    colours words: the palette, >0RGB (12 bits), loaded into F18A entries 32-
    then the pixels, run-length packed (tools/rlepack.py, TXA's format: >00-7F n+1 literal bytes, >80-FE the next byte n-7D times, >FF the end)

The conversions are TXA's (tools/tiartist.py: a TI Artist picture is cropped to 96 rows from row 48, or squeezed to half height, by NAME_T beside it; a PNG of at most 4 colours
becomes format 2 and any other format 4, in 16 colours); --rows N (default 88) then drops the bottom rows beyond N, because the free VRAM in Text 80 with no enhanced colour tiles and no
sprite patterns is >2000-35FF, 5,632 bytes, which is 88 rows of 64 bytes.  --rows 96 keeps the whole picture (6,144 bytes: it needs 512 bytes more than that run has, so the program
must give it VRAM that way, see docs/VIDEO-MODES.md).  Taken from the TXA project (MIT) and its picture format; the layer's setting is in docs/VIDEO-MODES.md part 10."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rlepack import pack, unpack

MAGIC = 0x5350


def from_png(path):
    """(format, palette words, raw 6144 bytes) as TXA's txpics makes them (a PNG)"""
    from PIL import Image
    W, H = 256, 96

    def rgb12(r, g, b):
        return (round(r / 17) << 8) | (round(g / 17) << 4) | round(b / 17)

    def encode(px, w, h, bpp):
        out, per = bytearray(), 8 // bpp
        for y in range(h):
            for x0 in range(0, w, per):
                b = 0
                for k in range(per):
                    b = (b << bpp) | (px[y * w + x0 + k] & ((1 << bpp) - 1))
                out.append(b)
        return bytes(out)
    im = Image.open(path).convert('RGB')
    colours = im.getcolors(1 << 16) or []
    if len(colours) <= 4:
        if im.size != (W, H):
            im = im.resize((W, H), Image.NEAREST)
        cols = sorted(c for _, c in im.getcolors(1 << 16))
        index = {c: i for i, c in enumerate(cols)}
        px = [index[im.getpixel((x, y))] for y in range(H) for x in range(W)]
        return 2, [rgb12(*c) for c in cols] + [0] * (4 - len(cols)), encode(px, W, H, 2)
    small = im.resize((W // 2, H), Image.LANCZOS) if im.size != (W // 2, H) else im
    q = small.quantize(colors=16, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    flat = q.getpalette()[:48]
    flat += [0] * (48 - len(flat))
    return 4, [rgb12(*flat[i * 3:i * 3 + 3]) for i in range(16)], encode(list(q.getdata()), W // 2, H, 4)


def from_tiartist(base):
    """(format, palette words, raw 6144 bytes) for NAME_P and NAME_C (tools/tiartist.py: TXA's crop or squeeze)"""
    import tiartist
    f = tiartist.find(os.path.basename(base), [os.path.dirname(base) or '.'])
    if f is None:
        sys.exit('skpic: no %s_P and %s_C (a TI Artist picture), and no %s.png' % (base, base, base))
    pat, col = tiartist.read_file(f[0]), tiartist.read_file(f[1])
    return 4, list(tiartist.TI_PALETTE), tiartist.raw(tiartist.fit(tiartist.pixels(pat, col), tiartist.settings(f[2])))


def record(source, rows=88):
    """the picture record for a PNG file or a TI Artist base name"""
    if not 1 <= rows <= 96:
        sys.exit('skpic: --rows is 1 to 96')
    fmt, pal, raw = from_png(source) if source.lower().endswith('.png') else from_tiartist(source)
    raw = raw[:rows * 64]
    out = bytearray(MAGIC.to_bytes(2, 'big'))
    out += bytes([fmt, len(pal), rows, 0])
    for v in pal:
        out += v.to_bytes(2, 'big')
    return bytes(out + pack(raw))


def parse(rec):
    """the reference reader: (format, palette words, raw pixel bytes, rows) (the tests check the assembly against it)"""
    if int.from_bytes(rec[:2], 'big') != MAGIC:
        raise ValueError('not a picture record')
    fmt, nc, rows = rec[2], rec[3], rec[4]
    pal = [int.from_bytes(rec[6 + 2 * i:8 + 2 * i], 'big') for i in range(nc)]
    return fmt, pal, unpack(rec[6 + 2 * nc:]), rows


def main(argv):
    out = rows = prev = None
    args = []
    k = 0
    while k < len(argv):
        if argv[k] == '-o':
            out = argv[k + 1]; k += 2
        elif argv[k] == '--rows':
            rows = int(argv[k + 1]); k += 2
        elif argv[k] == '--preview':
            prev = argv[k + 1]; k += 2
        else:
            args.append(argv[k]); k += 1
    if len(args) != 1 or not out:
        sys.exit(__doc__.split('THE RECORD')[0])
    rec = record(args[0], rows or 88)
    open(out, 'wb').write(rec)
    fmt, pal, raw, nrows = parse(rec)
    print('%s: format %d, %d colours, %d rows, %d bytes (%d unpacked)' % (out, fmt, len(pal), nrows, len(rec), len(raw)))
    if prev:
        from PIL import Image
        w = 256 if fmt == 2 else 128
        bpp = 2 if fmt == 2 else 4
        px = []
        for b in raw:
            for s in range(8 - bpp, -1, -bpp):
                px.append((b >> s) & ((1 << bpp) - 1))
        im = Image.new('RGB', (w, nrows))
        im.putdata([(((pal[c] >> 8) & 15) * 17, ((pal[c] >> 4) & 15) * 17, (pal[c] & 15) * 17) for c in px])
        im.resize((512, nrows * 2), Image.NEAREST).save(prev)


if __name__ == '__main__':
    main(sys.argv[1:])
