#!/usr/bin/env python3
"""SAMS Kernel tests: the example applications run in tools/sim9900.py.

  python3 tests/test_kernel.py [group ...]      (no names: all)

Groups: sources dbg native nativemods workbench workbenchfull boot refusal ram keys quit modules files browser modes modesquit music rom realdsr
Builds the examples first (tools/skbuild.py; XAS99 or ./xdt99 needed).
The 'rom' group runs the real console ROM's interrupt routine when
TI_CONSOLE_ROM names your own copy of the 8K console ROM (a raw dump, or
an EA5 image); without it the group is skipped.  The ROM is TI's code and
is never part of this repository.  The 'realdsr' group runs the file service and
the disk browser against TI's own disk controller DSR (tools/tifdc.py, a WD1771 on a
disk image): it needs the controller's 8K ROM, at tools/tifdc_dsr.bin or named by
TIFDC_ROM (join the two 4K EPROM images, low half first); skipped without it.
"""
import glob, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import sim9900, keytab

FAILS = []
def check(cond, what):
    print(('  ok   ' if cond else '  FAIL ') + what)
    if not cond: FAILS.append(what)

def build(app):
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'),
                        os.path.join(ROOT, 'examples', app)], capture_output=True, text=True)
    if r.returncode: sys.exit(r.stdout + r.stderr)
    return open(glob.glob(os.path.join(ROOT, 'build', app, '*8.bin'))[0], 'rb').read()

def lines(m): return sim9900.screen(m).split('\n')
def codes(m):
    n = m.rw(0x200E); return [m.rb(0x2040 + i) for i in range(n)]

def boot():
    c = build('hello')
    m, cpu, halt = sim9900.run(c, frames=120)
    check(halt is None, 'hello boots without a halt')
    check(m.vregs[0] == 4 and m.vregs[1] == 0xF0 and m.vregs[49] == 0x40 and m.vregs[50] == 2 and m.vregs[51] == 0,
          'Text 80, 30 rows, position attributes, no sprites, display on')
    check('Hello, SAMS Kernel' in lines(m)[0], 'the module drew its title')
    check(m.rw(0x834C) == 128 and m.rw(0x8348) == 1 and m.rw(0x834A) == 0x19, 'NPAGES 128, F18A found, version 1.9')
    check(m.scratch[0xC2] == 0x50 and m.scratch[0xFC] == 1, 'ISR flags >50, frame increment set')
    check(m.palette.get(1) == 0x23A and m.palette.get(2) == 0xDDE, 'colour scheme 0 in the palette')
    check(bytes(m.vram[0x1800 + 65 * 8:0x1800 + 66 * 8]) == bytes([0x70, 0x88, 0x88, 0x88, 0xF8, 0x88, 0x88, 0]), 'glyph A in the pattern table')
    m, cpu, halt = sim9900.run(c, keys='<ALPHA>hi there', frames=200)
    check(lines(m)[4].startswith('  hi there'), 'typed text is echoed: %r' % lines(m)[4][:14])
    check(m.rw(0x8346) == 0x1213, 'slot C holds the boot module, pages >12 >13 (CURPC=%04X)' % m.rw(0x8346))

def refusal():
    c = build('hello')
    for pages in (64, 32):
        m, cpu, halt = sim9900.run(c, frames=120, pages=pages)
        ln = lines(m)
        check(m.vregs[0] == 0 and any('WITH 512K' in l for l in ln) and any('HELLO' in l for l in ln),
              '%dK card refused in 40-column text, naming the app' % (pages * 4))
    m, cpu, halt = sim9900.run(c, frames=120, sams=False)
    check(any('WITH 512K' in l for l in lines(m)), 'no card refused')
    m, cpu, halt = sim9900.run(c, frames=200, setup=lambda m: m.bad_pages.add(0x2A))
    check(any('FAILED ITS TEST' in l for l in lines(m)) and any('>2A' in l for l in lines(m)), 'a bad page refused and named')
    m, cpu, halt = sim9900.run(c, frames=150, f18a=False)
    check(any('NEEDS AN F18A' in l for l in lines(m)), 'no F18A refused')
    m, cpu, halt = sim9900.run(c, frames=120, pages=256)
    check(m.rw(0x834C) == 256 and 'Hello' in lines(m)[0], '1M card found as 256 pages and accepted')

def ram():
    c = build('hello')
    os.environ['SIM_RANDOM_RAM'] = '7'
    try:
        m, cpu, halt = sim9900.run(c, keys='ab', frames=150)
    finally:
        del os.environ['SIM_RANDOM_RAM']
    check(halt is None and 'Hello' in lines(m)[0] and codes(m) == [0x41, 0x42], 'boots and types from random power-up RAM')

def keys():
    c = build('hello')
    t = keytab.tables()
    bad = 0; n = 0
    for mod, script in (('N', '%s'), ('S', '<S-%s>'), ('F', '<F-%s>'), ('C', '<C-%s>')):
        for col in range(6):
            for row in range(8):
                k = keytab.MATRIX[col][row]
                if k in (None, 'FCTN', 'SHIFT', 'CTRL', '\r', ' ') or t[mod][col * 8 + row] == 0 or (mod == 'F' and k == '='): continue
                if mod == 'N' and k.isalpha(): s = k.lower()
                elif mod == 'N': s = k
                else: s = script % k.lower() if mod != 'N' else k
                if n >= 40 and mod != 'F': continue
                m, cpu, halt = sim9900.run(c, keys=('<ALPHA>' + s) if (mod == 'N' and k.isalpha()) else s, frames=130)
                got = codes(m); n += 1
                if got != [t[mod][col * 8 + row]]: bad += 1; print('    ', mod, k, got, hex(t[mod][col * 8 + row]))
    check(bad == 0, 'a sample of chords (%d) gives the codes tools/keytab.py says' % n)
    m, cpu, halt = sim9900.run(c, keys='<HOLD 60>a', frames=140)
    check(len(codes(m)) == 10, 'a key held 60 frames gives 10 codes (press, then every 4 from the 24th): %d' % len(codes(m)))

