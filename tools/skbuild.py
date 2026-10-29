#!/usr/bin/env python3
"""skbuild.py - build a SAMS Kernel application into a cartridge image.

    python3 tools/skbuild.py APPDIR [--out DIR]

APPDIR holds app.json and the application's sources.  The result is
OUT/APPNAME8.bin (default OUT: build/APPDIR-name): a FinalGROM 99 "8"
image of 8K banks, bank n selected by a write to >6000 + 2n, which is also
what js99er and Classic99 load.

app.json:
  {
    "name":      "HELLO",              menu and refusal-screen name (<= 20 chars)
    "min_pages": 128,                  SAMS pages required: 32, 64, 128 or 256
    "modules": [                       each an 8K bank of code run in slot C
      {"name": "hello", "source": "hello.a99"},
      {"name": "more",  "source": "more.a99", "page": "0x20"}   (optional page)
    ],
    "boot":      "hello",              the module that starts (default: the first)
    "data": [                          optional: files copied into SAMS pages
      {"file": "words.bin", "page": "0x40"},     (> 8K: consecutive page pairs)
      {"file": "tune.skm", "from": "tune.mml", "loop": true}      music, compiled from a MIDI file or
    ]                                            a text score by tools/skmusic.py (then MUPLAY PD_TUNE)
  }

What the build does, in order: generates gen/font.a99 and gen/keytab.a99;
writes build/.../appcfg.a99 (the application's numbers), appname.a99 and
appmsg.a99 (the loader's refusal screens and bank table); assembles the
kernel, which exports its symbols to kernel.equ; assembles the loader, the
data bank and each module (which COPY "kernel.equ"); checks every bank
fits in 8K; packs the image.

Include path: the kernel and the loader see only the build directory, kernel/ and gen/ (an
application's file of the same name as one of the kernel's cannot shadow it); the data bank and
every module see the application's directory first, so an application may replace databank.a99
(the font and colour schemes) with its own.

The assembler is xdt99's xas99.py: set XAS99, or put xdt99 beside this
directory (./xdt99 or ../xdt99).
"""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = 0x2000
PGDATA, PGMOD0 = 0x10, 0x12
LOW_FREE = range(0x04, 0x0A)          # pages the CPU never maps: free for the application


def die(msg):
    sys.exit('skbuild: ' + msg)


def find_xas():
    for p in (os.environ.get('XAS99'), os.path.join(ROOT, 'xdt99', 'xas99.py'),
              os.path.join(ROOT, '..', 'xdt99', 'xas99.py')):
        if p and os.path.exists(p):
            return p
    die('xas99.py not found: set XAS99 or put xdt99 beside this directory')


XAS = find_xas()


