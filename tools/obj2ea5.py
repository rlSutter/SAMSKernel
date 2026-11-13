#!/usr/bin/env python3
"""obj2ea5.py - link Editor/Assembler object files into an option 5 image that RUN PROGRAM FILE can start.

    python3 tools/obj2ea5.py prog.obj [more.obj ...] -o build/PROG          raw image files PROG, PROH, ...
    python3 tools/obj2ea5.py prog.obj --disk build/prog.dsk --name PROG     a disk with the PROGRAM files
    python3 tools/obj2ea5.py --from-disk old.dsk PROG1 PROG2 --disk out.dsk --name PROG

Object files are what the TI Assembler and xas99 write (DIS/FIX 80, the tagged object format of the Editor/Assembler
manual), uncompressed or compressed (option C), on the PC or read off a TI disk image (--from-disk).  The modules are
loaded in order: absolute code where it says (tag 9), relocatable code from --base (default >A000, where the E/A
loader puts it) one module after another; REFs are resolved against the modules' DEFs and against the Editor/Assembler's
fixed names (VDPWA, VDPWD, SOUND, GPLWS, FAC ... the console's own addresses); the entry is the END label (tag 1 or 2).
An option 5 image starts where its first file loads: if the entry is not the program's lowest address, the first file is
a four-byte stub, B @entry (why it is not simply the file holding the entry: see image_files).

The Editor/Assembler's UTILITIES (VSBW, VMBW, VSBR, VMBR, VWTR, KSCAN, GPLLNK, XMLLNK, DSRLNK, LOADER) are code the
E/A cartridge copies into low memory; RUN PROGRAM FILE does not provide them, so a program that REFs them is refused
with their names.  --allow-ea-utilities resolves them to E/A's addresses anyway (for a machine where they will be there).

Checksums (tag 7) are checked; --no-checksum skips that.  Exit status 1 with a message on any error.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# the console's and the Editor/Assembler's fixed names: addresses that are there without E/A's utilities
FIXED = {
    'VDPRD': 0x8800, 'VDPSTA': 0x8802, 'VDPWD': 0x8C00, 'VDPWA': 0x8C02, 'SOUND': 0x8400,
    'SPCHRD': 0x9000, 'SPCHWT': 0x9400, 'GRMRD': 0x9800, 'GRMRA': 0x9802, 'GRMWD': 0x9C00, 'GRMWA': 0x9C02,
    'PAD': 0x8300, 'GPLWS': 0x83E0, 'FAC': 0x834A, 'ARG': 0x835C, 'STATUS': 0x837C,
}
# the E/A utilities: vectors E/A puts in low memory (refused unless --allow-ea-utilities)
EAUTIL = {
    'GPLLNK': 0x2100, 'XMLLNK': 0x2104, 'KSCAN': 0x2108, 'VSBW': 0x210C, 'VMBW': 0x2110, 'VSBR': 0x2114,
    'VMBR': 0x2118, 'VWTR': 0x211C, 'DSRLNK': 0x2120, 'LOADER': 0x2124, 'UTLTAB': 0x2022,
}
FILEMAX = 8192 - 6          # data bytes in one image file (header 6)
GAPFILL = 256               # gaps up to this many bytes between pieces are filled with zeros, not split


class LinkError(Exception):
    pass


def records(data):
    """the 80-byte records of an object file: lines of text, or fixed 80-byte records (as xas99 and a TI disk have them)"""
    if data[:1] == b'\x01':                                    # compressed: binary, always fixed records
        return [data[i:i + 80] for i in range(0, len(data), 80)]
    if b'\n' in data:
        return [ln.rstrip(b'\r') for ln in data.split(b'\n') if ln.strip()]
    return [data[i:i + 80] for i in range(0, len(data), 80)]


class Module:
    def __init__(self, src):
        self.src = src
        self.name = ''
        self.length = 0
        self.ops = []           # (op, args) in order: ('org_abs', a), ('org_rel', a), ('abs', w), ('rel', w),
        #                         ('entry', a, rel), ('def', name, a, rel), ('ref', name, a, rel)


def parse(data, src, check=True):
    """the modules of one object file"""
    mods, mod = [], None
    for n, rec in enumerate(records(data)):
        comp = rec[:1] == b'\x01' or (mod is not None and getattr(mod, 'compressed', False))
        p = 0
        def word():
            nonlocal p
            if comp:
                if p + 2 > len(rec):
                    raise LinkError('%s: record %d is cut short' % (src, n + 1))
                v = (rec[p] << 8) | rec[p + 1]
                p += 2
                return v
            s = rec[p:p + 4].decode('ascii', 'replace')
            p += 4
            try:
                return int(s, 16)
            except ValueError:
                raise LinkError('%s: record %d: %r is not a hex word' % (src, n + 1, s))
        def text(k):
            nonlocal p
            s = rec[p:p + k].decode('ascii', 'replace')
            p += k
            return s.rstrip()
        while p < len(rec):
            tag = rec[p:p + 1]
            p += 1
            if tag == b'\x01' or tag == b'0':
                mod = Module(src)
                mod.compressed = (tag == b'\x01')
                comp = mod.compressed
                mods.append(mod)
                mod.length = word()
                mod.name = text(8)
                continue
            if mod is None:
                raise LinkError('%s: the first record does not start with a program identifier (tag 0)' % src)
            if tag == b'1':
                mod.ops.append(('entry', word(), False))
            elif tag == b'2':
                mod.ops.append(('entry', word(), True))
            elif tag in (b'3', b'4'):
                a = word()
                mod.ops.append(('ref', text(6), a, tag == b'3'))
            elif tag in (b'5', b'6'):
                a = word()
                mod.ops.append(('def', text(6), a, tag == b'5'))
            elif tag == b'7':
                start = p - 1
                c = word()
                if check and c is not None:
                    total = sum(rec[:start + 1])
                    if (total + c) & 0xFFFF:
                        raise LinkError('%s: record %d: the checksum is wrong (the file is damaged; --no-checksum to load it anyway)' % (src, n + 1))
            elif tag == b'8':
                word()
            elif tag == b'9':
                mod.ops.append(('org_abs', word()))
            elif tag == b'A':
                mod.ops.append(('org_rel', word()))
            elif tag == b'B':
                mod.ops.append(('abs', word()))
            elif tag == b'C':
                mod.ops.append(('rel', word()))
            elif tag == b'F':
                break                                         # the rest of the record is padding and its number
            elif tag == b':':
                return mods                                   # the end of the file
            elif tag in (b' ', b''):
                continue
            else:
                raise LinkError('%s: record %d: tag %r is not one this linker knows' % (src, n + 1, tag.decode('latin-1')))
    return mods


def link(modules, base=0xA000, allow_util=False):
    """-> (memory {addr: byte}, entry, symbols) ; raises LinkError"""
    mem, defs, refs, entry = {}, {}, [], None
    bases = []
    b = base
    for m in modules:
        bases.append(b)
        b += (m.length + 1) & ~1
    for m, mb in zip(modules, bases):
        lc = mb
        for op in m.ops:
            k = op[0]
            if k == 'org_abs':
                lc = op[1]
            elif k == 'org_rel':
                lc = mb + op[1]
            elif k in ('abs', 'rel'):
                v = (op[1] + (mb if k == 'rel' else 0)) & 0xFFFF
                if lc & 1:
                    raise LinkError('%s: a word at the odd address >%04X' % (m.src, lc))
                mem[lc] = v >> 8
                mem[lc + 1] = v & 0xFF
                lc += 2
            elif k == 'entry':
                if entry is None:
                    entry = (op[1] + (mb if op[2] else 0)) & 0xFFFF
            elif k == 'def':
                name, a, rel = op[1], op[2], op[3]
                if name in defs:
                    raise LinkError('%s is defined twice (%s and %s)' % (name, defs[name][1], m.src))
                defs[name] = ((a + (mb if rel else 0)) & 0xFFFF, m.src)
            elif k == 'ref':
                refs.append((op[1], op[2], op[3], mb, m.src))
    missing, used_util = [], set()
    for name, head, rel, mb, src in refs:
        if name in defs:
            val = defs[name][0]
        elif name in FIXED:
            val = FIXED[name]
        elif name in EAUTIL and allow_util:
            val = EAUTIL[name]
            used_util.add(name)
        else:
            missing.append((name, src))
            continue
        a = (head + (mb if rel else 0)) & 0xFFFF if head else 0
        guard = 0
        while a:
            if a not in mem or a + 1 not in mem:
                raise LinkError('%s: the reference chain of %s goes to >%04X, where nothing was loaded' % (src, name, a))
            nxt = (mem[a] << 8) | mem[a + 1]
            mem[a], mem[a + 1] = val >> 8, val & 0xFF
            a = (nxt + (mb if rel else 0)) & 0xFFFF if nxt else 0
            guard += 1
            if guard > 32768:
                raise LinkError('%s: the reference chain of %s loops' % (src, name))
    if missing:
        util = sorted({n for n, s in missing if n in EAUTIL})
        other = sorted({n for n, s in missing if n not in EAUTIL})
        msg = []
        if util:
            msg.append('it uses the Editor/Assembler\'s utilities %s, which the E/A cartridge copies into low memory and RUN PROGRAM FILE '
                       'does not provide (use E/A\'s option 3, or a version of the program with its own utilities; '
                       '--allow-ea-utilities links them to E/A\'s addresses anyway)' % ', '.join(util))
        if other:
            msg.append('nothing defines %s (a module missing from the list?)' % ', '.join(other))
        raise LinkError('; '.join(msg))
    if entry is None:
        raise LinkError('no entry point: the program\'s END has no label (give --entry)')
    symbols = {n: v for n, (v, s) in defs.items()}
    return mem, entry, symbols, sorted(used_util)


def pieces(mem):
    """contiguous (address, bytes) pieces, small gaps filled with zeros"""
    if not mem:
        return []
    addrs = sorted(mem)
    out, start, prev = [], addrs[0], addrs[0]
    for a in addrs[1:]:
        if a - prev - 1 > GAPFILL:
            out.append((start, bytes(mem.get(x, 0) for x in range(start, prev + 1))))
            start = a
        prev = a
    out.append((start, bytes(mem.get(x, 0) for x in range(start, prev + 1))))
    return out


def image_files(mem, entry):
    """the option 5 files (bytes each, header included) and the address of a start stub (or None).

    The loader copies as many bytes as a file's length word says, and that word counts the six-byte header too (xas99 writes it
    so, and the Editor/Assembler and RUN PROGRAM FILE copy that many): every file lays six bytes of whatever follows its data
    past its end.  So the files are written in rising address order, where each one's six extra bytes land on the next file's
    place before it is loaded, or past the end of the program.  An option 5 image starts where its FIRST file loads: if the
    entry is not the start of the lowest piece, the first file is a stub of four bytes, B @entry, put where no later file's
    extra bytes reach (above the program's end, past those six bytes, or below its start when that is still RAM)."""
    ps = pieces(mem)
    if not any(a <= entry < a + len(d) for a, d in ps):
        raise LinkError('the entry >%04X is not in the loaded code' % entry)
    chunks = []
    for a, d in ps:
        if len(d) & 1:
            d = d + b'\x00'
        for i in range(0, len(d), FILEMAX):
            chunks.append((a + i, d[i:i + FILEMAX]))
    stub = None
    if chunks[0][0] != entry:
        lo = chunks[0][0]
        hi = chunks[-1][0] + len(chunks[-1][1])
        ram = (0x2000 <= lo - 4 and lo - 4 < 0x4000 and lo < 0x4000) or (0xA000 <= lo - 4)
        if ram:
            stub = lo - 4
        elif hi + 6 + 4 + 6 <= 0x10000:
            stub = (hi + 6 + 1) & ~1
        else:
            raise LinkError('no room for the start stub (the program fills the memory to its end and starts at its bottom)')
        chunks.insert(0, (stub, bytes([0x04, 0x60, entry >> 8, entry & 0xFF])))
    files = []
    for k, (a, d) in enumerate(chunks):
        more = 0xFFFF if k + 1 < len(chunks) else 0
        hdr = bytes([more >> 8, more & 0xFF, (len(d) + 6) >> 8, (len(d) + 6) & 0xFF, a >> 8, a & 0xFF])
        files.append(hdr + d)
    return files, stub


def next_name(name):
    return name[:-1] + chr(ord(name[-1]) + 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description='link Editor/Assembler object files into an option 5 image')
    ap.add_argument('objects', nargs='*')
    ap.add_argument('--from-disk', metavar='DSK', help='read the objects (DIS/FIX 80 files) from this TI disk image')
    ap.add_argument('--base', default='>A000', help='where relocatable code goes (default >A000)')
    ap.add_argument('--entry', help='the entry address, if the END has no label')
    ap.add_argument('-o', '--output', help='write the image files as OUTPUT, then its name with the last character incremented')
    ap.add_argument('--disk', help='write a new single-density disk image with the PROGRAM files')
    ap.add_argument('--name', default='PROG', help='the first file\'s name on the disk (default PROG)')
    ap.add_argument('--allow-ea-utilities', action='store_true')
    ap.add_argument('--no-checksum', action='store_true')
    a = ap.parse_args(argv)
    num = lambda s: int(s.lstrip('>'), 16) if s.startswith('>') else int(s, 0)
    try:
        if not a.objects:
            raise LinkError('no object files given')
        modules = []
        if a.from_disk:
            import tifdc
            img = bytearray(open(a.from_disk, 'rb').read())
            for name in a.objects:
                recs = tifdc.read_file(img, name.upper())
                if recs is None:
                    raise LinkError('%s has no file %s' % (a.from_disk, name.upper()))
                modules += parse(b''.join(r.ljust(80, b' ')[:80] for r in recs), name.upper(), not a.no_checksum)
        else:
            for f in a.objects:
                modules += parse(open(f, 'rb').read(), f, not a.no_checksum)
        mem, entry, syms, util = link(modules, num(a.base), a.allow_ea_utilities)
        if a.entry:
            entry = num(a.entry)
        files, stub = image_files(mem, entry)
        if util:
            print('obj2ea5: warning: linked to the E/A utilities %s at E/A\'s addresses; RUN PROGRAM FILE does not provide them' % ', '.join(util))
        name = a.name.upper()
        names = []
        for f in files:
            names.append(name)
            name = next_name(name)
        if a.output:
            out = a.output
            for f in files:
                open(out, 'wb').write(f)
                out = os.path.join(os.path.dirname(out), next_name(os.path.basename(out)))
        if a.disk:
            import skdisk
            skdisk.make_disk(a.disk, [], None, 'PROGRAM', 'sssd', programs=list(zip(names, files)))
        span = sum(len(f) - 6 for f in files) - (4 if stub is not None else 0)
        print('obj2ea5: %d module%s, %d bytes in %d file%s (%s), entry >%04X%s' % (len(modules), '' if len(modules) == 1 else 's', span, len(files),
              '' if len(files) == 1 else 's', ', '.join(names), entry, '' if stub is None else ', started by B @>%04X at >%04X' % (entry, stub)))
        return 0
    except LinkError as e:
        print('obj2ea5: %s' % e)
        return 1


if __name__ == '__main__':
    sys.exit(main())