def quit_():
    c = build('hello')
    m, cpu, halt = sim9900.run(c, keys='<F-=>e', frames=300)
    r = getattr(m, 'at_reset', None)
    check(r is not None, 'FCTN = resets the console (BLWP @>0000)')
    if r:
        regs, pal, mapping = r
        check(regs[49] == 0 and regs[50] == 0 and regs[51] == 0x20 and regs[15] == 0, 'F18A registers as at power-up before the reset')
        check(pal.get(7) == 0x4EF and pal.get(15) == 0xFFF, 'standard palette restored')
        check(not mapping, 'SAMS mapping off at the reset')

def modules():
    c = build('diag')
    m, cpu, halt = sim9900.run(c, keys='<C-t><WAIT 700>', frames=1000)
    res = [m.rw(0x2202 + 2 * i) for i in range(8)]
    check(m.rw(0x2200) == 8 and res == [1] * 8, 'self-test: 8 of 8 pass %s' % res)
    m2, cpu, halt = sim9900.run(c, keys='<C-t><WAIT 700>x', frames=1100)
    check('diagnostic' in lines(m2)[0], 'a key in the self-test returns to the diagnostic (GOMOD PREVPG)')
    m3, cpu, halt = sim9900.run(c, keys='<C-3>', frames=200)
    check(m3.palette.get(1) == 0x3A4, 'CTRL 3 loads colour scheme 1 (SETSCH)')
    m4, cpu, halt = sim9900.run(c, keys='<F-=>e', frames=300)
    check(getattr(m4, 'at_reset', None) is not None, 'quit from the diagnostic')

def files():
    c = build('diag')
    m, cpu, halt = sim9900.run(c, keys='<C-t><WAIT 700>', frames=1000)
    check('PASS' in lines(m)[10], 'DSK1 write, read, end of file, delete, file gone')
    def nodrive(m): m.dsr_on = False
    # a drive that is not there: the DSR search finds no card
    c2 = c
    m, cpu, halt = sim9900.run(c2, keys='<C-t><WAIT 700>', frames=1000, setup=lambda m: setattr(m, 'dsrrom', bytearray(0x2000)))
    check('FAIL' in lines(m)[10] and '1' in lines(m)[10], 'no drive: the file check fails with a step and error (%r)' % lines(m)[10][38:60])

def browser():
    c = build('browser')
    def setup(m):
        m.dvfiles['README'] = [('line %d' % i).encode() for i in range(1, 130)]
        m.dvfiles['NOTES'] = [b'a short file', b'two']
        m.dvfiles['DATA'] = [bytes([1, 2, 3, 4])] * 3
        m.ftypes['DATA'] = (False, True, 4)
    m, cpu, halt = sim9900.run(c, keys='<WAIT 40>', frames=200, setup=setup)
    ln = lines(m)
    check('PRESSDISK' in ln[2] and '1440' in ln[2], 'the catalog: the disk line')
    check(ln[5].split()[:2] == ['DATA', 'INT/FIX'] and ln[6].split()[:2] == ['NOTES', 'DIS/VAR'] and ln[7].split()[:2] == ['README', 'DIS/VAR'], 'the catalog: three files with types')
    m, cpu, halt = sim9900.run(c, keys='<ENTER><WAIT 60>', frames=300, setup=setup)
    check('Not a DIS/VAR' in lines(m)[27], 'ENTER on an INT/FIX file: refused')
    m, cpu, halt = sim9900.run(c, keys='<F-x><F-x><ENTER><WAIT 200>', frames=700, setup=setup)
    ln = lines(m)
    check('DSK1.README' in ln[0] and ln[2].strip() == 'line 1' and ln[27].strip() == 'line 26', 'GOMOD with an argument: README viewed, 26 lines')
    check('Line 1 of 129' in ln[29], 'the footer: %r' % ln[29][55:80])
    m, cpu, halt = sim9900.run(c, keys='<F-x><F-x><ENTER><WAIT 200><F-x><F-x><F-x>', frames=900, setup=setup)
    check(lines(m)[2].strip() == 'line 4' and 'Line 4 of 129' in lines(m)[29], 'DOWN scrolls (lines read into pool pages, drawn through MAPE)')
    m, cpu, halt = sim9900.run(c, keys='<F-x><F-x><ENTER><WAIT 200><F-9><WAIT 100>', frames=900, setup=setup)
    check('Disk browser' in lines(m)[0], 'BACK returns to the browser (PREVPG)')

def rom_music():
    import skmusic
    p = os.environ.get('TI_CONSOLE_ROM')
    if not p or not os.path.exists(p):
        return
    c = build('music')
    skm, _ = skmusic.compile_file(os.path.join(ROOT, 'examples', 'music', 'songs', 'scale.mml'))
    exp = [0x9F, 0xBF, 0xDF, 0xFF] + [b for f, b in skmusic.decode(skm)[0]]
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5>2<WAIT 150>', frames=260, rom=p)
    got = [b for (src, i, b) in m.chip_log if src == 'cpu']
    check(got[:len(exp)] == exp and not [1 for (src, i, b) in m.chip_log if src == 'isr'],
          'music under the real ISR: the same bytes, and the console routine writes none of its own')

