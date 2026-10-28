#!/usr/bin/env python3
"""f18render.py - draw what the F18A would show, from the simulator's VRAM,
registers and palette.

    import f18render
    img = f18render.render(m)            # numpy array (height, width, 3), uint8
    f18render.save(m, 'screen.png')

Covers every display mode of the F18A: Graphics I, Graphics II (bitmap), Text 40,
Text 80, Multicolor; enhanced colour modes 1-3 for tiles and sprites; tile layers
1 and 2 with hardware scroll and page sizes; the bitmap layer (4 colours, or 16
with fat pixels); sprites (8 x 8, 16 x 16, magnified, linked, flipped, up to 32 a
line, fifth-sprite and collision flags are not reported); 24 or 30 rows; the 64-entry
palette.  Not drawn: scan lines, the border, GPU-driven effects between lines.

The drawing rules are those of js99er's F18A (src/emu/f18a.js, by Rasmus Moustgaard,
from the F18A's documentation), restated in Python; the hardware is the reference.
The image is the active area only: 256 x 192 (or 240 rows), 512 wide in Text 80.
"""
import numpy as np

DEFAULT_PALETTE = '000 000 2C3 5D6 54F 76F D54 4EF F54 F76 DC3 ED6 2B2 C5C CCC FFF 000 2C3 000 54F 000 D54 000 4EF 000 CCC 000 DC3 000 C5C 000 FFF 000 00A 0A0 0AA A00 A0A A50 AAA 555 55F 5F5 5FF F55 F5F FF5 FFF 000 555 000 00A 000 0A0 000 0AA 000 A00 000 A0A 000 A50 000 FFF'.split()

def palette_rgb(m):
    pal = [tuple(int(c, 16) * 17 for c in e) for e in DEFAULT_PALETTE]
    for idx, val in m.palette.items():
        if 0 <= idx < 64:
            pal[idx] = (((val >> 8) & 0xF) * 17, ((val >> 4) & 0xF) * 17, (val & 0xF) * 17)
    return pal

GRAPHICS, TEXT, TEXT80, BITMAP, MULTI = range(5)
MODE_NAMES = ['Graphics I', 'Text 40', 'Text 80', 'Graphics II (bitmap)', 'Multicolor']

def mode_of(m):
    v = m.vregs
    if (v[0] & 2) and (v[1] & 0x18) == 0:
        return BITMAP
    k = (v[1] & 0x18) >> 3
    if k == 0: return GRAPHICS
    if k == 1: return MULTI
    if k == 2: return TEXT80 if (v[0] & 4) else TEXT
    return GRAPHICS

