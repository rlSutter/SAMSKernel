#!/usr/bin/env python3
"""skbuild.py - build a SAMS Kernel application into a cartridge image.

    python3 tools/skbuild.py APPDIR [--out DIR] [--disk [--geometry sssd|dsdd] [--disk-files FILE...]]

APPDIR holds app.json and the application's sources.  The result is
OUT/APPNAME8.bin (default OUT: build/APPDIR-name): a FinalGROM 99 "8"
image of 8K banks, bank n selected by a write to >6000 + 2n, which is also
what js99er and Classic99 load.

app.json:
  {
    "name":      "HELLO",              menu and refusal-screen name (<= 20 chars)
    "min_pages": 128,                  SAMS pages required: 32, 64, 128 ... 4096
    "modprog": false,                  optional: true lets the cartridge's RUN PROGRAM FILE run module programs from disk (tools/skmodprog.py; implies "ea5"): docs/MODPROG.md
    "ea5": false,                      optional: true adds a second program to the cartridge's menu, RUN PROGRAM FILE (Editor/Assembler option 5, for programs and kernel disk programs): kernel/ea5run.a99
    "motion": false,                   optional: true puts SPMINI, SPMPUT and SPMVEL (sprite motion: a motion table the kernel steps every frame) in the kernel
    "sfx": false,                      optional: true puts SFXPLAY and SFXSTOP (sound effects over the song) in the kernel: 512 bytes
    "prun": false,                     optional: true puts PRUN (run another disk program) in the kernel: 206 bytes
    "disk_name": "HELLO",              optional: the name of the program on a disk (--disk): 1-6 capitals and digits
    "module_size": 8192,               optional: 8192 (default) or 4096: the size every module may be
    "appram_code": {"source": "ar.a99",  optional: code the program keeps in its own RAM, assembled at >2300 (AORG >2300), at most 6K, copied there from
                "exports": ["NAME"]},   a page at start-up; application RAM (APPRAM) then begins after it; exports in arcode.equ
    "common": {"source": "common.a99",   optional: code shared by every module, assembled at >D000 (the source says AORG >D000),
                "exports": ["NAME"]},    at most 4K, mapped into window >D000 at start-up and never moved; its exports are
                                       in common.equ for the modules to COPY. Every module must then be "size": 4096
    "modules": [                       each an 8K bank of code run in slot C
      {"name": "hello", "source": "hello.a99"},
      {"name": "more",  "source": "more.a99", "page": "0x20"},   (optional page)
      {"name": "vm",    "source": "vm.a99", "size": 4096}   (optional: this module's size; at most 4K,
    ],                                  and it leaves window >D000 to the program: docs, part 8)
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
import json, os, re, shutil, struct, subprocess, sys

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
    ms = app.setdefault('module_size', 8192)
    if ms not in (4096, 8192):
        die('\"module_size\" is 4096 or 8192')
    for m in app['modules']:
        m.setdefault('size', ms)
        if m['size'] not in (4096, 8192):
            die('module %s: \"size\" is 4096 or 8192' % m['name'])
    app.setdefault('disk_name', (re.sub('[^A-Z0-9]', '', app.get('name', 'APP').upper()) or 'APP')[:6])
    if not re.fullmatch('[A-Z0-9]{1,6}', app['disk_name']):
        die('\"disk_name\" is 1 to 6 capital letters and digits')
    app.setdefault('boot', names[0])
    if app['boot'] not in names:
        die('"boot" names no module')
    if 'common' in app:
        c = app['common']
        if not isinstance(c, dict) or 'source' not in c:
            die('"common" is {"source": "common.a99", "exports": ["NAME", ...]}')
        if 'common' in [ident(n).lower() for n in names]:
            die('a module named "common" clashes with the "common" code')
        for m in app['modules']:
            if m['size'] != 4096:
                die('"common" is mapped into window >D000 for every module, so every module must be a single page ("size": 4096): %s is 8K' % m['name'])
        app['modules'].append({'name': 'common', 'source': c['source'], 'size': 4096, '_common': True})
    app.setdefault('data', [])
    omit = app.setdefault('omit', [])
    if not isinstance(omit, list) or any(o not in OMITTABLE for o in omit):
        die('"omit" lists some of: %s' % ', '.join(sorted(OMITTABLE)))
    app.setdefault('ea5', False)
    app.setdefault('modprog', False)
    if app['modprog']:
        app['ea5'] = True                 # the runner is what loads a module program
    app.setdefault('sfx', False)
    app.setdefault('motion', False)
    if app['sfx'] and 'music' in omit:
        die('\"sfx\": true needs the music player: \"music\" is left out')
    app.setdefault('prun', False)
    if app['prun'] and 'files' in omit:
        die('\"prun\": true needs the file service: \"files\" is left out')
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
        if 'from' in d and (d['from'].lower().endswith('.png') or d['file'].lower().endswith('.skp')):
            import skpic                      # a picture: a PNG or a TI Artist picture (NAME_P, NAME_C); "rows" (default 88)
            src = os.path.join(app['_dir'], d['from'])
            rec = skpic.record(src, d.get('rows', 88))
            d['_path'] = os.path.join(bdir, d['file'])
            open(d['_path'], 'wb').write(rec)
            fmt, pal, raw, rows = skpic.parse(rec)
            print('picture %s: format %d, %d colours, %d rows, %d bytes' % (d['file'], fmt, len(pal), rows, len(rec)))
        elif 'from' in d:
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
    L.append('ARSIZE EQU  %d           bytes of the program\'s own code at the start of application RAM' % app.get('_arsize', 0))
    L.append('COMMONPG EQU >%02X           the page of the common code, mapped at >D000 at start (0: none)' %
             next((m['_page'] for m in app['modules'] if m.get('_common')), 0))
    if app.get('modprog'):
        com = any(m.get('_common') for m in app['modules'])
        L.append('MODMAX EQU  %d            the largest module program this cartridge takes (docs/MODPROG.md)' % (4096 if com else 8192))
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
    msg += ['       EVEN', "* DKTMPL: the disk start's file name template (docs/DISKSTART.md): the name and /B; the device and two digits go either side",
            "DKTMPL STRI '%s/B'" % app['disk_name'], '       EVEN']
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


def warn_hazards(app, appdir):
    """A warning (not an error) for an expression xas99 evaluates left to right where arithmetic would not (tools/exprcheck.py: `X+8*16` is (X+8)*16)."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import exprcheck
    srcs = [m['source'] for m in app['modules']]
    for key in ('common', 'appram_code'):
        if key in app:
            srcs.append(app[key]['source'])
    for src in srcs:
        path = os.path.join(appdir, src)
        if os.path.exists(path):
            for n, text in exprcheck.hazards(open(path, encoding='latin-1').read().split('\n')):
                print('skbuild: warning: %s:%d: xas99 evaluates this left to right, without precedence: %s' % (src, n, text), file=sys.stderr)