def rom():
    p = os.environ.get('TI_CONSOLE_ROM')
    if not p or not os.path.exists(p):
        print('  skip  set TI_CONSOLE_ROM to your own console ROM to run the real interrupt routine'); return
    for app, k in (('hello', '<ALPHA>ab'), ('diag', '<C-t><WAIT 700>')):
        c = build(app)
        m, cpu, halt = sim9900.run(c, keys=k, frames=1000, rom=p)
        check(halt is None and m.isr_count > 100 and m.rw(0x8340) > 100, '%s runs under the real ISR (%d interrupts, FRAME %d)' % (app, m.isr_count, m.rw(0x8340)))
        if app == 'diag':
            check(m.rw(0x2200) == 8 and all(m.rw(0x2202 + 2 * i) == 1 for i in range(8)), 'the self-test passes under the real ISR')
        else:
            check(lines(m)[4].startswith('  ab'), 'typing works under the real ISR')
    rom_music()

def realdsr():
    rp = os.environ.get('TIFDC_ROM') or os.path.join(ROOT, 'tools', 'tifdc_dsr.bin')
    if not os.path.exists(rp):
        print('  skip  TI controller ROM not found (tools/tifdc_dsr.bin or TIFDC_ROM)'); return
    os.environ['TIFDC_ROM'] = rp
    import tifdc
    crom = os.environ.get('TI_CONSOLE_ROM')
    crom = crom if crom and os.path.exists(crom) else None
    for withrom in ([None, crom] if crom else [None]):
        tag = 'real console ROM + ' if withrom else ''
        c = build('diag')
        img = tifdc.blank_disk()
        m, cpu, halt = sim9900.run(c, keys='<C-t><WAIT 2500>', frames=3200, rom=withrom,
                                   setup=lambda m: setattr(m, 'tifdc', tifdc.TIFDC(image=img)))
        check('PASS' in lines(m)[10] and m.rw(0x2200) == 8 and 'Passed 8   of 8' in lines(m)[12],
              tag + "TI's controller: the self-test's file check passes (%r)" % lines(m)[10][38:60])
        check(tifdc.TIFDC(image=img).files() == {}, 'the test file was written, read back and deleted on the disk image')
    b = build('browser')
    img = bytearray(open(os.path.join(ROOT, 'tests', 'data', 'pressref.dsk'), 'rb').read())
    hook = lambda m: setattr(m, 'tifdc', tifdc.TIFDC(image=img))
    m, cpu, halt = sim9900.run(b, keys='<WAIT 1200>', frames=1800, setup=hook)
    ln = lines(m)
    check('PRESSREF' in ln[2] and '358' in ln[2] and '336' in ln[2], "TI's catalog records decoded: the disk, 358 sectors, 336 free")
    check(ln[5].split()[:3] == ['REFDOC', 'DIS/VAR', '22'], 'the file: REFDOC DIS/VAR 22 sectors')
    m, cpu, halt = sim9900.run(b, keys='<ENTER><WAIT 1800>', frames=3000, setup=hook)
    want = tifdc.read_file(img, 'REFDOC')
    check('DSK1.REFDOC' in lines(m)[0] and 'Notes on a Word Processor' in lines(m)[2]
          and lines(m)[4].startswith(want[2].decode('latin-1')[:40]),
          'the viewer shows the real file through the real DSR (lines 1 and 3 match the disk image)')

def modes_quit():
    """Quitting from the screens that set the most registers puts them all back."""
    c = build('modes')
    for key, what in (('c', 'tile layer 2 and scroll'), ('d', 'the bitmap layer'), ('b', 'sprites with enhanced colour')):
        m, cpu, halt = sim9900.run(c, keys='<WAIT 5>' + key + '<WAIT 30><F-=>e', frames=900)
        r = getattr(m, 'at_reset', None)
        check(r is not None, '%s: FCTN = resets the console' % what)
        if r:
            regs = r[0]
            zero = [regs[i] for i in (10, 11, 19, 24, 25, 26, 27, 28, 29, 30, 31, 49, 50)]
            check(zero == [0] * 13 and regs[51] == 32 and regs[48] == 1 and regs[15] == 0,
                  '%s: VR10 VR11 VR19 VR24-31 VR49 VR50 back to 0, VR51 = 32, VR48 = 1 before the reset' % what)

def sources():
    """Every source line fits a TI text file (80 columns, ASCII, no tabs) and the public list has headers."""
    import lint80, docindex
    glob_ = sorted(glob.glob(os.path.join(ROOT, 'kernel', '*.a99')) + glob.glob(os.path.join(ROOT, 'examples', '*', '*.a99')))
    bad = [(os.path.relpath(f, ROOT), n, w) for f in glob_ for n, w in lint80.problems(f)]
    check(not bad, 'all %d sources are TI-editable (80 columns, ASCII): %s' % (len(glob_), bad[:3]))
    h = docindex.headers()
    miss = [n for n in docindex.PUBLIC if n not in h]
    check(not miss, 'every public routine has a header comment: %s' % miss)

