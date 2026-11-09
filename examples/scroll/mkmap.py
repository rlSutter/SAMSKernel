#!/usr/bin/env python3
"""mkmap.py - makes the world of examples/scroll: map.a99 (112 x 56 tiles: water, sand, grass, forest,
rock, paths, houses and flowers) and tiles.a99 (the palette, the colour table and the patterns).

    python3 examples/scroll/mkmap.py          writes both next to this file

The tests import it (make(), PAL, CTAB, PATS) to draw the picture the example should show.  A tile
number is its type x 8 + a variant (0 or 1): the layer's classic colour table has one entry for
each group of 8 tiles, so a type is a group.
"""
import os, random

MW, MH = 112, 56
WATER, SAND, GRASS, FOREST, ROCK, PATH, HOUSE, FLOWER = range(8)

# palette entries 1-15 (>0RGB): 0 is "transparent" in a tile layer
PAL = [0x0222, 0x025A, 0x04AE, 0x0ACF, 0x0EDA, 0x0262, 0x04A3, 0x07D5, 0x0853, 0x0888, 0x0DDD, 0x0D33, 0x0FD3, 0x0F8C, 0x0A64]
# the colour table: foreground / background palette entries of each type's group of 8 tiles
CTAB = [0x43, 0x95, 0x87, 0x67, 0xBA, 0xF9, 0xCB, 0xE7] + [0x00] * 24
# two 8 x 8 patterns for each type (tile = type x 8 + variant)
PATS = [
    [0x00, 0x66, 0x99, 0x00, 0x00, 0x66, 0x99, 0x00], [0x00, 0x33, 0xCC, 0x00, 0x00, 0x33, 0xCC, 0x00],
    [0x00, 0x10, 0x00, 0x04, 0x00, 0x40, 0x00, 0x08], [0x02, 0x00, 0x20, 0x00, 0x08, 0x00, 0x80, 0x00],
    [0x00, 0x08, 0x00, 0x00, 0x20, 0x00, 0x00, 0x04], [0x10, 0x00, 0x00, 0x40, 0x00, 0x02, 0x00, 0x00],
    [0x18, 0x3C, 0x7E, 0xFF, 0x7E, 0x18, 0x18, 0x00], [0x00, 0x3C, 0x7E, 0x7E, 0x3C, 0x00, 0x00, 0x00],
    [0x00, 0x18, 0x3C, 0x7E, 0x7E, 0x3C, 0x00, 0x00], [0x00, 0x00, 0x1C, 0x3E, 0x7E, 0x3C, 0x00, 0x00],
    [0x00, 0x00, 0x24, 0x00, 0x00, 0x42, 0x00, 0x00], [0x00, 0x08, 0x00, 0x00, 0x20, 0x00, 0x04, 0x00],
    [0xFF, 0xFF, 0xFF, 0x00, 0xFF, 0xFF, 0xFF, 0x00], [0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55, 0xAA, 0x55],
    [0x00, 0x08, 0x1C, 0x08, 0x00, 0x00, 0x00, 0x00], [0x00, 0x00, 0x00, 0x00, 0x20, 0x70, 0x20, 0x00],
]


def tile_number(i):
    """the tile number of pattern i of PATS"""
    return ((i >> 1) << 3) | (i & 1)


def make():
    rnd = random.Random(2026)
    gw, gh = 16, 9
    grid = [[rnd.random() for _ in range(gw)] for _ in range(gh)]
    def height(x, y):
        fx, fy = x * (gw - 1) / (MW - 1), y * (gh - 1) / (MH - 1)
        x0, y0 = int(fx), int(fy)
        x1, y1 = min(gw - 1, x0 + 1), min(gh - 1, y0 + 1)
        tx, ty = fx - x0, fy - y0
        tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        a = grid[y0][x0] * (1 - tx) + grid[y0][x1] * tx
        b = grid[y1][x0] * (1 - tx) + grid[y1][x1] * tx
        return a * (1 - ty) + b * ty
    typ = [[GRASS] * MW for _ in range(MH)]
    for y in range(MH):
        for x in range(MW):
            h = height(x, y)
            typ[y][x] = WATER if h < 0.36 else SAND if h < 0.42 else GRASS if h < 0.62 else FOREST if h < 0.75 else ROCK
    for x in range(MW):                         # a road across and one down, over the land
        for y in (27, 28):
            if typ[y][x] != WATER:
                typ[y][x] = PATH
    for y in range(MH):
        for x in (55, 56):
            if typ[y][x] != WATER:
                typ[y][x] = PATH
    for hx, hy in ((20, 20), (36, 33), (70, 18), (84, 36), (96, 12), (12, 40), (48, 9), (62, 40)):
        for dy in range(2):
            for dx in range(3):
                if 0 <= hx + dx < MW and 0 <= hy + dy < MH and typ[hy + dy][hx + dx] in (GRASS, FOREST, SAND):
                    typ[hy + dy][hx + dx] = HOUSE
    for y in range(MH):
        for x in range(MW):
            if typ[y][x] == GRASS and rnd.random() < 0.05:
                typ[y][x] = FLOWER
    return [[typ[y][x] * 8 + ((x * 7 + y * 13 + (x * y)) & 1) for x in range(MW)] for y in range(MH)]


def write(here=os.path.dirname(os.path.abspath(__file__))):
    mp = make()
    with open(os.path.join(here, 'map.a99'), 'w') as f:
        f.write('* map.a99 - the world of examples/scroll (mkmap.py): %d x %d tiles\nMAP\n' % (MW, MH))
        for row in mp:
            for i in range(0, MW, 16):
                f.write('       BYTE ' + ','.join(str(v) for v in row[i:i + 16]) + '\n')
    with open(os.path.join(here, 'tiles.a99'), 'w') as f:
        f.write('* tiles.a99 - the palette, colours and patterns (mkmap.py)\n')
        f.write('PAL\n' + ''.join('       DATA >%04X\n' % v for v in PAL))
        f.write('CTAB\n' + ''.join('       BYTE ' + ','.join('>%02X' % v for v in CTAB[i:i + 8]) + '\n' for i in range(0, 32, 8)))
        f.write('PATS\n' + ''.join('       BYTE ' + ','.join('>%02X' % v for v in p) + '\n' for p in PATS))


if __name__ == '__main__':
    write()