def build_appram_code(app, appdir, bdir, args):
    """app.json "appram_code": code the program keeps in its own RAM, at the start of application RAM (>2300), copied there from a page at start-up.
    It is assembled against the kernel it will run with, but the kernel's application RAM address depends on the code's size, so the build runs once
    first (--kernel-only) with a 2-byte stand-in, assembles the code against that pass's kernel.equ, and then builds for real; check_same_kernel
    makes sure the kernel did not move between the passes.  The code is also a data file (PD_ARCODE is its page) and its exports go to arcode.equ."""
    ar = app['appram_code']
    d = {'file': 'arcode.bin', '_path': os.path.join(bdir, 'arcode.bin')}
    if '--kernel-only' in args:
        open(d['_path'], 'wb').write(b'\0\0')
        app['_arsize'] = 2
    else:
        tmp = bdir + '.ar'
        r = subprocess.run([sys.executable, os.path.abspath(__file__), appdir, '--out', tmp, '--kernel-only'], capture_output=True, text=True)
        if r.returncode:
            die('the first pass (the kernel the application RAM code is assembled against) failed:\n' + r.stdout + r.stderr)
        src = os.path.join(appdir, ar['source'])
        if not re.search(r'^\s+AORG\s+>2300\b', open(src, encoding='latin-1').read(), re.M | re.I):
            die('the application RAM code is assembled at >2300: its source must say AORG >2300')
        code = asm(src, os.path.join(bdir, 'arcode.raw'), [appdir, tmp, os.path.join(ROOT, 'kernel'), os.path.join(ROOT, 'gen'), os.path.join(ROOT, 'lib')],
                   os.path.join(bdir, 'arcode.lst'), os.path.join(bdir, 'arcodeall.equ'))
        if len(code) % 2:
            code += b'\0'
        if len(code) > 0x1800:
            die('the application RAM code is %d bytes: at most 6,144 (>2300-3AFF), so that the program keeps at least 1,792 bytes of data' % len(code))
        open(d['_path'], 'wb').write(code)
        app['_arsize'] = len(code)
        syms = {}
        text = open(os.path.join(bdir, 'arcodeall.equ')).read()
        for mm in re.finditer(r'(\w+):\s*\n\s+equ\s+(>[0-9A-Fa-f]+)', text):
            syms[mm.group(1).upper()] = mm.group(2).upper()
        lines = ['* arcode.equ - made by tools/skbuild.py: what the code in application RAM (>2300) exports']
        for n in ar.get('exports', []):
            if n.upper() not in syms:
                die('the application RAM code exports %s, which its source does not define' % n)
            lines.append('%-8s EQU  %s' % (n.upper(), syms[n.upper()]))
        open(os.path.join(bdir, 'arcode.equ'), 'w').write('\n'.join(lines) + '\n')
    app['data'].append(d)