def dbg():
    """kernel/dbg.a99: a module COPYs it; DBG shows R0-R3, waits for a key, keeps every register."""
    import tempfile, shutil
    d = tempfile.mkdtemp()
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'newapp.py'), d, '--name', 'DBGTEST'], capture_output=True)
    src = open(os.path.join(d, 'main.a99')).read()
    src = src.replace('       LI   R1,ATEXT\n       BL   @CLS\n       CLR  R0\n       LI   R1,ABAR','       LI   R1,ATEXT\n       BL   @CLS\n       CLR  R0\n       LI   R1,ABAR', 1)
    src = src.replace('INIT   .enter\n       BL   @REDRAW\n       .leave','INIT   .enter\n       BL   @REDRAW\n       LI   R0,>1234\n       LI   R1,>BEEF\n       LI   R2,>0042\n       LI   R3,>FFFF\n       LI   R4,>4444\n       LI   R9,>9999\n       BL   @DBG\n       MOV  R4,@APPRAM+20\n       MOV  R9,@APPRAM+22\n       MOV  R0,@APPRAM+24\n       .leave', 1)
    src = src.replace("TITLE  STRI", '       COPY "dbg.a99"\nTITLE  STRI', 1)
    open(os.path.join(d, 'main.a99'), 'w').write(src)
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d, '--out', os.path.join(d, 'b')], capture_output=True, text=True)
    if r.returncode: sys.exit(r.stdout + r.stderr)
    c = open(glob.glob(os.path.join(d, 'b', '*8.bin'))[0], 'rb').read()
    m, cpu, halt = sim9900.run(c, frames=150)
    row = lines(m)[29]
    check(row[2:21] == '1234 BEEF 0042 FFFF', 'DBG shows R0-R3 on the bottom row: %r' % row[:24])
    check(m.rw(0x2314) == 0, 'DBG waits for a key: the code after it has not run')
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5>x<WAIT 20>', frames=300)
    check((m.rw(0x2314), m.rw(0x2316), m.rw(0x2318)) == (0x4444, 0x9999, 0x1234), 'after a key DBG returns with R0, R4 and R9 as they were')
    shutil.rmtree(d, ignore_errors=True)

def music():
    """The music player: the music demo and the compiler, checked against the bytes the player
    writes to the sound chip, their timing, and the pitch of what a model of the chip makes of them."""
    import skmusic, sn76489, struct
    c = build('music')
    VF = sim9900.VSYNC_INSNS
    def chip(m): return [(i, b) for (src, i, b) in m.chip_log if src == 'cpu']
    def songbytes(name, **kw):
        skm, info = skmusic.compile_file(os.path.join(ROOT, 'examples', 'music', 'songs', name), **kw)
        return skm
    SIL = [0x9F, 0xBF, 0xDF, 0xFF]
    # a one-note song: the bytes, the timing, the pitch
    skm = songbytes('scale.mml')
    ev, nframes = skmusic.decode(skm)
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5>2<WAIT 150>', frames=260)
    log = chip(m)
    check([b for i, b in log[:4 + len(ev)]] == SIL + [b for f, b in ev], 'scale: MUPLAY silences the chip, then the song\'s bytes arrive exactly as compiled')
    t0 = log[4][0]
    check(abs((log[-5][0] - t0) / VF - 0) < 1.5 and abs((log[-1][0] - t0) / VF - nframes) < 1.5 and m.rw(0x21C0) == 0,
          'scale: the song ends %d frames after it began and stops by itself (MUSTAT = 0), silencing the chip' % nframes)
    s = sn76489.synth([((i - t0) / (VF * 60.0), b) for i, b in log[4:-4]], 1.5)
    check(abs(sn76489.peak_hz(s[2000:20000]) - 440.4) < 3, 'scale: the note sounds at 440 Hz (a model of the chip, FFT peak %.1f)' % sn76489.peak_hz(s[2000:20000]))
    # the tune: it loops; the second pass writes what the first did
    skm = songbytes('tune.mml', loop=True)
    ev, nframes = skmusic.decode(skm, 2)
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5>1<WAIT 1180>', frames=1300)
    log = chip(m)
    got = [b for i, b in log[4:]]
    check(m.rw(0x21C0) != 0 and got[:len(ev)] == [b for f, b in ev][:len(got)] and len(got) > len(ev) // 2 + 100,
          'tune: loops, and the bytes written (%d) are the compiled two passes\' bytes' % len(got))
    # pause and resume: silent while paused, the same sound afterwards
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5>1<WAIT 150> <WAIT 60> <WAIT 80>', frames=520)
    log = chip(m)
    paused = [i for i, b in log if False]
    model = sn76489.Sn76489(); before = None
    # find the pause: four silence bytes written by MUPAUSE after the song's bytes began
    idx = [k for k in range(8, len(log) - 3) if [b for i, b in log[k:k + 4]] == SIL]
    check(len(idx) == 1, 'pause: exactly one run of four silencing bytes after the song began')
    k = idx[0]
    for i, b in log[:k]: model.write(b)
    snap = (list(model.div), list(model.att), model.noise)
    for i, b in log[k:k + 4 + 11]: model.write(b)       # the four silencing bytes, then the 8 latch and 3 data bytes of the restore
    after = (list(model.div), list(model.att), model.noise)
    check(snap == after and any(a < 15 for a in after[1]), 'pause: the restore writes put back the dividers and volumes the chip had before the pause')
    mid = [i for i, b in log[k + 4:]]
    check(not [1 for (i, b) in log[k + 4:k + 12] if (i - log[k + 3][0]) / VF < 30 and k + 12 < len(log) and False] and (log[k + 4][0] - log[k + 3][0]) / VF > 40,
          'pause: nothing is written while paused (%.0f frames)' % ((log[k + 4][0] - log[k + 3][0]) / VF))
    # KIDLE steps the song through a loop that never returns to the main loop
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5>1<WAIT 20>w<WAIT 200>', frames=400)
    log = chip(m)
    times = [i / VF for i, b in log[4:]]
    # the keys go down at frame 60+: W at about frame 140; the loop ends 120 frames later
    wstart = [(src, i) for (src, i, b) in m.chip_log][0][1] / VF
    work = [t for t in times if 140 <= t <= 255]
    check(len(work) > 20, 'KIDLE: %d chip writes during the two seconds of work (the song went on)' % len(work))
    # SNDTONE and SNDOFF
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5>b<WAIT 20>o<WAIT 20>', frames=200)
    b = [x for i, x in chip(m)]
    check(b[:3] == [0x8E, 0x0F, 0x90] and b[3:7] == SIL, 'SNDTONE: voice 1, divider 254 (>8E, >0F) loudest (>90); SNDOFF: the four voices off')
    # stop, and quit silences the chip
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5>1<WAIT 20>s<WAIT 20><F-=>e', frames=300)
    b = [x for i, x in chip(m)]
    check(m.rw(0x21C0) == 0 and b[-4:] == SIL, 'S stops the song, and quitting leaves the chip silent')
    # the compiler from MIDI: two notes and a drum, as a standard MIDI file
    def vlq(n):
        out = [n & 0x7F]; n >>= 7
        while n: out.append(0x80 | (n & 0x7F)); n >>= 7
        return bytes(reversed(out))
    trk = b'\x00\xFF\x51\x03' + (500000).to_bytes(3, 'big')
    trk += b'\x00\x90\x45\x64' + vlq(480) + b'\x80\x45\x00' + b'\x00\x90\x48\x64' + vlq(480) + b'\x80\x48\x00'
    trk += b'\x00\x99\x26\x7F' + vlq(120) + b'\x89\x26\x00' + b'\x00\xFF\x2F\x00'
    smf = b'MThd' + struct.pack('>IHHH', 6, 0, 1, 480) + b'MTrk' + struct.pack('>I', len(trk)) + trk
    open('/tmp/sk_test.mid', 'wb').write(smf)
    skm, info = skmusic.compile_file('/tmp/sk_test.mid')
    ev, nf = skmusic.decode(skm)
    divs = []
    model = sn76489.Sn76489()
    frames = {}
    for f, b in ev: frames.setdefault(f, []).append(b)
    for f in sorted(frames):                 # look at the chip between frames: a divider arrives in two bytes
        for b in frames[f]: model.write(b)
        if model.att[0] < 15 and (not divs or model.div[0] != divs[-1]): divs.append(model.div[0])
    check(divs == [254, 214] and nf >= 60 and any(0xE0 <= b <= 0xF0 for f, b in ev),
          'MIDI: A4 (divider 254) then C5 (214) on voice 1, one second each at 120 BPM, and the drum on the noise voice: %s, %d frames' % (divs, nf))
    skm2, info2 = skmusic.compile_file('/tmp/sk_test.mid', loop_at=1.0)
    lp = struct.unpack('>H', skm2[4:6])[0]
    ev2, _ = skmusic.decode(skm2, 2)
    check(lp != 0xFFFF and lp > 8 and len(ev2) > len(ev), 'compiler: loop-at one second makes a loop target (offset %d) and the second pass replays from there' % lp)