def render(m):
    v, ram, pal = m.vregs, m.vram, palette_rgb(m)
    unl = m.unlocked and m.f18a
    mode = mode_of(m)
    t80 = mode == TEXT80
    textlike = mode in (TEXT, TEXT80)
    row30 = bool(v[49] & 0x40) and unl
    ecm = (v[49] & 0x30) >> 4 if unl else 0
    sprecm = v[49] & 3 if unl else 0
    posattr = bool(v[50] & 2) and unl
    tl1 = not (v[50] & 0x10) if unl else True
    tl2 = bool(v[49] & 0x80) and unl
    tl2top = not (v[50] & 1) if unl else True
    realy = bool(v[49] & 8) and unl
    linking = bool(v[49] & 4) and unl
    drawW = 512 if t80 else 256
    drawH = 240 if row30 else 192
    nt = (v[2] & (0xF if (not t80 or unl) else 0xC)) << 10
    if mode == BITMAP:
        ct = (v[3] & 0x80) << 6; pt = (v[4] & 4) << 11
        ctmask = ((v[3] & 0x7F) << 6) | 0x3F
        ptmask = ((v[4] & 3) << 11) | (ctmask & 0x7FF)
    else:
        ct = v[3] << 6; pt = (v[4] & 7) << 11; ctmask = ptmask = 0x3FFF
    sat = (v[5] & 0x7F) << 7; spt = (v[6] & 7) << 11
    fg, bg = (v[7] & 0xF0) >> 4, v[7] & 0xF
    nt2 = (v[10] & 0xF) << 10; ct2 = v[11] << 6
    spal = v[24] & 0x30; tpal = (v[24] & 3) << 4; tpal2 = (v[24] & 0xC) << 2
    hs2, vs2, hs1, vs1 = v[25], v[26], v[27], v[28]
    hp1 = (v[29] & 2) << 9; vp1 = (v[29] & 1) << 11
    hp2 = (v[29] & 0x20) << 5; vp2 = (v[29] & 0x10) << 7
    splane = 0x100 << (3 - ((v[29] & 0xC0) >> 6)); tplane = 0x100 << (3 - ((v[29] & 0x0C) >> 2))
    maxscan = v[30] if v[30] else 32
    if maxscan == 31: maxscan = 32
    bmp_on = bool(v[31] & 0x80) and unl
    bmp_prio = bool(v[31] & 0x40); bmp_trans = bool(v[31] & 0x20); bmp_fat = bool(v[31] & 0x10)
    bmp_pal = (v[31] & (0x0C if bmp_fat else 0x0F)) << 2
    bmp_base = v[32] << 6; bmp_x = v[33]; bmp_y = v[34]
    bmp_w = v[35] or 256; bmp_h = v[36]
    maxspr = v[51] & 0x3F if unl else 32
    img = np.zeros((drawH, drawW, 3), np.uint8)
    border = 8 if mode == TEXT else (16 if t80 else 0)
    scrollW = drawW - 2 * border
    scrollH = drawH
    hshift = 1 if t80 else 0
    sprsize = (v[1] & 2) >> 1; sprmag = v[1] & 1

    def tile_layer(x, y1row, nbase, ctab, hsc, hpage, vpage, tpalsel, y1, ncanon):
        """-> (color, palbase, priority, transparent0) for pixel x of a row."""
        x1 = x - border + (hsc << hshift)
        naddr = nbase
        if x1 >= scrollW:
            x1 -= scrollW; naddr ^= hpage
        if mode == GRAPHICS:
            naddr += (x1 >> 3) + y1row
            ch = ram[naddr & 0x3FFF]; bs = x1 & 7; ly = y1 & 7
            attr = 0; prio = False; t0 = True
            if ecm:
                attr = ram[(ctab + (naddr - ncanon if posattr else ch)) & 0x3FFF]
                prio = bool(attr & 0x80)
                if attr & 0x40: bs = 7 - bs
                if attr & 0x20: ly = 7 - ly
                t0 = bool(attr & 0x10)
            bit = 0x80 >> bs
            pa = (pt + (ch << 3) + ly) & 0x3FFF
            pb = ram[pa]
            if ecm == 0:
                cs = ram[(ctab + (ch >> 3)) & 0x3FFF]
                col = (cs & 0xF0) >> 4 if pb & bit else cs & 0xF
                return col, tpalsel, False, True
            c = (pb & bit) >> (7 - bs)
            if ecm == 1:
                return c, (tpalsel & 0x20) | ((attr & 0xF) << 1), prio, t0
            c |= ((ram[(pa + tplane) & 0x3FFF] & bit) >> (7 - bs)) << 1
            if ecm == 2:
                return c, (attr & 0xF) << 2, prio, t0
            c |= ((ram[(pa + 2 * tplane) & 0x3FFF] & bit) >> (7 - bs)) << 2
            return c, (attr & 0xE) << 2, prio, t0
        if mode == BITMAP:
            ch = ram[(nbase + (x1 >> 3) + y1row) & 0x3FFF]
            bs = x1 & 7; bit = 0x80 >> bs
            off = (y & 0xC0) << 5
            pb = ram[(pt + (((ch << 3) + off) & ptmask) + (y1 & 7)) & 0x3FFF]
            cb = ram[(ctab + (((ch << 3) + off) & ctmask) + (y1 & 7)) & 0x3FFF]
            col = (cb & 0xF0) >> 4 if pb & bit else cb & 0xF
            return col, tpalsel, False, True
        if textlike:
            if not (border <= x < drawW - border):
                return None
            naddr += x1 // 6 + y1row
            ch = ram[naddr & 0x3FFF]; bs = x1 % 6; ly = y1 & 7
            attr = 0; prio = False; t0 = True
            if ecm:
                attr = ram[(ctab + (naddr - ncanon if posattr else ch)) & 0x3FFF]
                prio = bool(attr & 0x80)
                if attr & 0x40: bs = 5 - bs
                if attr & 0x20: ly = 7 - ly
                t0 = bool(attr & 0x10)
            bit = 0x80 >> bs
            pa = (pt + (ch << 3) + ly) & 0x3FFF
            pb = ram[pa]
            if ecm == 0:
                if unl and posattr:
                    ab = ram[(ctab + naddr - ncanon) & 0x3FFF]
                    col = ab >> 4 if pb & bit else ab & 0xF
                else:
                    col = fg if pb & bit else bg
                return col, tpalsel, False, True
            c = (pb & bit) >> (7 - bs)
            if ecm == 1:
                return c, (tpalsel & 0x20) | ((attr & 0xF) << 1), prio, t0
            c |= ((ram[(pa + tplane) & 0x3FFF] & bit) >> (7 - bs)) << 1
            if ecm == 2:
                return c, (attr & 0xF) << 2, prio, t0
            c |= ((ram[(pa + 2 * tplane) & 0x3FFF] & bit) >> (7 - bs)) << 2
            return c, (attr & 0xE) << 2, prio, t0
        ch = ram[(nbase + (x1 >> 3) + y1row) & 0x3FFF]          # multicolor
        cb = ram[(pt + (ch << 3) + ((y1 & 0x1C) >> 2)) & 0x3FFF]
        return ((cb & 0xF0) >> 4 if (x1 & 4) == 0 else cb & 0xF), tpalsel, False, True

    rowsz = {GRAPHICS: 32, BITMAP: 32, MULTI: 32, TEXT: 40, TEXT80: 80}[mode]
    ncanon1 = nt & 0x3000 if vp1 else (nt & 0x3800 if hp1 else nt)
    ncanon2 = nt2 & 0x3000 if vp2 else (nt2 & 0x3800 if hp2 else nt2)
    for y in range(drawH):
        sbuf = [0] * drawW; spbuf = [0] * drawW
        if unl or not textlike:
            on = 0; idx = 0
            outy = 0xF0 if row30 else 0xC0; negy = 0xF0 if row30 else 0xD0
            a = sat; amax = sat + (maxspr << 2)
            while (row30 or ram[a] != 0xD0) and a < amax and on <= maxscan:
                par = None
                if linking:
                    la = ram[sat + 0x80 + ((a - sat) >> 2)]
                    if la & 0x20: par = sat + ((la & 0x1F) << 2)
                sy = ram[a]
                if par is not None: sy = (sy + ram[par]) & 0xFF
                if not realy: sy += 1
                if sy < outy or sy > negy:
                    if sy > negy: sy -= 256
                    sa = ram[a + 3]
                    ssize = 1 if (unl and (sa & 0x10)) else sprsize
                    h = 8 << ssize; dimy = h << sprmag
                    if sy <= y < sy + dimy:
                        if on < maxscan:
                            sx = ram[a + 1]
                            if par is None:
                                if sa & 0x80: sx -= 32
                            else:
                                sx = (sx + ram[par + 1]) & 0xFF
                                if ram[par + 3] & 0x80: sx -= 32
                            pn = ram[a + 2] & (0xFC if ssize else 0xFF)
                            fy = unl and bool(sa & 0x20); fx = unl and bool(sa & 0x40)
                            base = sa & 0xF
                            if sprecm == 0: pbase = spal
                            elif sprecm == 1: pbase = (spal & 0x20) | (base << 1)
                            elif sprecm == 2: pbase = base << 2
                            else: pbase = (base & 0xE) << 2
                            pbaseaddr = spt + (pn << 3)
                            dy = (y - sy) >> sprmag
                            if fy: dy = h - dy - 1
                            for dx in range(0, h, 8):
                                paddr = pbaseaddr + dy + (dx << 1)
                                b0 = ram[paddr & 0x3FFF]; b1 = ram[(paddr + splane) & 0x3FFF]; b2 = ram[(paddr + 2 * splane) & 0x3FFF]
                                for sh in range(8):
                                    bit = 0x80 >> sh; s2 = 7 - sh
                                    pon = False
                                    if sprecm == 0:
                                        pon = bool(b0 & bit); sc = base if pon else 0
                                    elif sprecm == 1: sc = (b0 & bit) >> s2
                                    elif sprecm == 2: sc = ((b0 & bit) >> s2) | (((b1 & bit) >> s2) << 1)
                                    else: sc = ((b0 & bit) >> s2) | (((b1 & bit) >> s2) << 1) | (((b2 & bit) >> s2) << 2)
                                    if sc > 0 or pon:
                                        x2 = sx + ((((h - (dx + sh) - 1) if fx else (dx + sh))) << sprmag)
                                        for k in range(2 if sprmag else 1):
                                            xx = x2 + k
                                            if 0 <= xx < drawW and sbuf[xx] == 0:
                                                sbuf[xx] = sc + 1; spbuf[xx] = pbase
                        on += 1
                a += 4; idx += 1
            if t80:
                for x1 in range(drawW >> 1, -1, -1):
                    if (x1 << 1) + 1 < drawW:
                        sbuf[x1 << 1] = sbuf[x1]; spbuf[x1 << 1] = spbuf[x1]
                        sbuf[(x1 << 1) + 1] = sbuf[x1]; spbuf[(x1 << 1) + 1] = spbuf[x1]
        y1 = y + vs1; nbase = nt
        if y1 >= scrollH: y1 -= scrollH; nbase ^= vp1
        row1 = (y1 >> 3) * rowsz
        y12 = y + vs2; nbase2 = nt2
        if y12 >= scrollH: y12 -= scrollH; nbase2 ^= vp2
        row2 = (y12 >> 3) * rowsz
        for x in range(drawW):
            color = bg; pbase = 0; prio = False; t0 = False
            if tl1:
                r = tile_layer(x, row1, nbase, ct, hs1, hp1, vp1, tpal, y1, ncanon1)
                if r is None:
                    color = bg
                else:
                    tc, tpb, prio, t0 = r
                    if tc > 0 or not t0:
                        color = tc; pbase = tpb
            if bmp_on:
                bx = x >> 1 if t80 else x
                if bmp_x <= bx < bmp_x + bmp_w and bmp_y <= y < bmp_y + bmp_h:
                    off = (x - bmp_x) + (y - bmp_y) * bmp_w
                    byte = ram[(bmp_base + (off >> 2)) & 0x3FFF]
                    if bmp_fat:
                        bc = (byte >> ((2 - (off & 2)) << 1)) & 0xF
                    else:
                        bc = (byte >> ((3 - (off & 3)) << 1)) & 3
                    if (bc > 0 or not bmp_trans) and (color == bg or bmp_prio):
                        color = bc; pbase = bmp_pal
            spc = None
            if (unl or not textlike) and (not prio or (t0 and color == 0)):
                s = sbuf[x] - 1
                if s > 0:
                    color = s; pbase = spbuf[x]; spc = s
            if tl2:
                r2 = tile_layer(x, row2, nbase2, ct2, hs2, hp2, vp2, tpal2, y12, ncanon2)
                if r2 is None:
                    tc2, tpb2, pr2, t02 = 0, 0, False, True
                else:
                    tc2, tpb2, pr2, t02 = r2
                if (tc2 > 0 or not t02) and (tl2top or pr2 or spc is None):
                    color = tc2; pbase = tpb2
            img[y, x] = pal[(color + pbase) & 0x3F]
    return img

def save(m, path, scale=2):
    from PIL import Image
    img = render(m)
    im = Image.fromarray(img)
    im = im.resize((im.width * scale, im.height * scale * (1 if im.width == 512 else 1)), Image.NEAREST)
    im.save(path)
    return path

if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sim9900
    cart = open(sys.argv[1], 'rb').read()
    keys = sys.argv[3] if len(sys.argv) > 3 else ''
    m, cpu, halt = sim9900.run(cart, keys=keys, frames=int(sys.argv[4]) if len(sys.argv) > 4 else 200)
    print(save(m, sys.argv[2]), MODE_NAMES[mode_of(m)])
