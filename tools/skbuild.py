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
    "min_pages": 128,                  SAMS pages required: 32, 64, 128 ... 4096
    "modules": [                       each an 8K bank of code run in slot C
      {"name": "hello", "source": "hello.a99"},
      {"name": "more",  "source": "more.a99", "page": "0x20"}   (optional page)
    ],
    "boot":      "hello",              the module that starts (default: the first)
    "omit": ["music"],                  optional: parts of the kernel the program does not use and leaves out, from
                                         "music", "files", "pool", "graphics" (Graphics I, Graphics II, Multicolor)
                                         and "enhanced" (enhanced colour, sprites): the room goes to resident code
                                         (docs/RESIDENT.md)
    "pool_max_pages": 4096,             optional: the most pages the program's pool will ever manage (a multiple
                                         of 64): the bitmap is pool_max_pages/8 bytes, the rest of the 512 is room
                                         for the kernel and resident code (docs/RESIDENT.md)
    "resident": {                      optional: code every module can call (docs/RESIDENT.md)
      "source": "resident.a99",        assembled INTO THE KERNEL's pages, after the kernel
      "exports": ["RSUM", "LINEIN"]    the labels the modules may BL to (added to kernel.equ)
    },
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

Include path: the kernel and the loader see only the build directory, kernel/, gen/ and lib/ (an
application's file of the same name as one of the kernel's cannot shadow it; an application with
resident code also lets it see the application's own directory, last of all); the data bank and
every module see the application's directory first, so an application may replace databank.a99
(the font and colour schemes) with its own.

The assembler is xdt99's xas99.py: set XAS99, or put xdt99 beside this
directory (./xdt99 or ../xdt99).
"""
import json, os, re, shutil, subprocess, sys

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


# what an application may leave out of its kernel: the symbol the build defines for the assembler (-D), and the kernel file that
# is skipped (None: part of video.a99, skipped inside it) ...
OMITTABLE = {'music': ('NOMUSIC', 'music'), 'files': ('NOFILES', 'files'), 'pool': ('NOPOOL', 'pool'),
             'graphics': ('NOGRAPHICS', None), 'enhanced': ('NOENHANCED', None)}
# ... and the names (equates, for the parts inside video.a99) that a module must then not use
OMITTED_EQUATES = {'graphics': ['VMGM1', 'VMGM2', 'VMMC'],
                   'enhanced': ['VOTE1', 'VOTE2', 'VOTE3', 'VOSE1', 'VOSE2', 'VOSE3', 'VOSPR', 'VOS16', 'VOSMG']}


def asm(src, out, incs, lst=None, equ=None, defs=()):
    cmd = [sys.executable, XAS, '-R', '-b', '-q']
    if equ:
        cmd += ['-E', equ]
    cmd += ['-I'] + incs
    if lst:
        cmd += ['-L', lst]
    cmd += ['-o', out, src]
    if defs:
        cmd += ['-D'] + list(defs)          # (after the source: -D takes every word that follows it)
    run(*cmd)
    return open(out, 'rb').read()


def omitted_routines(app, ksrc):
    """{routine name: the "omit" word that removes it}: the kernel's public routines defined in the files that are left out
    (MUTICK stays: without the music code it is a bare return)."""
    pub = set(open(os.path.join(ksrc, 'public.txt')).read().split())
    out = {}
    for key in app['omit']:
        for n in OMITTED_EQUATES.get(key, []):
            out[n] = key
        if OMITTABLE[key][1] is None:
            continue
        for line in open(os.path.join(ksrc, OMITTABLE[key][1] + '.a99'), encoding='latin-1'):
            m = re.match(r'^([A-Z][A-Z0-9_]*)\b', line)
            if m and m.group(1) in pub and m.group(1) != 'MUTICK':
                out[m.group(1)] = key
    return out


def source_words(path, incs, seen=None):
    """Every name used as an operand in the source at PATH and in the files it COPYs (not the kernel's own)."""
    seen = seen if seen is not None else set()
    words = set()
    if path in seen or not os.path.exists(path):
        return words
    seen.add(path)
    for line in open(path, encoding='latin-1'):
        if line.startswith('*') or not line.strip():
            continue
        f = line.split()
        if line[0] not in ' \t':
            f = f[1:]                                   # a label
        if len(f) < 2:
            continue
        if f[0].upper() == 'COPY':
            name = f[1].strip('"\'')
            if name.lower() not in ('kernel.equ', 'macros.a99'):
                for d in incs:
                    if os.path.exists(os.path.join(d, name)):
                        words |= source_words(os.path.join(d, name), incs, seen)
                        break
            continue
        words |= set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', f[1]))
    return {w.upper() for w in words}


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
    if app['min_pages'] not in (32, 64, 128, 256, 512, 1024, 2048, 4096):
        die('"min_pages" must be 32, 64, 128, 256 ... 4096')
    if not app.get('modules'):
        die('"modules" needs at least one module')
    names = [m['name'] for m in app['modules']]
    if len(set(ident(n) for n in names)) != len(names):
        die('module names must be distinct')
    app.setdefault('boot', names[0])
    if app['boot'] not in names:
        die('"boot" names no module')
    app.setdefault('data', [])
    omit = app.setdefault('omit', [])
    if not isinstance(omit, list) or any(o not in OMITTABLE for o in omit):
        die('"omit" lists some of: %s' % ', '.join(sorted(OMITTABLE)))
    if 'pool' in omit and 'pool_max_pages' in app:
        die('"omit": ["pool"] leaves out the page pool, and "pool_max_pages" sets the size of its bitmap: use one')
    app.setdefault('pool_max_pages', 4096)
    pm = app['pool_max_pages']
    if not isinstance(pm, int) or pm % 64 or not 64 <= pm <= 4096:
        die('"pool_max_pages" must be a multiple of 64 from 64 to 4096 (the pool\'s bitmap has a bit for each page)')
    res = app.get('resident')
    if res is not None:
        if not isinstance(res, dict) or not res.get('source'):
            die('"resident" needs a "source"')
        if not os.path.exists(os.path.join(appdir, res['source'])):
            die('resident source %s not found' % res['source'])
        res.setdefault('exports', [])
        for n in res['exports']:
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', n):
                die('resident export %r is not a label' % n)
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
    pm = 0 if 'pool' in app['omit'] else app['pool_max_pages']       # (no pool: no bitmap)
    L.append('POOLMX EQU  %d            pages the pool can manage: pool_max_pages' % pm)
    L.append('POOLBM EQU  >%04X          the pool bitmap: at the top of the kernel\'s pages' % (0xC000 - pm // 8))
    L.append('POOLWD EQU  %d             its size in words' % (pm // 16))
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


def equ_labels(equ):
    """Every label the assembler wrote to the equate file: {lower-case name: value}."""
    out, lines = {}, open(equ).read().split('\n')
    for i in range(len(lines) - 1):
        if lines[i].endswith(':') and 'equ' in lines[i + 1]:
            m = re.search(r'>([0-9a-fA-F]+)', lines[i + 1])
            out[lines[i][:-1].lower()] = int(m.group(1), 16)
    return out


def export_public(ksrc, bdir, equ, extra=()):
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
    keep.update(n.lower() for n in extra)           # the application's resident routines
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
    nopool = 'pool' in app['omit']
    if not nopool and app['pool_max_pages'] <= pgfree:
        die('"pool_max_pages" (%d) must be above the first free page (>%02X): the pool would be empty' % (app['pool_max_pages'], pgfree))
    kmax = 0x2000 if nopool else 0xC000 - app['pool_max_pages'] // 8 - 0xA000     # the kernel may be this long: the pool bitmap, if any, is above it
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
    incs = [appdir, bdir, os.path.join(ROOT, 'kernel'), os.path.join(ROOT, 'gen'), os.path.join(ROOT, 'lib')]
    kincs = [bdir, os.path.join(ROOT, 'kernel'), os.path.join(ROOT, 'gen'), os.path.join(ROOT, 'lib')]    # the kernel never sees the application's files...
    ksrc = os.path.join(ROOT, 'kernel')
    res = app.get('resident')
    if res:
        kincs.append(appdir)               # ...except for resident code, and then last, so it cannot shadow the kernel's
        shutil.copy(os.path.join(appdir, res['source']), os.path.join(bdir, 'resident.a99'))
        text = ('* the application\'s resident code (app.json "resident"), assembled with the kernel\n'
                'KRESB  EVEN\n       COPY "resident.a99"\n       EVEN\nKRESE\n')
    else:
        text = '* no resident code\nKRESB\nKRESE\n'
    open(os.path.join(bdir, 'kresident.a99'), 'w').write(text)
    if app['omit']:
        gone = omitted_routines(app, ksrc)
        users = [(m['name'], os.path.join(appdir, m['source'])) for m in app['modules']]
        if res:
            users.append(('the resident code', os.path.join(appdir, res['source'])))
        for who, path in users:
            hit = sorted(gone.keys() & source_words(path, incs))
            if hit:
                die('%s uses %s, which this kernel does not have: app.json leaves "%s" out of it' % (who, hit[0], gone[hit[0]]))
    equ = os.path.join(bdir, 'kernel.equ')
    kernel = asm(os.path.join(ksrc, 'kernel.a99'), os.path.join(bdir, 'kernel.bin'), kincs,
                 os.path.join(bdir, 'kernel.lst'), equ, [OMITTABLE[o][0] for o in app['omit']])
    labels = equ_labels(equ)
    rbytes = labels['krese'] - labels['kresb']
    for n in (res or {}).get('exports', []):
        if n.lower() not in labels:
            die('resident export %s is not a label in %s' % (n, res['source']))
    export_public(ksrc, bdir, equ, [n for n in (res or {}).get('exports', [])])
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
    if len(kernel) > kmax:
        die('the kernel (%d bytes%s) %s: it may be at most %s bytes%s' %
            (len(kernel), ', of which resident code %d' % rbytes if res else '',
             'does not fit its 8K' if nopool else 'runs into the page-pool bitmap at >%04X' % (0xA000 + kmax), format(kmax, ','),
             '' if nopool or app['pool_max_pages'] < 4096 else ' (a smaller "pool_max_pages" makes the bitmap, and so the room, smaller; so does leaving out the pool)'))
    for n, sz in sizes:
        if sz > BANK:
            die('%s is %d bytes: over its 8K bank' % (n, sz))
    n = 1
    while n < len(images):
        n *= 2
    n = max(n, 4)
    image = b''.join(b.ljust(BANK, b'\0') for b in images).ljust(n * BANK, b'\0')
    out = os.path.join(bdir, app['name'].lower().replace(' ', '') + '8.bin')
    open(out, 'wb').write(image)
    print('kernel %d bytes (ends >%04X, %d free %s)' % (len(kernel), 0xA000 + len(kernel), kmax - len(kernel),
          'in its 8K: no pool, no bitmap' if nopool else 'below the page-pool bitmap at >%04X' % (0xA000 + kmax)))
    if app['omit']:
        print('  left out of the kernel (app.json "omit"): %s' % ', '.join(app['omit']))
    if res:
        print('  of which resident code %d bytes (exports: %s)' % (rbytes, ' '.join(res['exports']) or 'none'))
    for (nme, sz) in sizes[3:]:
        print('  %-16s %5d bytes' % (nme, sz))
    print('wrote %s: %dK, %d banks, SAMS pages needed: %d (%s)' %
          (out, len(image) // 1024, n, app['min_pages'], 'no pool' if nopool else 'pool from >%02X' % pgfree))


if __name__ == '__main__':
    main()