def native():
    """The assembler that runs on the TI (examples/workbench/asm.a99), checked against xas99: the probe
    sources byte for byte, a broken source error for error, and the encodings xas99 gets wrong."""
    import asmharness
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    X = os.environ.get('XAS99', os.path.join(ROOT, 'xdt99', 'xas99.py'))
    def xas(src):
        out = '/tmp/sk_native.bin'
        r = subprocess.run([sys.executable, X, '-R', '-b', '-I', os.path.join(ROOT, 'kernel'), '-o', out, src], capture_output=True, text=True)
        if r.returncode: sys.exit(r.stdout + r.stderr)
        return open(out, 'rb').read()
    for name in ('probe1', 'probe2'):
        src = os.path.join(ROOT, 'tests', 'asm', name + '.a99')
        r = asmharness.assemble(src, 'hello')
        want = xas(src)
        check(r.errors == 0 and r.image == want, '%s: every instruction form, directive and macro: %d bytes, byte for byte as xas99 (errors %d)' % (name, len(want), r.errors))
    r = asmharness.assemble(os.path.join(ROOT, 'tests', 'asm', 'errors.a99'), 'hello')
    found = sorted(set((l, c & 255) for l, c in r.errtab))
    want = [(3, 1), (4, 2), (5, 3), (6, 4), (7, 5), (10, 7), (13, 2), (15, 11), (17, 12)]
    check(all(w in found for w in want), 'errors.a99: unknown operation, bad operand, undefined symbol, duplicate label, jump range, missing file, R0 index, bad list, EQU without label are all found: %s' % [w for w in want if w not in found])
    check((14, 10) in found and (8, 6) in found and (9, 6) in found and (16, 6) in found,
          'errors.a99: and what xas99 lets through: a long label, SBO 200, SLA 16, BYTE 300')
    open('/tmp/ldcr.a99', 'w').write('       AORG >C000\n       LDCR R1,16\n       STCR R1,16\n       LDCR R1,1\n')
    r = asmharness.assemble('/tmp/ldcr.a99', 'hello')
    check(r.image.hex() == '300134013041', 'LDCR with 16 bits is >3001 (xas99 makes it >3401, an STCR): %s' % r.image.hex())

