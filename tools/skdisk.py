#!/usr/bin/env python3
"""skdisk.py - make a TI disk image holding sources for the SAMS Kernel workbench.

    python3 tools/skdisk.py out.dsk --kernel-equ build/APP/kernel.equ FILE [FILE ...] [--volume NAME] [--geometry sssd|dssd|ssdd|dsdd] [--dir DIR]

Each FILE is stored as a DIS/VAR 80 file named after the file (upper case, at most 10 characters:
"hello.a99" is HELLO.A99).  --kernel-equ also stores KERNEL.EQU: the kernel's public symbols as
"NAME EQU >ADDR" lines, which a program's "COPY "kernel.equ"" reads on the TI.  The image is a
single-sided single-density disk (90K), the size the TI's own controller and tools/tifdc.py use.
--dir DIR also writes every file of the disk into DIR in TIFILES format, named as xdm99 names them (hello.a99.tfi):
the form a TIPI's directory or a FIAD-style directory holds.  How your TIPI wants such a file named is not something
I have checked: rename them if it needs another form.
Needs xdt99's xdm99.py (next to this directory, or XAS99's directory).
"""
import os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def xdm():
    for d in (os.path.dirname(os.environ.get('XAS99', '')), os.path.join(ROOT, 'xdt99'), os.path.join(ROOT, '..', 'xdt99')):
        p = os.path.join(d, 'xdm99.py')
        if d and os.path.exists(p):
            return p
    sys.exit('skdisk: xdm99.py not found (set XAS99 to xdt99/xas99.py)')


def equ_lines(path):
    """The kernel.equ the assembler writes ("name:" then "equ >addr") as NAME EQU >ADDR lines."""
    t = open(path).read()
    out = []
    for m in re.finditer(r'^(\S+):\s*\n\s*equ\s+(>[0-9a-fA-F]+)', t, re.M):
        out.append('%-8s EQU  %s' % (m.group(1).upper(), m.group(2).upper()))
    pg = re.search(r'^PGFREE\s+EQU\s+>([0-9A-F]+)', '\n'.join(out), re.M)
    if pg and any(l.startswith('PG_ASM') for l in out):     # the workbench's own: where a program is run
        out.append('%-8s EQU  >%X' % ('PGUSER', int(pg.group(1), 16) + 2))
    return '\n'.join(out) + '\n'


def make_disk(out, files, kernel_equ=None, volume='SKDISK', geometry='sssd'):
    x = xdm()
    if os.path.exists(out):
        os.remove(out)
    r = subprocess.run([sys.executable, x, '-X', geometry, out, '-n', volume], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr + r.stdout)
    tmp = tempfile.mkdtemp()
    adds = []
    if kernel_equ:
        p = os.path.join(tmp, 'KERNEL.EQU')
        open(p, 'w').write(equ_lines(kernel_equ))
        adds.append((p, 'KERNEL.EQU'))
    for f in files:
        name = os.path.basename(f).upper()
        if len(name) > 10:
            sys.exit('skdisk: %s: a TI file name has at most 10 characters' % name)
        adds.append((f, name))
    for path, name in adds:
        for n, line in enumerate(open(path, encoding='latin-1'), 1):
            if len(line.rstrip('\r\n')) > 80:
                sys.exit('skdisk: %s line %d is over 80 columns (tools/lint80.py)' % (path, n))
        r = subprocess.run([sys.executable, x, out, '-a', path, '-n', name, '-f', 'DIS/VAR80'], capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stderr + r.stdout)
    return out


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0].startswith('-'):
        print(__doc__); sys.exit(1)
    out = a[0]
    equ = a[a.index('--kernel-equ') + 1] if '--kernel-equ' in a else None
    vol = a[a.index('--volume') + 1] if '--volume' in a else 'SKDISK'
    geo = a[a.index('--geometry') + 1] if '--geometry' in a else 'sssd'
    skip = set()
    for flag in ('--kernel-equ', '--volume', '--dir', '--geometry'):
        if flag in a:
            skip.update({a.index(flag), a.index(flag) + 1})
    files = [f for i, f in enumerate(a[1:], 1) if i not in skip]
    make_disk(out, files, equ, vol, geo)
    print('wrote', out)
    if '--dir' in a:
        d = a[a.index('--dir') + 1]
        os.makedirs(d, exist_ok=True)
        names = [l.split()[0] for l in subprocess.run([sys.executable, xdm(), out], capture_output=True, text=True).stdout.split('\n')[2:] if l.strip()]
        for n in names:
            r = subprocess.run([sys.executable, xdm(), out, '-e', n, '-t', '-o', os.path.join(d, n.lower().replace('/', '.') + '.tfi')], capture_output=True, text=True)
            if r.returncode:
                sys.exit(r.stderr + r.stdout)
        print('wrote %d TIFILES files to %s' % (len(names), d))


if __name__ == '__main__':
    main()
