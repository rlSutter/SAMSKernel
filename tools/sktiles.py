#!/usr/bin/env python3
"""sktiles.py - turn a tile sheet and a map made on the PC into the data lib/scroll.a99 shows.

    python3 tools/sktiles.py --map world.csv --tiles sheet.png --out build/world [--name WORLD]
    python3 tools/sktiles.py --map world.tmx --layer Ground --subtract 1 --out build/world

THE MAP is what Tiled (mapeditor.org) writes: a CSV file (rows of comma-separated tile numbers) or a TMX
file (the layer's CSV data; --layer picks one by name, the first is used otherwise).  Tiled counts its
tiles from 1 and keeps 0 for "empty": --subtract 1 makes the first tile of the sheet tile 0.  The
flip flags in a TMX tile number are removed.  Every tile number must fit a byte (0-255).

THE TILE SHEET is a PNG of 8 x 8 tiles, side by side and in rows: the tile at the top left is the first
and they run along the row, then down.  A pixel is "set" (the foreground colour) when it is darker than
half grey, as ink on paper; --invert makes the light ones the set ones.  A transparent pixel is paper.
--first N numbers the sheet's first tile N (so two sheets can share the pattern table); a tile's
number is what a map byte holds, and the classic colour table has one entry for each group of 8 tile
numbers (the foreground and background colours as a hexadecimal pair): --colors 4:3,9:5,8:7 gives the
groups 0, 1, 2 those colours (palette entries, 1-15; 0 is transparent in a tile layer).

OUTPUT, for --out PREFIX: PREFIX-map.a99 (NAME, the map's bytes a row at a time, and the equates NAMEW and
NAMEH, its width and height in tiles), PREFIX-tiles.a99 (NAMEPAT: 8 bytes a tile, NAMECOL: the colour
table's 32 bytes, if --colors was given) and, with --bin, PREFIX-map.bin: the bytes alone, for a disk.
COPY them into a module (a map of 6,000 bytes or so fits one beside the code) and give SCRINI the map's
address and size (examples/scroll does exactly this).
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET


def read_map(path, layer=None):
    """-> (rows of ints)"""
    text = open(path, encoding='utf-8').read()
    if path.lower().endswith('.tmx') or text.lstrip().startswith('<'):
        root = ET.fromstring(text)
        layers = root.findall('layer')
        if not layers:
            raise SystemExit('sktiles: no layer in %s' % path)
        chosen = None
        for ly in layers:
            if layer is None or ly.get('name') == layer:
                chosen = ly
                break
        if chosen is None:
            raise SystemExit('sktiles: %s has no layer named %r (it has %s)' % (path, layer, ', '.join(repr(l.get('name')) for l in layers)))
        data = chosen.find('data')
        if data is None or data.get('encoding') != 'csv':
            raise SystemExit('sktiles: layer data must be CSV (Tiled: Map > Map Properties > Tile Layer Format = CSV)')
        w, h = int(chosen.get('width')), int(chosen.get('height'))
        vals = [int(v) & 0x1FFFFFFF for v in data.text.replace('\n', '').split(',') if v.strip()]
        if len(vals) != w * h:
            raise SystemExit('sktiles: layer is %d x %d but has %d tiles' % (w, h, len(vals)))
        return [vals[y * w:(y + 1) * w] for y in range(h)]
    rows = []
    for line in text.splitlines():
        line = line.strip().rstrip(',')
        if line:
            rows.append([int(v) for v in line.split(',')])
    if not rows or any(len(r) != len(rows[0]) for r in rows):
        raise SystemExit('sktiles: the rows of %s are not all the same length' % path)
    return rows


def read_tiles(path, invert=False):
    """-> a list of tiles, each 8 bytes"""
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit('sktiles: reading a PNG needs Pillow (pip install pillow)')
    im = Image.open(path).convert('RGBA')
    paper = Image.new('RGBA', im.size, (255, 255, 255, 255))
    gray = Image.alpha_composite(paper, im).convert('L')
    w, h = gray.size
    if w % 8 or h % 8:
        raise SystemExit('sktiles: the sheet is %d x %d: its sides must be multiples of 8' % (w, h))
    px = gray.load()
    tiles = []
    for ty in range(h // 8):
        for tx in range(w // 8):
            rows = []
            for y in range(8):
                b = 0
                for x in range(8):
                    on = px[tx * 8 + x, ty * 8 + y] < 128
                    if on != invert:
                        b |= 0x80 >> x
                rows.append(b)
            tiles.append(bytes(rows))
    return tiles


def parse_colors(spec):
    out = []
    for item in spec.split(','):
        fg, bg = item.split(':')
        fg, bg = int(fg), int(bg)
        if not (0 <= fg < 16 and 0 <= bg < 16):
            raise SystemExit('sktiles: colours are palette entries 0-15: %r' % item)
        out.append((fg << 4) | bg)
    if len(out) > 32:
        raise SystemExit('sktiles: the colour table has 32 entries')
    return out + [0] * (32 - len(out))


def main(argv=None):
    ap = argparse.ArgumentParser(description='tile sheet and map -> lib/scroll.a99 data')
    ap.add_argument('--map')
    ap.add_argument('--layer')
    ap.add_argument('--subtract', type=int, default=0, help='subtract this from every tile number (Tiled: 1)')
    ap.add_argument('--tiles')
    ap.add_argument('--first', type=int, default=0)
    ap.add_argument('--invert', action='store_true')
    ap.add_argument('--colors')
    ap.add_argument('--name', default='MAP')
    ap.add_argument('--out', required=True)
    ap.add_argument('--bin', action='store_true')
    a = ap.parse_args(argv)
    name = a.name.upper()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    nt = None
    if a.tiles:
        tiles = read_tiles(a.tiles, a.invert)
        nt = len(tiles)
        if a.first + nt > 256:
            raise SystemExit('sktiles: %d tiles from number %d go past 255' % (nt, a.first))
        with open(a.out + '-tiles.a99', 'w') as f:
            f.write('* %s-tiles.a99 - made by tools/sktiles.py from %s\n' % (os.path.basename(a.out), os.path.basename(a.tiles)))
            f.write('* tile numbers %d to %d, 8 bytes each: write them to the pattern table at +8 x number\n' % (a.first, a.first + nt - 1))
            f.write('%sPAT\n' % name)
            for t in tiles:
                f.write('       BYTE ' + ','.join('>%02X' % b for b in t) + '\n')
            if a.colors:
                f.write('* the classic colour table: one byte (foreground, background) for each group of 8 tile numbers\n')
                f.write('%sCOL\n' % name)
                cols = parse_colors(a.colors)
                for i in range(0, 32, 8):
                    f.write('       BYTE ' + ','.join('>%02X' % b for b in cols[i:i + 8]) + '\n')
    elif a.colors:
        raise SystemExit('sktiles: --colors goes with --tiles')
    if a.map:
        rows = [[v - a.subtract for v in r] for r in read_map(a.map, a.layer)]
        flat = [v for r in rows for v in r]
        if min(flat) < 0 or max(flat) > 255:
            raise SystemExit('sktiles: tile numbers %d to %d: they must fit a byte (0-255); is --subtract right?' % (min(flat), max(flat)))
        if nt is not None and max(flat) >= a.first + nt:
            print('sktiles: warning: the map uses tile %d but the sheet gives tiles %d to %d' % (max(flat), a.first, a.first + nt - 1))
        h, w = len(rows), len(rows[0])
        with open(a.out + '-map.a99', 'w') as f:
            f.write('* %s-map.a99 - made by tools/sktiles.py from %s: %d x %d tiles\n' % (os.path.basename(a.out), os.path.basename(a.map), w, h))
            f.write('%sW     EQU  %d\n%sH     EQU  %d\n%s\n' % (name, w, name, h, name))
            for r in rows:
                for i in range(0, w, 16):
                    f.write('       BYTE ' + ','.join(str(v) for v in r[i:i + 16]) + '\n')
        if a.bin:
            open(a.out + '-map.bin', 'wb').write(bytes(flat))
        print('sktiles: %s: %d x %d tiles, %d bytes' % (a.map, w, h, w * h))
    if a.tiles:
        print('sktiles: %s: %d tiles' % (a.tiles, nt))


if __name__ == '__main__':
    main()