def nativemods():
    """Every example module, assembled on the simulated TI from its source on a disk: identical to xas99's."""
    import asmharness
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    mods = [('hello', 'hello', 'hello', ()), ('music', 'music', 'music', ()), ('browser', 'browse', 'browser/browse.a99', ('browser/shared.a99',)),
            ('browser', 'view', 'browser/view.a99', ('browser/shared.a99',)), ('modes', 'modes', 'modes/modes.a99', ()),
            ('diag', 'diag', 'diag/diag.a99', ()), ('diag', 'tests', 'diag/tests.a99', ())]
    for app, mod, src, extra in mods:
        src = os.path.join(ROOT, 'examples', src if '/' in src else src + '/' + src + '.a99')
        extra = [os.path.join(ROOT, 'examples', e) for e in extra]
        build(app)
        want = open(os.path.join(ROOT, 'build', app, mod + '.bin'), 'rb').read()
        r = asmharness.assemble(src, app, extra)
        check(r.errors == 0 and r.image == want, '%s: %d bytes assembled on the TI, identical to xas99 (errors %d)' % (mod, len(want), r.errors))

def workbench():
    """The workbench: the editor's keys, the catalog, and the whole round: type a program in the editor,
    assemble it, run it."""
    import asmharness, tifdc
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    open('/tmp/t1.txt', 'w').write('first\nsecond\nthird\n')
    pre = '<WAIT 10>nT1/TXT<ENTER><WAIT 10>e<WAIT 300>'
    def ed(k, frames=720):
        m, img = asmharness.workbench_ui(pre + k + '<WAIT 20>', frames, ['/tmp/t1.txt'])
        return asmharness.editor_lines(m), m, img
    L, m, img = ed('XY')
    check(L == ['XYfirst', 'second', 'third'], 'editor: typing inserts: %s' % L)
    L, m, img = ed('<F-2>ZZ')
    check(L[0] == 'ZZrst', 'editor: FCTN 2 switches to overwriting: %s' % L[0])
    L, m, img = ed('XY<F-x><F-5><F-d><F-d><ENTER>')
    check(L == ['XYfirst', 'se', 'cond', 'third'], 'editor: ENTER splits a line: %s' % L)
    L, m, img = ed('XY<F-x><F-5><F-d><F-d><ENTER><C-h>')
    check(L == ['XYfirst', 'second', 'third'], 'editor: CTRL H at the start of a line joins it to the one before: %s' % L)
    L, m, img = ed('<F-x><F-3>')
    check(L == ['first', 'third'], 'editor: FCTN 3 deletes the line: %s' % L)
    L, m, img = ed('<F-d><F-1><F-1>')
    check(L[0] == 'fst', 'editor: FCTN 1 deletes characters: %s' % L[0])
    L, m, img = ed('<F-6>Q<F-5>P')
    check(L[0] == 'PfirstQ', 'editor: BEGIN and PROC\'D go to the ends of the line: %s' % L[0])
    L, m, img = ed('<F-e><F-e><F-s><F-8><F-7>')
    check(L == ['first', 'second', 'third'], 'editor: moving past the ends changes nothing')
    L, m, img = ed('XY<F-x><F-5><F-d><F-d><ENTER><C-h><F-x><F-3><WAIT 20><C-s><WAIT 120>', 1300)
    check(tifdc.read_file(img, 'T1/TXT') == [b'XYfirst', b'second'], 'editor: CTRL S writes the file: %s' % tifdc.read_file(img, 'T1/TXT'))
    m, img = asmharness.workbench_ui('<WAIT 10>c<WAIT 120><F-x><WAIT 20><ENTER><WAIT 20>', 400, ['/tmp/t1.txt'])
    check(bytes(m.rb(0x2300 + 1 + i) for i in range(11)).startswith(b'DSK1.T1/TXT'), 'catalog: UP and DOWN pick a file and ENTER makes it the file name: %s' % bytes(m.rb(0x2300 + i) for i in range(16)))
    # a program comes back to the workbench with GOMOD PG_WB
    open('/tmp/ret.a99', 'w').write('\n'.join(['       COPY "kernel.equ"', '       COPY "macros.a99"', '       AORG >C000', '       DATA INIT,TICK,INIT,0',
        'INIT   RT', 'TICK   .enter', '       MOV  R0,R0', '       JEQ  T9', '       LI   R0,PG_WB', '       CLR  R1', '       BL   @GOMOD', 'T9     .leave', '       RT']) + '\n')
    m, img = asmharness.workbench_ui('<WAIT 10>nRET/A99<ENTER><WAIT 10>a<WAIT 2500>r<WAIT 60><ALPHA>x<WAIT 80>', 3200, ['/tmp/ret.a99'])
    ln = sim9900.screen(m).split('\n')
    check(ln[0].strip() == 'SAMS Kernel   workbench' and 'Assembled' in ln[9], 'a program returns to the workbench with GOMOD PG_WB, and its result is still there: %r' % ln[9].strip())

def workbenchfull():
    """The whole round on the simulated TI: type a program in the editor, assemble it, run it."""
    import asmharness, tifdc
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    prog = ['       COPY "kernel.equ"', '       COPY "macros.a99"', '       AORG >C000', '       DATA INIT,TICK,INIT,0',
            'INIT   .enter', '       LI   R0,2*COLS+2', '       LI   R1,MSG', '       LI   R2,(RTEXT*16+RBG)*256',
            '       BL   @PUTS', '       .leave', '       RT', 'TICK   RT', "MSG    STRI 'Built on the TI'"]
    keys = '<WAIT 10>nNEW1<ENTER><WAIT 10>e<WAIT 300>' + '<ENTER>'.join(prog) + '<WAIT 30><C-a><WAIT 2500>r<WAIT 150>'
    m, img = asmharness.workbench_ui(keys, 9000)
    ln = sim9900.screen(m).split('\n')
    rec = tifdc.read_file(img, 'NEW1')
    check(rec and rec[0] == b'       COPY "KERNEL.EQU"' and len(rec) == 13, 'typed in the editor and saved to the disk as NEW1 (13 lines)')
    check(m.rw(0x2300 + 526) == 0 and m.rw(0x2300 + 524) == 50, 'CTRL A saved and assembled it on the TI: no errors, 50 bytes')
    check(ln[2].strip() == 'BUILT ON THE TI', 'R ran it, in SAMS pages, as a module: its screen says %r' % ln[2].strip())