def check_same_kernel(first, second):
    """the kernel's symbols (but not APPRAM and ARSIZE, which follow the code's size) must be where the first pass put them, or the code assembled against it is wrong"""
    def read(d):
        text = open(os.path.join(d, 'kernel.equ')).read()
        return {m.group(1): m.group(2) for m in re.finditer(r'(\w+):\s*\n\s+equ\s+(>[0-9A-Fa-f]+)', text) if m.group(1) not in ('appram', 'arsize')}
    a, b = read(first), read(second)
    moved = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    if moved:
        die('the kernel moved between the two passes (%s ...): the application RAM code was assembled against the wrong addresses' % ', '.join(moved[:4]))


def write_disk(app, bdir, images, kincs, ksrc, args):
    """The disk start (docs/DISKSTART.md): the bootstrap, an Editor/Assembler option 5 image of the loader assembled with DISKBOOT and loaded at >C000, and
    every bank after bank 0 as an 8K PROGRAM file NAME/Bnn, on a disk image OUT/NAME.dsk."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import skdisk
    boot = asm(os.path.join(ksrc, 'loader.a99'), os.path.join(bdir, 'bootstrap.bin'), kincs, os.path.join(bdir, 'bootstrap.lst'), None, ['DISKBOOT'])
    if len(boot) > BANK:
        die('the disk bootstrap is %d bytes: at most 8,192' % len(boot))
    name = app['disk_name']
    progs = [(name, struct.pack('>HHH', 0, len(boot), 0xC000) + boot)]
    for i in range(1, len(images)):
        # trailing zeros are not stored: the bootstrap zero-fills the rest of the 8K (kernel/dskboot.a99), so the bank arrives as it was
        progs.append(('%s/B%02d' % (name, i), images[i].rstrip(b'\0') or b'\0'))
    geo = args[args.index('--geometry') + 1] if '--geometry' in args else 'dsdd'
    path = os.path.join(bdir, name.lower() + '.dsk')
    files = []
    if '--disk-files' in args:      # source files for the disk too (and this build's KERNEL/EQU, which a program assembled on the TI needs)
        for a in args[args.index('--disk-files') + 1:]:
            if a.startswith('--'):
                break
            files.append(a)
    skdisk.make_disk(path, files, os.path.join(bdir, 'kernel.equ') if files else None, name, geo, programs=progs)
    print('wrote %s: %s disk, the bootstrap %s (%d bytes at >C000) and %d bank files %s/B01-B%02d' %
          (path, geo, name, len(boot), len(progs) - 1, name, len(images) - 1))


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
    warn_hazards(app, appdir)
    if 'appram_code' in app:
        build_appram_code(app, appdir, bdir, args)
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
    if app['omit'] or not app['prun'] or not app['sfx'] or not app['motion']:
        gone = omitted_routines(app, ksrc)
        for name, flag in (('PRUN', 'prun'), ('SFXPLAY', 'sfx'), ('SFXSTOP', 'sfx'), ('SPMINI', 'motion'), ('SPMPUT', 'motion'), ('SPMVEL', 'motion')):
            if not app[flag]:
                gone[name] = flag
        users = [(m['name'], os.path.join(appdir, m['source'])) for m in app['modules']]
        if res:
            users.append(('the resident code', os.path.join(appdir, res['source'])))
        for who, path in users:
            hit = sorted(gone.keys() & source_words(path, incs))
            if hit:
                if gone[hit[0]] in ('prun', 'sfx', 'motion'):
                    die('%s uses %s, which this kernel does not have: app.json needs "%s": true' % (who, hit[0], gone[hit[0]]))
                die('%s uses %s, which this kernel does not have: app.json leaves "%s" out of it' % (who, hit[0], gone[hit[0]]))
    equ = os.path.join(bdir, 'kernel.equ')
    kernel = asm(os.path.join(ksrc, 'kernel.a99'), os.path.join(bdir, 'kernel.bin'), kincs,
                 os.path.join(bdir, 'kernel.lst'), equ, [OMITTABLE[o][0] for o in app['omit']] + (['WITHPRUN'] if app['prun'] else []) + (['WITHSFX'] if app['sfx'] else []) + (['WITHMOTION'] if app['motion'] else []) +
                 (['ARCODE'] if 'appram_code' in app else []))
    labels = equ_labels(equ)
    rbytes = labels['krese'] - labels['kresb']
    for n in (res or {}).get('exports', []):
        if n.lower() not in labels:
            die('resident export %s is not a label in %s' % (n, res['source']))
    export_public(ksrc, bdir, equ, [n for n in (res or {}).get('exports', [])])
    if '--kernel-only' in args:
        sys.exit(0)               # the first pass for application RAM code: the kernel's symbols are all that was wanted
    if 'appram_code' in app:
        check_same_kernel(bdir + '.ar', bdir)
    if app['modprog']:
        import zlib
        crc = zlib.crc32(open(equ, 'rb').read()) & 0xFFFFFFFF          # this kernel build's identity: its exported symbols
        open(os.path.join(bdir, 'modid.a99'), 'w').write(
            '* modid.a99 - made by tools/skbuild.py: this kernel build\'s identity (docs/MODPROG.md)\nKIDHI  EQU  >%04X\nKIDLO  EQU  >%04X\n' % (crc >> 16, crc & 0xFFFF))
        print('kernel build ID %08X: module programs (tools/skmodprog.py) are built against this kernel.equ' % crc)
    loader = asm(os.path.join(ksrc, 'loader.a99'), os.path.join(bdir, 'loader.bin'), kincs,
                 os.path.join(bdir, 'loader.lst'), None,
                 (['WITHEA5'] + (['WITHMODPRG'] if app['modprog'] else []) + (['WITHEA5DIAG'] if app.get('ea5_diag') else [])) if app['ea5'] else None)
    ds = os.path.join(appdir, 'databank.a99')
    ds = ds if os.path.exists(ds) else os.path.join(ksrc, 'databank.a99')
    data = asm(ds, os.path.join(bdir, 'databank.bin'), incs, os.path.join(bdir, 'databank.lst'))
    images = [loader, kernel, data]
    sizes = [('loader', len(loader)), ('kernel', len(kernel)), ('data bank', len(data))]
    built = {}
    for m in sorted(app['modules'], key=lambda m: not m.get('_common')):      # (the common code first: the modules COPY its exports)
        src = os.path.join(appdir, m['source'])
        out = os.path.join(bdir, m['name'] + '.bin')
        b = asm(src, out, incs, os.path.join(bdir, m['name'] + '.lst'),
                os.path.join(bdir, ('commonall' if m.get('_common') else m['name']) + '.equ'))   # (the module's symbols: for tests and debugging)
        if m.get('_common'):
            # the common code: at >D000 (its source says AORG >D000), at most a page; the names it exports go to common.equ
            if len(b) > 4096:
                die('the common code is %d bytes: it may be at most 4,096' % len(b))
            syms = {}
            text = open(os.path.join(bdir, 'commonall.equ')).read()       # (the assembler's own format: "name:" then "equ >addr")
            for mm in re.finditer(r'(\w+):\s*\n\s+equ\s+(>[0-9A-Fa-f]+)', text):
                syms[mm.group(1).upper()] = mm.group(2).upper().replace('>', '>')
            lines = ['* common.equ - made by tools/skbuild.py: what the common code at >D000 exports']
            for n in app['common'].get('exports', []):
                if n.upper() not in syms:
                    die('the common code exports %s, which its source does not define' % n)
                lines.append('%-8s EQU  %s' % (n.upper(), syms[n.upper()]))
            open(os.path.join(bdir, 'common.equ'), 'w').write('\n'.join(lines) + '\n')
        elif m['size'] == 4096:
            # a single-page module: at most 4K, and a flag in the last word of its header (>C006) tells the kernel
            # not to map a second page into >D000 (the program owns that window)
            if len(b) > 4096:
                die('module %s is %d bytes: with \"size\": 4096 it may be at most 4,096' % (m['name'], len(b)))
            if len(b) < 8:
                die('module %s is too short to have the four-word header' % m['name'])
            b = b[:6] + (int.from_bytes(b[6:8], 'big') | 1).to_bytes(2, 'big') + b[8:]
        built[m['name']] = b
    for m in app['modules']:                  # the banks go in the order of the module list, which is the order of the pages
        images.append(built[m['name']])
        sizes.append((m['name'], len(built[m['name']])))
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
    if '--disk' in args:
        write_disk(app, bdir, images, kincs, ksrc, args)
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
