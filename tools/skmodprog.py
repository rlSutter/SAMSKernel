#!/usr/bin/env python3
"""skmodprog.py - a MODULE PROGRAM: a kernel module on a disk, run by a cartridge that already holds the kernel (docs/MODPROG.md).

    python3 tools/skmodprog.py guest.a99 --target build/workbench -o GUEST [--title "MY GUEST"] [--disk guest.dsk [--geometry sssd|dsdd] [--volume NAME]]

The program is one module (<= the cartridge's MODMAX: 8,192 bytes, or 4,096 if the cartridge has common code) assembled against the TARGET's kernel.equ (a directory with it, or the file),
with the module's own header at >C000 as in any module (INIT, TICK, REDRAW, flags).  The target must have been built with "modprog": true.  The result is one PROGRAM file (an Editor/Assembler
option 5 image for >2000), 134 bytes plus the module:

    the 6-byte option 5 header: flag 0 (one file), the length, the load address >2000
    a stub of 96 bytes (kernel/modstub.a99): what the Editor/Assembler's own option 5 runs: it says the program needs the cartridge and returns
    a 32-byte header: 'SKMP', version 1, the target's kernel build ID (a CRC-32 of its kernel.equ, two words), the module's length, a flags word (0), the title (a length byte and 15 characters)
    the module

The cartridge's RUN PROGRAM FILE sees the signature, compares the build ID with its own (a program for another build is refused with both IDs on the screen), puts the module over its
boot module's pages, and the kernel starts it as the application.  Everything the cartridge's kernel offers is there (its routines, data pages and modules by their kernel.equ names)."""
import os
import re
import subprocess
import sys
import tempfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
STUB = 96
HDR = 32


def die(msg):
    sys.exit('skmodprog: ' + msg)


def xas():
    p = os.environ.get('XAS99') or os.path.join(os.path.dirname(ROOT), 'xdt99', 'xas99.py')
    if not os.path.exists(p):
        die('xas99.py not found: set XAS99 (see the README)')
    return p


def assemble(src, incs, out):
    r = subprocess.run([sys.executable, xas(), '-R', '-b', '-q', '-I'] + incs + ['-o', out, src], capture_output=True, text=True)
    if r.returncode:
        die('assembling %s failed:\n%s' % (src, r.stdout + r.stderr))
    return open(out, 'rb').read()


def read_equ(path):
    """(the file's bytes, {name: value}) for a kernel.equ (the assembler's "name:" and "equ value" lines)"""
    raw = open(path, 'rb').read()
    vals = {}
    for m in re.finditer(r'(\w+):\s*\n\s+equ\s+(>?[0-9A-Fa-f]+)', raw.decode('latin-1')):
        v = m.group(2)
        vals[m.group(1).lower()] = int(v[1:], 16) if v.startswith('>') else int(v)
    return raw, vals


def build(source, target, title=None):
    """(None, the kernel build ID, the file's data: stub, header and module)"""
    equ = target if os.path.isfile(target) else os.path.join(target, 'kernel.equ')
    if not os.path.exists(equ):
        die('no kernel.equ at %s: build the cartridge first (skbuild.py), with "modprog": true' % target)
    raw, vals = read_equ(equ)
    if 'modmax' not in vals:
        die('%s has no MODMAX: that cartridge was not built with "modprog": true' % equ)
    crc = zlib.crc32(raw) & 0xFFFFFFFF
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, 'kernel.equ'), 'wb').write(raw)
    mod = assemble(source, [tmp, os.path.join(ROOT, 'kernel'), os.path.join(ROOT, 'lib'), os.path.join(ROOT, 'gen'), os.path.dirname(os.path.abspath(source))],
                   os.path.join(tmp, 'module.bin'))
    if len(mod) < 8:
        die('the module is too short to have its four-word header')
    if len(mod) > vals['modmax']:
        die('the module is %d bytes: this cartridge takes %d at most' % (len(mod), vals['modmax']))
    if vals.get('commonpg') and len(mod) <= 4096:           # the cartridge has code at >D000: the module owns only its own page
        mod = mod[:6] + (int.from_bytes(mod[6:8], 'big') | 1).to_bytes(2, 'big') + mod[8:]
    stub = assemble(os.path.join(ROOT, 'kernel', 'modstub.a99'), [os.path.join(ROOT, 'kernel')], os.path.join(tmp, 'stub.bin'))
    if len(stub) > STUB:
        die('the stub grew past %d bytes' % STUB)
    stub = stub + bytes(STUB - len(stub))
    t = (title or os.path.splitext(os.path.basename(source))[0]).upper()[:15]
    head = b'SK' + b'MP' + (1).to_bytes(2, 'big') + crc.to_bytes(4, 'big') + len(mod).to_bytes(2, 'big') + (0).to_bytes(2, 'big')
    head += bytes([len(t)]) + t.encode('ascii') + bytes(HDR - len(head) - 1 - len(t))
    data = stub + head + mod
    return None, crc, data


def program_file(source, target, title=None):
    """(the file's bytes, the build ID)"""
    _, crc, data = build(source, target, title)
    return (0).to_bytes(2, 'big') + len(data).to_bytes(2, 'big') + (0x2000).to_bytes(2, 'big') + data, crc


def main(argv):
    out = disk = title = None
    geometry, volume = 'sssd', 'MODPROG'
    args = []
    k = 0
    while k < len(argv):
        a = argv[k]
        if a in ('-o', '--target', '--title', '--disk', '--geometry', '--volume'):
            if k + 1 >= len(argv):
                die('%s needs a value' % a)
            v = argv[k + 1]
            if a == '-o': out = v
            elif a == '--target': target = v
            elif a == '--title': title = v
            elif a == '--disk': disk = v
            elif a == '--geometry': geometry = v
            else: volume = v
            k += 2
        else:
            args.append(a)
            k += 1
    if len(args) != 1 or 'target' not in locals() or not (out or disk):
        sys.exit(__doc__.split('The program is one module')[0])
    data, crc = program_file(args[0], target, title)
    name = (os.path.basename(out) if out else os.path.splitext(os.path.basename(args[0]))[0]).upper()
    if out:
        open(out, 'wb').write(data)
    print('%s: module program for kernel build %08X, %d bytes in the file (module %d)' % (name, crc, len(data), len(data) - 6 - STUB - HDR))
    if disk:
        import skdisk
        n = (os.path.splitext(os.path.basename(out))[0] if out else os.path.splitext(os.path.basename(args[0]))[0]).upper()[:10]
        skdisk.make_disk(disk, [], None, volume, geometry, programs=[(n, data)])
        print('wrote %s with the program %s' % (disk, n))


if __name__ == '__main__':
    main(sys.argv[1:])