def modes():
    """Every display mode: the modes demo application (examples/modes) run in the
    simulator, each screen drawn by tools/f18render.py and its pixels checked."""
    import f18render
    c = build('modes')
    def screen(key, frames=700):
        m, cpu, halt = sim9900.run(c, keys='<WAIT 5>' + key + '<WAIT 20>', frames=frames)
        img = f18render.render(m)
        pal = f18render.palette_rgb(m)
        px = lambda x, y: tuple(int(v) for v in img[y, x])
        pl = lambda i: pal[i]
        has = lambda x0, y0, x1, y1, color: any(px(x, y) == color for y in range(y0, y1) for x in range(x0, x1))
        return m, img, px, pl, has
    def regs(m): return dict(v0=m.vregs[0], v1=m.vregs[1], v3=m.vregs[3], v49=m.vregs[49], v50=m.vregs[50], v51=m.vregs[51])
    def geo(m): return (m.rw(0x20EC), m.rw(0x20EE), m.rw(0x20F0), m.rw(0x20F2), m.rw(0x20F4))
    # 1 Text 80, 30 rows, attribute per position (the boot mode)
    m, img, px, pl, has = screen('1')
    check(f18render.mode_of(m) == f18render.TEXT80 and img.shape == (240, 512, 3) and geo(m) == (80, 30, 2400, 0xFFFF, 0),
          '1: Text 80, 30 rows, attributes per position; TXCOLS/TXROWS/TXCELLS/TXATTR/NAMBAS set')
    check(regs(m)['v49'] == 0x40 and regs(m)['v50'] == 2 and regs(m)['v51'] == 0, '1: VR49 = 30 rows, VR50 = position attributes, VR51 = no sprites')
    check(has(16, 8 * 8, 16 + 80, 9 * 8, pl(6)) and has(16, 14 * 8, 16 + 80, 15 * 8, pl(12)) and not has(16, 8 * 8, 16 + 80, 9 * 8, pl(12)),
          '1: role 6 and role 12 rows draw in their own colours (per-position attributes)')
    # 2 Text 80, 24 rows, VR7 colours
    m, img, px, pl, has = screen('2')
    check(img.shape == (192, 512, 3) and geo(m) == (80, 24, 1920, 0, 0) and m.vregs[50] == 0, '2: Text 80, 24 rows, no attribute table')
    check(has(16, 8 * 8, 16 + 80, 9 * 8, pl(2)) and not has(16, 8 * 8, 16 + 80, 9 * 8, pl(6)), '2: every row in the text colour of VR7 (attributes ignored)')
    # 3, 4 Text 40
    m, img, px, pl, has = screen('3')
    check(f18render.mode_of(m) == f18render.TEXT and img.shape == (192, 256, 3) and geo(m) == (40, 24, 960, 0, 0), '3: Text 40, 24 rows')
    m, img, px, pl, has = screen('4')
    check(img.shape == (240, 256, 3) and geo(m) == (40, 30, 1200, 0xFFFF, 0) and has(8, 8 * 8, 8 + 100, 9 * 8, pl(6)), '4: Text 40, 30 rows, colour per position')
    # 5 Graphics I: glyph 'A' (65) is in group 8: colour 8 mod 14 + 2 = 10
    m, img, px, pl, has = screen('5')
    check(f18render.mode_of(m) == f18render.GRAPHICS and geo(m)[:2] == (32, 24) and m.vregs[3] == 0x27, '5: Graphics I, colour table at >09C0')
    check(has(8, 5 * 8, 16, 6 * 8, pl(10)), "5: glyph 'A' (code 65, group 8) is colour 10")
    # 6 Graphics II
    m, img, px, pl, has = screen('6', 900)
    check(f18render.mode_of(m) == f18render.BITMAP and m.vregs[0] == 2 and m.vregs[2] == 6 and m.vregs[3] == 0xFF, '6: Graphics II: VR0 M3, names >1800, colours >2000')
    check(px(0, 0) == pl(2) and px(1, 0) == pl(1) and px(7, 7) == pl(2) and px(8, 0) == pl(3), '6: tile 0 diagonal in colour 2 on the page; the next tile one colour up')
    # the Graphics II address formula in VIDEO-MODES.md: poke a pixel and its colour, draw again
    for (x, y, fg) in ((100, 150, 5), (3, 70, 9), (250, 190, 12)):
        off = (y >> 6) * 2048 + ((((y >> 3) & 7) * 32 + (x >> 3)) * 8) + (y & 7)
        m.vram[off] |= 0x80 >> (x & 7)
        m.vram[0x2000 + off] = (fg << 4) | 1
        check(f18render.render(m)[y, x].tolist() == list(f18render.palette_rgb(m)[fg]), '6: pixel (%d,%d) at GM2PT+%d is colour %d (the documented address formula)' % (x, y, off, fg))
    # 7 Multicolor: cell (5,0) is name 5; row 0: left block colour 5, right (5/4) = 1
    m, img, px, pl, has = screen('7', 900)
    check(f18render.mode_of(m) == f18render.MULTI and px(40, 0) == pl(5) and px(44, 0) == pl(1) and px(40, 4) == pl(6), '7: Multicolor blocks: 4 x 4 pixels, colours from the pattern bytes')
    # 8 ECM 1: pair n = entries 2n, 2n+1; row 5 is pair 3: glyph pixels are entry 7
    m, img, px, pl, has = screen('8')
    check(f18render.mode_of(m) == f18render.TEXT80 and m.vregs[49] == 0x50 and geo(m)[3] == 0xFFFF and has(16, 5 * 8, 16 + 150, 6 * 8, pl(7)) and has(16, 5 * 8, 16 + 150, 6 * 8, pl(6)),
          '8: ECM 1: VR49 = 30 rows + tile ECM 1; pair 3 draws entries 6 and 7')
    row = lambda y, x0: [px(x0 + i, y) for i in range(24)]
    check(has(16, 19 * 8, 16 + 160, 20 * 8, pl(7)), '8: the flip x row draws in pair 3 as well')
    # 9 ECM 2: tile 1 = colours 3 2 1 0 3 2 across 6 pixels; row 3 set 0, row 8 set 5 (entries 20-23)
    m, img, px, pl, has = screen('9')
    x0 = 8 + 2 * 6
    check(m.vregs[49] == 0x60 and [px(x0 + i, 3 * 8 + 1) for i in range(6)] == [pl(c) for c in (3, 2, 1, 0, 3, 2)], '9: ECM 2: the two planes give 4 colours: 3 2 1 0 3 2')
    check([px(x0 + i, 8 * 8 + 1) for i in range(6)] == [pl(20 + c) for c in (3, 2, 1, 0, 3, 2)], '9: attribute 5 picks palette set 5 (entries 20-23)')
    # 0 ECM 3 on Graphics I: gradient 7..0 across 8 pixels; set 0 on row 3, attribute 2 (entries 8-15) on row 4
    m, img, px, pl, has = screen('0')
    check(f18render.mode_of(m) == f18render.GRAPHICS and m.vregs[49] == 0x30 and [px(16 + i, 3 * 8) for i in range(8)] == [pl(7 - i) for i in range(8)], '0: ECM 3: eight colours across a tile, 7 down to 0')
    check([px(16 + i, 4 * 8) for i in range(8)] == [pl(15 - i) for i in range(8)], '0: attribute 2 picks palette entries 8-15')
    check([px(16 + i, 12 * 8) for i in range(8)] == [pl(i) for i in range(8)], '0: attribute >40 flips the tile in x')
    # A sprites
    m, img, px, pl, has = screen('a')
    check(m.vregs[51] == 32 and px(19, 43) == pl(2) and px(215, 155) == pl(9) and px(16, 40) == pl(1), 'A: sprites on (VR51 = 32): ball 0 colour 2, ball 7 colour 9')
    # B enhanced colour sprites 16 x 16
    m, img, px, pl, has = screen('b')
    check(m.vregs[49] == 0x03 and m.vregs[1] & 2 and [px(40 + i, 60) for i in range(4)] == [pl(7), pl(6), pl(5), pl(4)], 'B: ECM 3 sprites, 16 x 16: gradient 7 6 5 4 ...')
    check([px(100 + i, 60) for i in range(2)] == [pl(15), pl(14)], 'B: colour 2 picks palette entries 8-15')
    check([px(161 + i, 60) for i in range(2)] == [pl(17), pl(18)] and px(175, 60) == pl(23), 'B: flip x reverses all 16 pixels (colour set 4: entries 16-23)')
    # C tile layer 2, scrolled 3 across, 4 down; its text is pair 1's colour 1 (entry 3)
    m, img, px, pl, has = screen('c')
    check(m.vregs[49] == 0x90 and m.vregs[10] == 8 and m.vregs[25] == 3 and m.vregs[26] == 4, 'C: tile layer 2 on; VR10, VR25, VR26')
    check(px(0, 0) == pl(1) and px(1, 0) == pl(0) and has(9 * 8 - 3, 10 * 8 - 4, 18 * 8 - 3, 11 * 8 - 4 + 4, pl(3)), 'C: layer 1 checker behind, layer 2 text on top where it is not transparent')
    # D bitmap layer, 4 colours, over Graphics I: x 20, y 100; band colour = (j/4 + y/8) mod 4 from entries 12-15
    m, img, px, pl, has = screen('d', 900)
    check(m.vregs[31] == 0x83 and px(20, 100) == pl(12) and px(36, 100) == pl(13) and px(20, 108) == pl(13) and px(19, 100) == pl(1),
          'D: bitmap layer 4 colours: bands in palette entries 12-15, nothing outside its rectangle')
    # E bitmap layer, 16 colours (fat pixels) over Graphics I: colour = (x/4 + y/2) mod 16
    m, img, px, pl, has = screen('e', 900)
    check(m.vregs[31] == 0x90 and px(60, 80) == pl(0) and px(64, 80) == pl(1) and px(60, 82) == pl(1), 'E: bitmap layer 16 colours: (x/4 + y/2) mod 16')

GROUPS = [('sources', sources), ('dbg', dbg), ('native', native), ('nativemods', nativemods), ('workbench', workbench), ('workbenchfull', workbenchfull), ('boot', boot), ('refusal', refusal), ('ram', ram), ('keys', keys), ('quit', quit_), ('modules', modules),
          ('files', files), ('browser', browser), ('modes', modes), ('modesquit', modes_quit), ('music', music), ('rom', rom), ('realdsr', realdsr)]

if __name__ == '__main__':
    want = sys.argv[1:] or [g for g, _ in GROUPS]
    for name, fn in GROUPS:
        if name in want:
            print(name); fn()
    print('\n%d failed' % len(FAILS) if FAILS else '\nall passed')
    sys.exit(1 if FAILS else 0)