def run(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    if r.returncode:
        sys.exit('skbuild: failed: ' + ' '.join(cmd))


def asm(src, out, incs, lst=None, equ=None):
    cmd = [sys.executable, XAS, '-R', '-b', '-q']
    if equ:
        cmd += ['-E', equ]
    cmd += ['-I'] + incs
    if lst:
        cmd += ['-L', lst]
    cmd += ['-o', out, src]
    run(*cmd)
    return open(out, 'rb').read()


def num(v):
    return int(v, 0) if isinstance(v, str) else int(v)


def ident(name):
    return re.sub(r'[^A-Z0-9]', '_', name.upper())


def load_app(appdir):
    path = os.path.join(appdir, 'app.json')
    if not os.path.exists(path):
        die('no app.json in ' + appdir)
    app = json.load(open(path))
    name = app.get('name', '').upper()
    if not name or len(name) > 20:
        die('"name" is required, 20 characters at most')
    app['name'] = name
    app.setdefault('min_pages', 128)
    if app['min_pages'] not in (32, 64, 128, 256):
        die('"min_pages" must be 32, 64, 128 or 256')
    if not app.get('modules'):
        die('"modules" needs at least one module')
    names = [m['name'] for m in app['modules']]
    if len(set(ident(n) for n in names)) != len(names):
        die('module names must be distinct')
    app.setdefault('boot', names[0])
    if app['boot'] not in names:
        die('"boot" names no module')
    app.setdefault('data', [])
    return app


def prepare_data(app, bdir):
    """Data entries with "from" are music: tools/skmusic.py compiles the MIDI file or text score
    (relative to the application) into the build directory; "loop": true, "loop_at": seconds and
    "fps" are passed on.  Every entry gets "_path", the file whose bytes go into SAMS."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    for d in app['data']:
        if 'from' in d:
            import skmusic
            src = os.path.join(app['_dir'], d['from'])
            skm, info = skmusic.compile_file(src, d.get('fps', 60), bool(d.get('loop')), d.get('loop_at'),
                                             d.get('volume', 0), d.get('transpose', 0))
            d['_path'] = os.path.join(bdir, d['file'])
            open(d['_path'], 'wb').write(skm)
            print('music %s: %d bytes, %.1f s' % (d['file'], info['bytes'], info['seconds']))
        else:
            d['_path'] = os.path.join(app['_dir'], d['file'])


def assign_pages(app):
    """Give every module and data file its pages; return (items, pgfree)."""
    used = {}                             # page -> owner
    def take(first, count, owner):
        for p in range(first, first + count):
            if p in used:
                die('page >%02X is wanted by both %s and %s' % (p, used[p], owner))
            if not (p in LOW_FREE or p >= PGMOD0):
                die('%s: page >%02X is the kernel\'s (use >04->09 or >12 and up)' % (owner, p))
            if p >= app['min_pages']:
                die('%s: page >%02X is beyond min_pages (%d)' % (owner, p, app['min_pages']))
            used[p] = owner
    items = []
    for m in app['modules']:
        if 'page' in m:
            first = num(m['page'])
            take(first, 2, m['name'])
            m['_page'] = first
    nxt = PGMOD0
    def next_free(count):
        nonlocal nxt
        while any(p in used for p in range(nxt, nxt + count)):
            nxt += 1
        first = nxt
        nxt += count
        return first
    for m in app['modules']:
        if '_page' not in m:
            m['_page'] = next_free(2)
            take(m['_page'], 2, m['name'])
    for d in app['data']:
        size = os.path.getsize(d['_path'])
        chunks = max(1, (size + BANK - 1) // BANK)
        if 'page' in d:
            first = num(d['page'])
            take(first, 2 * chunks, d['file'])
        else:
            first = next_free(2 * chunks)
            take(first, 2 * chunks, d['file'])
        d['_page'], d['_chunks'] = first, chunks
    pgfree = max([p + 1 for p in used] + [PGMOD0])
    return pgfree


def write_cfg(app, bdir, banks, pgfree):
    L = ['* appcfg.a99 - made by tools/skbuild.py from app.json; do not edit',
         'PGMIN  EQU  %d' % app['min_pages']]
    for m in app['modules']:
        L.append('%-6s EQU  >%02X' % ('PG_' + ident(m['name']), m['_page']))
    L.append('PGBOOT EQU  PG_' + ident(app['boot']))
    L.append('PGFREE EQU  >%02X' % pgfree + '            first SAMS page the build leaves unassigned')
    for d in app['data']:
        L.append('%-6s EQU  >%02X' % ('PD_' + ident(os.path.splitext(d['file'])[0]), d['_page']))
    open(os.path.join(bdir, 'appcfg.a99'), 'w').write('\n'.join(L) + '\n')
    open(os.path.join(bdir, 'appname.a99'), 'w').write(
        '* made by tools/skbuild.py\n       BYTE %d\n       TEXT \'%s\'\n' % (len(app['name']), app['name']))
    kb = app['min_pages'] * 4
    size = ('%dK' % kb)
    msg = ['* appmsg.a99 - made by tools/skbuild.py: the refusal screens and the bank table',
           'MSGSAM BYTE 8', '       STRI \'%s\'' % app['name'],
           '       BYTE 11', '       STRI \'NEEDS A SAMS MEMORY CARD WITH %s\'' % size,
           '       BYTE 12', "       STRI 'OF MEMORY OR MORE TO RUN.'",
           '       BYTE 16', "       STRI 'PRESS FCTN = TO RETURN TO THE TITLE'", '       BYTE >FF',
           'MSGF18 BYTE 8', '       STRI \'%s\'' % app['name'],
           '       BYTE 11', "       STRI 'NEEDS AN F18A VIDEO CARD FOR ITS'",
           '       BYTE 12', "       STRI '80-COLUMN SCREEN AND COLOR.'",
           '       BYTE 16', "       STRI 'PRESS FCTN = TO RETURN TO THE TITLE'", '       BYTE >FF',
           'MSGBAD BYTE 8', '       STRI \'%s\'' % app['name'],
           '       BYTE 11', "       STRI 'THE MEMORY CARD FAILED ITS TEST AT'",
           '       BYTE 12', "       STRI 'PAGE'", '       BYTE 13', "       STRI '>?'",
           '       BYTE 16', "       STRI 'PRESS FCTN = TO RETURN TO THE TITLE'", '       BYTE >FF',
           '       EVEN', '* BANKTB: (bank, first page) for every bank after the kernel; 0 ends it',
           'BANKTB']
    for bank, page in banks:
        msg.append('       DATA %d,>%02X' % (bank, page))
    msg.append('       DATA 0')
    open(os.path.join(bdir, 'appmsg.a99'), 'w').write('\n'.join(msg) + '\n')


def export_public(ksrc, bdir, equ):
    """Rewrite kernel.equ so that it exports only what an application may use: the
    equates (kdefs.a99 and the generated appcfg.a99) and the routines in
    kernel/public.txt.  Every other kernel label stays private, so the kernel can
    add routines without colliding with the labels of an application's modules."""
    keep = set()
    for f in (os.path.join(ksrc, 'kdefs.a99'), os.path.join(bdir, 'appcfg.a99')):
        for line in open(f, encoding='latin-1'):
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s+EQU\b', line, re.I)
            if m: keep.add(m.group(1).lower())
    for line in open(os.path.join(ksrc, 'public.txt')):
        if not line.startswith('#'):
            keep.update(n.lower() for n in line.split())
    lines = open(equ).read().split('\n')
    out, i, total = [], 0, 0
    while i + 1 < len(lines):
        if lines[i].endswith(':') and 'equ' in lines[i + 1]:
            total += 1
            if lines[i][:-1].lower() in keep:
                out += [lines[i], lines[i + 1]]
            i += 2
        else:
            i += 1
    open(equ, 'w').write('\n'.join(out) + '\n')
    return total, len(out) // 2


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith('-'):
        print(__doc__)
        sys.exit(1)
    appdir = os.path.abspath(args[0])
    app = load_app(appdir)
    app['_dir'] = appdir
    outdir = args[args.index('--out') + 1] if '--out' in args else \
        os.path.join(ROOT, 'build', os.path.basename(appdir.rstrip('/')))
    bdir = os.path.abspath(outdir)
    os.makedirs(bdir, exist_ok=True)
    os.makedirs(os.path.join(ROOT, 'gen'), exist_ok=True)
    run(sys.executable, os.path.join(ROOT, 'tools', 'font.py'))
    run(sys.executable, os.path.join(ROOT, 'tools', 'keytab.py'))
    prepare_data(app, bdir)
    pgfree = assign_pages(app)
    # banks: 0 loader, 1 kernel, 2 data bank, then modules, then data files
    banks = [(2, PGDATA)]
    nb = 3
    for m in app['modules']:
        m['_bank'] = nb
        banks.append((nb, m['_page']))
        nb += 1
    for d in app['data']:
        d['_bank'] = nb
        for c in range(d['_chunks']):
            banks.append((nb, d['_page'] + 2 * c))
            nb += 1
    write_cfg(app, bdir, banks, pgfree)
    incs = [appdir, bdir, os.path.join(ROOT, 'kernel'), os.path.join(ROOT, 'gen')]
    kincs = [bdir, os.path.join(ROOT, 'kernel'), os.path.join(ROOT, 'gen')]    # the kernel never sees the application's files
    ksrc = os.path.join(ROOT, 'kernel')
    equ = os.path.join(bdir, 'kernel.equ')
    kernel = asm(os.path.join(ksrc, 'kernel.a99'), os.path.join(bdir, 'kernel.bin'), kincs,
                 os.path.join(bdir, 'kernel.lst'), equ)
    export_public(ksrc, bdir, equ)
    loader = asm(os.path.join(ksrc, 'loader.a99'), os.path.join(bdir, 'loader.bin'), kincs,
                 os.path.join(bdir, 'loader.lst'))
    ds = os.path.join(appdir, 'databank.a99')
    ds = ds if os.path.exists(ds) else os.path.join(ksrc, 'databank.a99')
    data = asm(ds, os.path.join(bdir, 'databank.bin'), incs, os.path.join(bdir, 'databank.lst'))
    images = [loader, kernel, data]
    sizes = [('loader', len(loader)), ('kernel', len(kernel)), ('data bank', len(data))]
    for m in app['modules']:
        src = os.path.join(appdir, m['source'])
        out = os.path.join(bdir, m['name'] + '.bin')
        b = asm(src, out, incs, os.path.join(bdir, m['name'] + '.lst'), os.path.join(bdir, m['name'] + '.equ'))   # (the module's symbols: for tests and debugging)
        images.append(b)
        sizes.append((m['name'], len(b)))
    for d in app['data']:
        raw = open(d['_path'], 'rb').read()
        for c in range(d['_chunks']):
            images.append(raw[c * BANK:(c + 1) * BANK])
        sizes.append((d['file'], len(raw)))
    for n, sz in sizes:
        if sz > BANK:
            die('%s is %d bytes: over its 8K bank' % (n, sz))
    if len(kernel) > BANK:
        die('the kernel is over 8K')
    n = 1
    while n < len(images):
        n *= 2
    n = max(n, 4)
    image = b''.join(b.ljust(BANK, b'\0') for b in images).ljust(n * BANK, b'\0')
    out = os.path.join(bdir, app['name'].lower().replace(' ', '') + '8.bin')
    open(out, 'wb').write(image)
    print('kernel %d bytes (ends >%04X, %d free)' % (len(kernel), 0xA000 + len(kernel), BANK - len(kernel)))
    for (nme, sz) in sizes[3:]:
        print('  %-16s %5d bytes' % (nme, sz))
    print('wrote %s: %dK, %d banks, SAMS pages needed: %d (pool from >%02X)' %
          (out, len(image) // 1024, n, app['min_pages'], pgfree))


if __name__ == '__main__':
    main()
