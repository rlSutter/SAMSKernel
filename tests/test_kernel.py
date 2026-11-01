#!/usr/bin/env python3
"""SAMS Kernel tests: the example applications run in tools/sim9900.py.

  python3 tests/test_kernel.py [group ...]      (no names: all)

Groups: sources dbg sams16 tipi hfdccru linein resident poolmax trim editorapp sourcesdisk jumpcheck fileapi dsdd dsddworkbench editorpages reversi reversiti joystick files2 native nativemods nativedisk tiprograms workbench workbenchfull boot refusal ram keys quit modules files browser modes modesquit music rom realdsr
Builds the examples first (tools/skbuild.py; XAS99 or ./xdt99 needed).
The 'rom' group runs the real console ROM's interrupt routine when
TI_CONSOLE_ROM names your own copy of the 8K console ROM (a raw dump, or
an EA5 image); without it the group is skipped.  The ROM is TI's code and
is never part of this repository.  The 'realdsr' group runs the file service and
the disk browser against TI's own disk controller DSR (tools/tifdc.py, a WD1771 on a
disk image): it needs the controller's 8K ROM, at tools/tifdc_dsr.bin or named by
TIFDC_ROM (join the two 4K EPROM images, low half first); skipped without it.
"""
import glob, json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import sim9900, keytab

FAILS = []
def check(cond, what):
    print(('  ok   ' if cond else '  FAIL ') + what)
    if not cond: FAILS.append(what)

def build(app):
    path = os.path.join(ROOT, app) if app.startswith('tests/') else os.path.join(ROOT, 'examples', app)
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), path], capture_output=True, text=True)
    if r.returncode: sys.exit(r.stdout + r.stderr)
    return open(glob.glob(os.path.join(ROOT, 'build', os.path.basename(app), '*8.bin'))[0], 'rb').read()

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
    check(m.rw(0x21E8) == 0x12 and m.rw(0x21EA) == 0x13, 'slot C holds the boot module, pages >12 >13 (CURCC=%04X CURCD=%04X)' % (m.rw(0x21E8), m.rw(0x21EA)))

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
    check(any('FAILED ITS TEST' in l for l in lines(m)) and any('>02A' in l for l in lines(m)), 'a bad page refused and named (three digits)')
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
    m, cpu, halt = sim9900.run(c, keys='<ENTER><WAIT 45>', frames=300, setup=setup)
    check('Not a DIS/VAR' in lines(m)[27], 'ENTER on an INT/FIX file: refused')
    m, cpu, halt = sim9900.run(c, keys='<F-x><F-x><ENTER><WAIT 200>', frames=700, setup=setup)
    ln = lines(m)
    check('DSK1.README' in ln[0] and ln[2].strip() == 'line 1' and ln[27].strip() == 'line 26', 'GOMOD with an argument: README viewed, 26 lines')
    check('Line 1 of 129' in ln[29], 'the footer: %r' % ln[29][55:80])
    m, cpu, halt = sim9900.run(c, keys='<F-x><F-x><ENTER><WAIT 200><F-x><F-x><F-x>', frames=900, setup=setup)
    check(lines(m)[2].strip() == 'line 4' and 'Line 4 of 129' in lines(m)[29], 'DOWN scrolls (lines read into pool pages, drawn through MAPE)')
    m, cpu, halt = sim9900.run(c, keys='<F-x><F-x><ENTER><WAIT 200><F-9><WAIT 100>', frames=900, setup=setup)
    check('Disk browser' in lines(m)[0], 'BACK returns to the browser (PREVPG)')

def sams16():
    """SAMS cards of 512K to 16M, whose registers are 12 bits (the even byte the low 8, the odd byte bits 8-11, as in
    js99er): the kernel sizes the card, its self-test passes (paging above page 255 and the pool's last pages included),
    and FCTN = quits with the mapping off.  Cards of 128K and 1M: as before."""
    c = build('diag')
    wide = lambda m: setattr(m, 'wide_regs', True)
    for pages, setup, label in ((128, None, '128 pages'), (256, None, '1M'), (512, wide, '2M (12-bit registers)'), (4096, wide, '16M (12-bit registers)')):
        big = pages > 256                     # the page test at power-up takes longer on a big card
        m, cpu, halt = sim9900.run(c, keys='<WAIT %d><C-t><WAIT 900>' % (1500 if big else 100), frames=3500 if big else 1300, pages=pages, setup=setup)
        ln = [l.strip() for l in lines(m)[2:12] if l.strip()]
        check(halt is None and len(ln) >= 8 and all('PASS' in l for l in ln[:8]) and ln[0].endswith(str(pages)),
              '%s: the kernel finds %d pages and the self-test passes: %s' % (label, pages, ln[0] if ln else ln))
    m, cpu, halt = sim9900.run(c, keys='<WAIT 1500><F-=>', frames=2200, pages=4096, setup=wide)
    r = getattr(m, 'at_reset', None)
    check(halt is None and r is not None and not r[2], '16M: FCTN = resets the console with the mapping off (the kernel runs on to the reset): halt %s, reset %s' % (halt, r is not None))

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

def joystick():
    """Both joysticks, read as keyboard columns 6 and 7: what is down, the presses between looks, and JOYKEY, which
    types arrow keys and ENTER for a joystick with the keyboard's repeat."""
    c = build('joystick')
    b = 0x2300 + 5760
    keys = '<WAIT 5><J1-FIRE><WAIT 6><J1-FIRE><WAIT 6><J1-LEFT+UP><WAIT 6><J1-RIGHT><WAIT 6><J1-DOWN><WAIT 6><J2-FIRE><WAIT 6><J2-LEFT><WAIT 10>'
    m, cpu, halt = sim9900.run(c, keys=keys, frames=260)
    check(m.rw(b) == 2 and m.rw(b + 2) == 1, 'fire presses counted per joystick, each press once (J1 %d, J2 %d)' % (m.rw(b), m.rw(b + 2)))
    check(m.rw(b + 8) == 0x1F and m.rw(b + 10) == 0x03, 'every direction of joystick 1 was seen (%02X); joystick 2 shows only its own (%02X)' % (m.rw(b + 8), m.rw(b + 10)))
    check(m.rw(b + 6) == 0 and m.rw(0x21F4) == 0, 'with JOYKEY off a joystick types nothing (%d keys)' % m.rw(b + 6))
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5>1<WAIT 8><J1-UP><WAIT 8><J1-LEFT><WAIT 8><J1-FIRE><WAIT 10>', frames=200)
    check(m.rw(b + 6) == 3 and m.rw(b + 4) == 0x0D, 'JOYKEY 1: UP, LEFT and FIRE type three keys, the last ENTER (%d keys, last >%02X)' % (m.rw(b + 6), m.rw(b + 4)))
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5>2<WAIT 8><HOLD 70><J2-DOWN><WAIT 10>', frames=200)
    check(m.rw(b + 6) >= 10 and m.rw(b + 4) == 0xD8, 'JOYKEY 2: DOWN held 70 frames repeats like a key (%d keys, last >%02X)' % (m.rw(b + 6), m.rw(b + 4)))
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5>1<WAIT 8><J2-UP><WAIT 8><J2-FIRE><WAIT 10>', frames=200)
    check(m.rw(b + 6) == 0, 'JOYKEY 1 does not type for joystick 2 (%d keys)' % m.rw(b + 6))
    m, cpu, halt = sim9900.run(c, keys='<WAIT 5><ALPHA>ab<J1-FIRE><WAIT 10>', frames=150)
    check(m.rw(b + 6) == 2 and m.rw(b + 4) == 0x62 and m.rw(b) == 1, 'the keyboard works beside a joystick: two keys typed (last %02X) and a fire press counted' % m.rw(b + 4))
    # a program that never uses the joysticks never makes the kernel read their columns (js99er treats a read of
    # keyboard columns 6 and 7 as 'this program uses the joystick' and then stops mapping the PC's arrow keys to FCTN E S D X)
    def spy(box):
        def setup(m):
            orig = m.cru_read
            def rd(bit):
                if 3 <= bit <= 10:
                    box.add(m.keycol)
                return orig(bit)
            m.cru_read = rd
        return setup
    cols = set()
    sim9900.run(build('hello'), keys='<WAIT 5>ab<WAIT 30>', frames=150, setup=spy(cols))
    check(cols and max(cols) <= 5, 'hello (no joystick use): the kernel reads keyboard columns %s only, never 6 or 7' % sorted(cols))
    cols = set()
    sim9900.run(c, keys='<WAIT 5><WAIT 30>', frames=100, setup=spy(cols))
    check(6 in cols and 7 in cols, 'the joystick example (it calls JOYGET) makes the kernel read columns 6 and 7: %s' % sorted(cols))


def files2():
    """Three files open at once, each through its own handle (FSEL): one file copied to a second while a third is read
    alongside; every record arrives; a fourth handle is refused.  Against TI's own disk controller ROM, and the stand-in drive."""
    import tempfile, skdisk, tifdc
    c = build('tests/apps/files2')
    d = tempfile.mkdtemp()
    src = ['record %02d of the source file, copied by handle 0 to handle 1' % i for i in range(1, 31)]
    open(d + '/src', 'w').write('\n'.join(src) + '\n')
    open(d + '/src2', 'w').write(''.join('second file, record %02d\n' % i for i in range(1, 21)))
    b = 0x2300
    def results(m):
        r = lambda o: m.rw(b + o)
        return dict(opens=(r(0), r(2), r(4)), copied=r(6), alongside=r(8), lasterr=r(10), werr=r(14), fsel3=r(16), done=r(18), closes=(r(20), r(22), r(24)))
    if os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM']):
        p = d + '/d.dsk'
        skdisk.make_disk(p, [d + '/src', d + '/src2'])
        img = bytearray(open(p, 'rb').read()); box = {}
        def setup(m): box['f'] = tifdc.TIFDC(image=img); m.tifdc = box['f']
        m, cpu, halt = sim9900.run(c, frames=1500, setup=setup)
        r = results(m)
        check(r['opens'] == (0, 0, 0) and r['done'] != 0, 'TI controller: three files open at once, all three opened without error %s' % (r['opens'],))
        check(r['copied'] == 30 and r['werr'] == 0 and r['lasterr'] == 5, 'TI controller: 30 records copied from handle 0 to handle 1, then the end of file (5): %s' % r)
        check(tifdc.read_file(box['f'].image, 'DST') == tifdc.read_file(bytes(img), 'SRC'), 'TI controller: the copy is the same file, record for record')
        check(r['alongside'] == 20, 'TI controller: handle 2 read its own 20 records alongside, at its own position (%d)' % r['alongside'])
        check(r['fsel3'] == 0xFF and r['closes'][1] == 0 and all(x in (0, 7) for x in r['closes']), 'a fourth handle is refused (>FF); every close answers (a file read to its end is already closed: 7): %s' % (r['closes'],))
    else:
        print('  (TI controller part skipped: TIFDC_ROM)')
    def setup2(m):
        m.dvfiles['SRC'] = [s.encode() for s in src]
        m.dvfiles['SRC2'] = [('second file, record %02d' % i).encode() for i in range(1, 21)]
    m, cpu, halt = sim9900.run(c, frames=1500, setup=setup2)
    r = results(m)
    check(r['copied'] == 30 and r['alongside'] == 20 and r['werr'] == 0 and r['fsel3'] == 0xFF and m.dvfiles.get('DST') == [s.encode() for s in src],
          'stand-in drive: the same: 30 records copied while 20 are read alongside, a fourth handle refused: %s' % r)

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

def nativedisk():
    """What the workbench's demonstration disk holds must assemble with the workbench's own KERNEL/EQU (a source that
    needs equates only another app's build has, like examples/music's song pages, must not be on it); and beep runs."""
    import asmharness
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    for src in DISK_SOURCES:
        r = asmharness.assemble(os.path.join(ROOT, src), 'workbench')
        check(r.errors == 0, '%s assembles against the workbench\'s own KERNEL/EQU: %d bytes, errors %d %s' % (src, r.length, r.errors, [(l, c & 255) for l, c in r.errtab][:3]))
    m, img = asmharness.workbench_ui('<WAIT 10>nBEEP/A99<ENTER><WAIT 10>a<WAIT 3500>r<WAIT 80>6<WAIT 40>', 4200, [os.path.join(ROOT, 'examples/workbench/programs/beep.a99')])
    b = [x for (src, i, x) in m.chip_log if src == 'cpu']
    check(b[-3:] == [0x8E, 0x0F, 0x90], 'beep, assembled and run on the TI: key 6 plays A on voice 1 (SNDTONE: >8E >0F >90): %s' % [hex(x) for x in b[-3:]])

DISK_SOURCES = ['examples/hello/hello.a99', 'examples/workbench/programs/beep.a99', 'examples/workbench/programs/mode.a99',
                'examples/workbench/programs/copy.a99', 'examples/workbench/programs/paging.a99', 'examples/workbench/programs/clock.a99',
                'examples/joystick/joy.a99', 'examples/reversi/revers.a99',
                'examples/modes/modes.a99', 'tests/asm/probe1.a99']

def tiprograms():
    """The programs on the workbench's disk, assembled on the simulated TI and run there: the TI-side examples the
    documentation points to (mode, paging, copy, joystick)."""
    import asmharness, tifdc
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    P = os.path.join(ROOT, 'examples/workbench/programs/')
    def go(name, extra, tail, frames):
        keys = '<WAIT 10>n%s<ENTER><WAIT 10>a<WAIT 2300>r<WAIT 60>%s' % (name, tail)
        return asmharness.workbench_ui(keys, frames, extra)
    m, img = go('MODE/A99', [P + 'mode.a99'], '2<WAIT 40>', 2900)
    check(m.rw(0x20EC) == 40, 'mode: key 2 set Text 40 (%d columns)' % m.rw(0x20EC))
    m, img = go('MODE/A99', [P + 'mode.a99'], '2<WAIT 40>1<WAIT 40>', 3000)
    check(m.rw(0x20EC) == 80, 'mode: key 1 set Text 80 again (%d columns)' % m.rw(0x20EC))
    m, img = go('MODE/A99', [P + 'mode.a99'], '2<WAIT 40><F-9><WAIT 80>', 3100)
    ln = lines(m)
    check(m.rw(0x20EC) == 80 and 'workbench' in ln[0], 'mode: FCTN 9 restores Text 80 and returns to the workbench: %r' % ln[0].strip())
    m, img = go('PAGING/A99', [P + 'paging.a99'], '<ENTER><WAIT 45>', 2900)
    ln = [l.strip() for l in lines(m)[:10]]
    check('4 of 4 pages kept their own number' in ln and 'OK' in ln, 'paging: four pool pages each kept their own number, and slot B was put back: %s' % [l for l in ln if l][-2:])
    open('/tmp/src', 'w').write('first record\nsecond record\nthird\nfourth\n')
    m, img = go('COPY/A99', [P + 'copy.a99', '/tmp/src'], '<ENTER><WAIT 120>', 3000)
    check(tifdc.read_file(img, 'DST') == tifdc.read_file(img, 'SRC') and len(tifdc.read_file(img, 'DST')) == 4, 'copy: two files open at once, SRC copied to DST record for record on the TI: %s' % tifdc.read_file(img, 'DST'))
    def pi(m):
        m.pi_card = True; m.pi_clock = '3,10/29/26,14:05:09'
    m, img = asmharness.workbench_ui('<WAIT 10>nCLOCK/A99<ENTER><WAIT 10>a<WAIT 2300>r<WAIT 60><ENTER><WAIT 80>', 2900, [P + 'clock.a99'], setup2=pi)
    check('10 29 2026' in lines(m)[4] and '14 5  9' in lines(m)[4], 'clock: assembled on the TI, it reads a TIPI model\'s clock: %r' % lines(m)[4].strip())
    m, img = go('JOY/A99', [os.path.join(ROOT, 'examples/joystick/joy.a99')], '<J1-FIRE><WAIT 8><J1-FIRE><WAIT 8>', 2800)
    check(m.rw(0x2300 + 5760) == 2, 'joystick: the program assembled on the TI counts two fire presses (%d)' % m.rw(0x2300 + 5760))
    m, img = go('ASK/A99', [P + 'ask.a99', os.path.join(ROOT, 'lib', 'linein.a99')], 'ann<ENTER><WAIT 40>bob<ENTER><WAIT 40><F-E><WAIT 40>', 3300)
    ln = lines(m)
    check('Hello, BOB' in ln[8] and ln[5].strip().endswith('BOB'),
          'ask: assembled on the TI with LINEIN/A99 included from its disk, LINEIN reads two names, greets them, and UP brings the last one back into the field: %r, %r' % (ln[8].strip(), ln[5].strip()))

DISK_SOURCES_PLACEHOLDER = None

def tipi():
    """Support for a TIPI, as far as a simulator can show it (a MODEL of a TIPI on a second card at CRU >1000, not its
    DSR): the TI controller is powered up whichever device is used first and the TIPI is not (its power-up only resets the Pi); a file on the TIPI is copied to a TI controller's
    disk with the TIPI used first; the clock (CLKGET); and the workbench's includes in the main file's directory."""
    import tempfile, skdisk, tifdc, asmharness
    c = build('tests/apps/tipi')
    b = 0x2300
    src = [b'record %02d from the TIPI' % i for i in range(1, 13)]
    if os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM']):
        d = tempfile.mkdtemp(); p = d + '/d.dsk'; skdisk.make_disk(p, [])
        img = bytearray(open(p, 'rb').read()); box = {}
        def setup(m):
            box['f'] = tifdc.TIFDC(image=img); m.tifdc = box['f']
            m.pi_card = True; m.pi_files = True; m.dvfiles['PI:IN.SRC'] = src; m.pi_clock = '3,10/29/26,14:05:09'
        m, cpu, halt = sim9900.run(c, frames=1500, setup=setup)
        check(not m.pi_powered and m.rw(b) == 0 and m.rw(b + 2) == 0 and m.rw(b + 4) == 12 and m.rw(b + 6) == 5 and m.rw(b + 8) == 0,
              'two cards: the TIPI model was NOT powered up (a real TIPI\'s power-up pulses the Pi\'s reset), a file on it opened first, then the TI controller\'s: 12 records copied (%d), end of file (%d)' % (m.rw(b + 4), m.rw(b + 6)))
        check(tifdc.read_file(box['f'].image, 'DST') == src, 'two cards: the copy on the TI controller\'s disk is the TIPI file, record for record')
        def setup2(m):
            f = tifdc.TIFDC(image=bytearray(open(p, 'rb').read())); orig = f.read; m.tifdc = f
            f.read = lambda a: 0 if a in (0x4004, 0x4005) else orig(a)      # the controller's power-up not run
            m.pi_card = True; m.pi_files = True; m.dvfiles['PI:IN.SRC'] = src
        m, cpu, halt = sim9900.run(c, frames=1500, setup=setup2)
        check(m.rw(b + 4) != 12, 'and the test means something: without the controller\'s power-up the copy does not happen (%d records)' % m.rw(b + 4))
    else:
        print('  (two-card copy skipped: TIFDC_ROM)')
    def clk(m):
        m.pi_card = True; m.pi_files = True; m.dvfiles['PI:IN.SRC'] = src; m.pi_clock = '3,10/29/26,14:05:09'
    m, cpu, halt = sim9900.run(c, frames=1500, setup=clk)
    words = [m.rw(0x20C0 + 2 * i) for i in range(7)]
    check(m.rw(b + 14) == 0 and words == [3, 10, 29, 26, 14, 5, 9], 'CLKGET: "3,10/29/26,14:05:09" gives DOW 3, 10/29/26, 14:05:09: %s' % words)
    def noclk(m):
        m.pi_card = True; m.pi_files = True; m.dvfiles['PI:IN.SRC'] = src; m.pi_clock = None
    m, cpu, halt = sim9900.run(c, frames=1500, setup=noclk)
    words = [m.rw(0x20C0 + 2 * i) for i in range(7)]
    check(m.rw(b + 14) != 0 and words == [0] * 7, 'CLKGET without a clock: an error (%d) and the words are 0' % m.rw(b + 14))
    # includes: in the main file's directory first, then on the device alone
    prog = ['       COPY "kernel.equ"', '       COPY "macros.a99"', '       COPY "inc.a99"', '       AORG >C000', '       DATA INIT,TICK,INIT,0',
            'INIT   LI   R0,VAL', '       RT', 'TICK   RT']
    inc = ['VAL    EQU  >1234']
    r = asmharness.assemble_standin({'SUB.MAIN/A99': prog, 'SUB.INC/A99': inc}, 'SUB.MAIN/A99')
    check(r.errors == 0 and b'\x12\x34' in r.image,
          'includes: inc.a99 is found beside DSK1.SUB.MAIN/A99 (SUB.INC/A99) and KERNEL/EQU on the device alone: errors %d' % r.errors)
    r = asmharness.assemble_standin({'SUB.MAIN/A99': prog, 'INC/A99': inc}, 'SUB.MAIN/A99')
    check(r.errors == 0 and b'\x12\x34' in r.image, 'includes: not beside it, the device\'s own directory has it (INC/A99): errors %d' % r.errors)
    r = asmharness.assemble_standin({'SUB.MAIN/A99': prog}, 'SUB.MAIN/A99')
    check(r.errors >= 1 and any((c & 255) == 7 for l, c in r.errtab), 'includes: nowhere: a file error, with its line: %s' % [(l, c & 255) for l, c in r.errtab][:3])

def reversi():
    """examples/reversi: the rules, the computer's two levels and the pass logic checked against a Python model
    (tests/reversi_model.py): thousands of cell checks on positions from random games, every move of whole games
    played through the keyboard, the joystick, hints and levels, and save and open through the file service."""
    import random, asmharness
    sys.path.insert(0, os.path.join(ROOT, 'tests'))
    import reversi_model as R
    c = build('reversi')
    B = 0x2300 + 5760
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'reversi', 'game.equ'))
    m = sim9900.Machine(c)
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m)
    cpu.pc = m.rw(m.rw(0x6006) + 2)
    while m.insns < 100 * sim9900.VSYNC_INSNS:
        cpu.step()
    def put(b):
        for i in range(100): m.wb(B + i, 3)
        for r in range(8):
            for c2 in range(8): m.wb(B + (r + 1) * 10 + c2 + 1, b[r * 8 + c2])
    def get(mm):
        return [mm.rb(B + (r + 1) * 10 + c2 + 1) for r in range(8) for c2 in range(8)]
    random.seed(1)
    cells = bad = moves = 0
    for g in range(20):
        b, p = R.start(), 1
        for ply in range(70):
            mv = R.legal(b, p)
            if not mv:
                p = 3 - p; mv = R.legal(b, p)
                if not mv: break
            put(b)
            for cell in range(64):
                m.ww(B + 108, 0)
                r = asmharness.call(m, cpu, syms['padix'], {0: cell})
                cells += 1
                if asmharness.call(m, cpu, syms['flipn'], {0: r[0], 1: p})[0] != len(R.flips(b, cell, p)): bad += 1
            cell = random.choice(mv)
            put(b); m.ww(B + 108, 0xFFFF)
            r = asmharness.call(m, cpu, syms['padix'], {0: cell}); asmharness.call(m, cpu, syms['flipn'], {0: r[0], 1: p})
            nb = R.play(b, cell, p)
            moves += 1
            if get(m) != nb: bad += 1
            b, p = nb, 3 - p
    check(bad == 0, 'rules: %d cells and %d moves in 20 random games: the legal-move scan and the flips agree with the model (%d differ)' % (cells, moves, bad))
    random.seed(7)
    n = bad = 0
    for g in range(12):
        b, p = R.start(), 1
        for ply in range(70):
            mv = R.legal(b, p)
            if not mv:
                p = 3 - p; mv = R.legal(b, p)
                if not mv: break
            put(b)
            for pl in (1, 2):
                n += 1
                if asmharness.call(m, cpu, syms['hasmv'], {1: pl})[0] != (1 if R.legal(b, pl) else 0): bad += 1
            if p == 2:
                m.ww(B + 104, 2)
                got = asmharness.call(m, cpu, syms['aimove'])[0]
                got = got - 65536 if got >= 32768 else got
                n += 1
                if got != R.greedy(b, 2): bad += 1
                m.ww(B + 104, 1); m.ww(B + 118, random.randrange(65536))
                n += 1
                if asmharness.call(m, cpu, syms['aimove'])[0] not in R.legal(b, 2): bad += 1
            b = R.play(b, random.choice(mv), p); p = 3 - p
    check(bad == 0, 'computer: level 2 picks the model\'s greedy move, level 1 always a legal one, and "has a move" agrees (%d checks, %d differ)' % (n, bad))
    # whole games through the keyboard: the first legal move each time
    def script(policy, limit=99):
        b, cur, keys, humans = R.start(), 19, '<WAIT 5>', 0
        while humans < limit:
            mv = R.legal(b, 1)
            if not mv:
                while not R.legal(b, 1):
                    cm = R.greedy(b, 2)
                    if cm is None: return keys, b, cur
                    b = R.play(b, cm, 2)
                continue
            cell = policy(mv)
            r0, c0 = divmod(cur, 8); r1, c1 = divmod(cell, 8)
            keys += ('<F-x>' if r1 > r0 else '<F-e>') * abs(r1 - r0) + ('<F-d>' if c1 > c0 else '<F-s>') * abs(c1 - c0) + '<ENTER><WAIT 45>'
            cur, humans = cell, humans + 1
            b = R.play(b, cell, 1)
            if R.legal(b, 2): b = R.play(b, R.greedy(b, 2), 2)
            elif not R.legal(b, 1): return keys, b, cur
            if not R.legal(b, 1) and not R.legal(b, 2): return keys, b, cur
        return keys, b, cur
    keys, b, cur = script(lambda mv: mv[0])
    mm, cpu2, halt = sim9900.run(c, keys=keys + '<WAIT 150>', frames=9500)
    text = ' '.join(lines(mm))
    want = 'You win!' if R.score(b)[0] > R.score(b)[1] else ('The computer wins' if R.score(b)[0] < R.score(b)[1] else 'A draw')
    check(get(mm) == b and (mm.rw(B + 110), mm.rw(B + 112)) == R.score(b) and mm.rw(B + 114) != 0 and want in text,
          'a whole game by keyboard, %d of your moves: every board equals the model\'s, the scores %s, game over, "%s" on screen' % (keys.count('<ENTER>'), R.score(b), want))
    random.seed(5)
    keys, b, cur = script(lambda mv: random.choice(mv), 12)
    mm, cpu2, halt = sim9900.run(c, keys=keys + '<WAIT 120>', frames=4500)
    check(get(mm) == b and (mm.rw(B + 110), mm.rw(B + 112)) == R.score(b) and mm.rw(B + 102) == cur, '12 random moves of yours by keyboard: the board, the scores and the cursor equal the model\'s')
    # an illegal move, hints, level
    mm, cpu2, halt = sim9900.run(c, keys='<WAIT 5><F-e><F-e><F-s><F-s><F-s><ENTER><WAIT 10>', frames=300)
    check(get(mm) == R.start() and 'not a legal move' in ' '.join(lines(mm)), 'an illegal move (a1) changes nothing and says so')
    mm, cpu2, halt = sim9900.run(c, keys='<WAIT 5>h<WAIT 8>l<WAIT 8>', frames=200)
    check(mm.rw(B + 106) != 0 and mm.rw(B + 104) == 1 and 'Level 1' in ' '.join(lines(mm)) and 'Hints: on' in ' '.join(lines(mm)), 'H turns the hints on, L switches to level 1')
    # the joystick: right and down, then fire
    mm, cpu2, halt = sim9900.run(c, keys='<WAIT 5><J1-FIRE><WAIT 70>', frames=250)
    b1 = R.play(R.start(), 19, 1)
    b1 = R.play(b1, R.greedy(b1, 2), 2)
    check(get(mm) == b1, 'the joystick\'s fire button plays d3 (JOYKEY types ENTER for it) and the computer answers like the model')
    mm, cpu2, halt = sim9900.run(c, keys='<WAIT 5><J1-LEFT><WAIT 8><J1-DOWN><WAIT 8>', frames=150)
    check(mm.rw(B + 102) == 19 - 1 + 8, 'the joystick moves the cursor: left, then down (cell %d)' % mm.rw(B + 102))
    # save and open
    def setup(mm):
        pass
    keys = '<WAIT 5><ENTER><WAIT 70>s<WAIT 30>n<WAIT 20>o<WAIT 30>'
    mm, cpu2, halt = sim9900.run(c, keys=keys, frames=700)
    sg = R.play(R.start(), 19, 1); sg = R.play(sg, R.greedy(sg, 2), 2)
    rec = mm.dvfiles.get('REVERSI')
    want = (''.join(str(x) for x in sg) + '12').encode()
    check(rec == [want] and get(mm) == sg and mm.rw(B + 100) == 1, 'S saves the game as one 66-character record, N starts again, O opens it: the position is back (%s)' % (rec[0][:20] if rec else rec))
    mm, cpu2, halt = sim9900.run(c, keys='<WAIT 5>o<WAIT 20>', frames=200)
    check('No saved game' in ' '.join(lines(mm)), 'O with no saved game says so')

def reversiti():
    """Reversi assembled on the simulated TI by the workbench's native assembler (it is one module of under 4,096
    bytes): identical to xas99's, and the program that results plays."""
    import asmharness
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    src = os.path.join(ROOT, 'examples', 'reversi', 'revers.a99')
    build('reversi')
    want = open(os.path.join(ROOT, 'build', 'reversi', 'game.bin'), 'rb').read()
    r = asmharness.assemble(src, 'workbench')
    check(r.errors == 0 and r.image == want, 'reversi assembled on the TI: %d bytes (limit 4096), byte for byte as xas99 (errors %d)' % (len(want), r.errors))
    m, img = asmharness.workbench_ui('<WAIT 10>nREVERS/A99<ENTER><WAIT 10>a<WAIT 5200>r<WAIT 80><ENTER><WAIT 90>', 5600, [src])
    B = 0x2300 + 5760
    sys.path.insert(0, os.path.join(ROOT, 'tests'))
    import reversi_model as R
    b1 = R.play(R.start(), 19, 1)
    b1 = R.play(b1, R.greedy(b1, 2), 2)
    got = [m.rb(B + (r_ + 1) * 10 + c2 + 1) for r_ in range(8) for c2 in range(8)]
    check(got == b1, 'run from the workbench on the TI: ENTER plays d3 and the computer answers like the model')

def editorpages():
    """The editor keeps its lines in SAMS pages taken from the pool as the file grows (examples/workbench/ed.a99,
    guide appendix B): a file of 1,500 lines is held in 30 pool pages and the order table's page, edited and saved
    whole; a file over the limit of 2,040 lines is loaded in part, said so, and cannot be saved over the original;
    the shell will not run a program over unsaved edits."""
    import asmharness, tifdc
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    big = ['line %04d of the big file: the quick brown fox' % i for i in range(1, 1101)]
    open('/tmp/big.txt', 'w').write('\n'.join(big) + '\n')
    m, img = asmharness.workbench_ui('<WAIT 10>nBIG/TXT<ENTER><WAIT 10>e<WAIT 2300>', 2400, ['/tmp/big.txt'])
    lines = asmharness.editor_lines(m)
    npg, ordpg = m.rw(0x2300 + 196), m.rw(0x2300 + 198)
    pages = [m.rw(0x2300 + 744 + 2 * i) for i in range(npg)]
    check(lines == big and npg == 22, 'a 1,100-line file is in the buffer, line for line, in %d pool pages (%d lines)' % (npg, len(lines)))
    check(len(set(pages + [ordpg])) == 23 and min(pages + [ordpg]) >= 0x18 + 4, 'the 22 text pages and the table\'s page are distinct pool pages, none of the workbench\'s own (%s...)' % pages[:3])
    # edit the first line of a 600-line file and save: the file on the disk is the original with that change
    mid = big[:600]
    open('/tmp/mid.txt', 'w').write('\n'.join(mid) + '\n')
    keys = '<WAIT 10>nMID/TXT<ENTER><WAIT 10>e<WAIT 1300>XY<C-s><WAIT 2500>'
    m, img = asmharness.workbench_ui(keys, 4000, ['/tmp/mid.txt'])
    got = tifdc.read_file(img, 'MID/TXT')
    want = [b'XY' + mid[0].encode()] + [x.encode() for x in mid[1:]]
    check(got == want, 'XY typed on line 1 of 600 lines (12 pool pages) and CTRL S: the file on the disk has 600 lines, the first changed (%d lines)' % len(got))
    # a file past the limit
    huge = ['row %04d' % i for i in range(1, 2101)]
    open('/tmp/huge.txt', 'w').write('\n'.join(huge) + '\n')
    m, img = asmharness.workbench_ui('<WAIT 10>nHUGE/TXT<ENTER><WAIT 10>e<WAIT 3400>', 3500, ['/tmp/huge.txt'])
    check(m.rw(0x2300 + 234) != 0 and m.rw(0x2300 + 128) == 2040, 'a 2,100-line file: %d lines loaded, marked as cut' % m.rw(0x2300 + 128))
    check('only part is loaded' in ' '.join(sim9900.screen(m).split('\n')), 'and the screen says only part of it is loaded')
    m, img = asmharness.workbench_ui('<WAIT 10>nHUGE/TXT<ENTER><WAIT 10>e<WAIT 3400>Z<C-s><WAIT 100>', 3700, ['/tmp/huge.txt'])
    check(tifdc.read_file(img, 'HUGE/TXT') == [x.encode() for x in huge] and 'could not be written' in ' '.join(sim9900.screen(m).split('\n')), 'CTRL S then refuses: the 2,100 lines on the disk are as they were, and it says so')
    # unsaved edits: the shell will not run a program over them
    prog = ['       AORG >C000', '       DATA INIT,TICK,INIT,0', 'INIT   RT', 'TICK   RT']
    keys = '<WAIT 10>nNEW2<ENTER><WAIT 10>e<WAIT 300>' + '<ENTER>'.join(prog) + '<WAIT 30><C-a><WAIT 2700>e<WAIT 60>X<WAIT 5><C-x><WAIT 5><C-x><WAIT 30>r<WAIT 60>'
    m, img = asmharness.workbench_ui(keys, 5000, [])
    check('unsaved changes: E, CTRL S' in ' '.join(sim9900.screen(m).split('\n')), 'R with unsaved edits in the editor does not run: it says to save first')

def _fileapi(label, geometry, make_card):
    """The kernel's newer file and screen routines, called one at a time on a booted machine: records addressed by
    number in a RELATIVE file through TI's real disk controller ROM (FRREAD, FRWRITE), the catalog (FCATOP, FCATNX), FEXIST,
    DECD (32-bit decimals), YESNO and PRESSK."""
    import random, subprocess, tempfile, asmharness, skdisk, tifdc
    def chk(cond, msg):
        check(cond, '[%s] %s' % (label, msg))
    c = build('hello')
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'hello', 'kernel.equ'))
    def boot(img=None, keys='', cart=None):
        m = sim9900.Machine(cart or c)
        if img is not None:
            m.tifdc = make_card(img)
        m.presses, m.toggles, end = sim9900.schedule(sim9900.parse_keys(keys))
        cpu = sim9900.CPU(m)
        cpu.pc = m.rw(m.rw(0x6006) + 2)
        while m.insns < 100 * sim9900.VSYNC_INSNS:
            cpu.step()
        return m, cpu
    def call(m, cpu, name, regs=None, limit=300_000_000):   # a call that never returns is caught by this; the HFDC DSR needs tens of millions for a catalog scan
        return asmharness.call(m, cpu, syms[name.lower()], regs or {}, limit=limit)
    def put(m, addr, data):
        for i, b in enumerate(data):
            m.wb(addr + i, b)
    def lp(s):
        return bytes([len(s)]) + s.encode()
    W = 0x2300 + 5000                       # scratch in APPRAM for names and buffers
    # --- DECD ---
    m, cpu = boot()
    random.seed(4)
    cases = [(0, 0, 0), (9, 0, 0), (10, 0, 0), (65535, 0, 0), (0, 1, 0), (0xFFFF, 0xFFFF, 0), (1, 0, 8), (12345, 0, 11), (0x3B9A, 0xCA00, 0)]
    cases += [(random.randrange(65536), random.randrange(65536), random.choice([0, 5, 10, 11])) for _ in range(40)]
    bad = 0
    for lo, hi, width in cases:
        pos = 10 * 80
        for i in range(80): m.vram[pos + i] = 32
        r = call(m, cpu, 'DECD', {0: pos, 1: hi, 2: lo, 3: 0x2100, 4: width})
        n = hi << 16 | lo
        want = str(n).rjust(width)
        got = bytes(m.vram[pos:pos + len(want)]).decode('latin-1')
        if got != want or r[3] != len(want) or m.vram[pos + len(want)] != 32:
            bad += 1
            print('   DECD', n, width, repr(got), repr(want), r[3])
    chk(bad == 0, 'DECD: %d 32-bit numbers (0, 9, 10, 65535, 65536, 4294967295, random), with and without a width, all print right' % len(cases))
    # --- YESNO, PRESSK (keys already in the buffer) ---
    def feed(m, keys):
        for i, k in enumerate(keys): m.wb(0x2040 + i, k)
        m.ww(0x200E, len(keys)); m.ww(0x2010, 0)
    results = []
    for key, want in ((ord('y'), 1), (ord('Y'), 1), (ord('n'), 0), (0xF9, 0)):
        m, cpu = boot()
        put(m, W, lp('Overwrite it?'))
        feed(m, [ord('x'), ord('1'), key])      # two other keys are ignored first
        r = call(m, cpu, 'YESNO', {0: 20 * 80 + 2, 1: W, 2: 0x2100})
        text = bytes(m.vram[20 * 80 + 2:20 * 80 + 2 + 19]).decode('latin-1')
        results.append((r[0] == want, text == 'Overwrite it? (Y/N)'))
    chk(all(a and b for a, b in results), 'YESNO: Y and y give 1, N and BACK give 0, other keys are ignored, and the prompt reads "Overwrite it? (Y/N)": %s' % results)
    m, cpu = boot()
    put(m, W, lp('Press a key'))
    feed(m, [ord('q')])
    r = call(m, cpu, 'PRESSK', {0: 22 * 80, 1: W, 2: 0x2100})
    chk(r[0] == 0x7100 and bytes(m.vram[22 * 80:22 * 80 + 11]) == b'Press a key', 'PRESSK writes the prompt and returns the key (>%04X)' % r[0])
    # --- files, through TI's real controller ROM ---
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (the file checks need TIFDC_ROM)')
        return
    d = tempfile.mkdtemp()
    for name, n in (('alpha.txt', 3), ('beta.a99', 12), ('gamma.txt', 40)):
        open(d + '/' + name, 'w').write(''.join('line %d of %s\n' % (i, name) for i in range(n)))
    p = d + '/d.dsk'
    skdisk.make_disk(p, [d + '/alpha.txt', d + '/beta.a99', d + '/gamma.txt'], None, 'FILEAPI', geometry)
    img = bytearray(open(p, 'rb').read())
    listing = subprocess.run([sys.executable, os.path.join(os.environ['XAS99'].rsplit('/', 1)[0], 'xdm99.py'), p], capture_output=True, text=True).stdout.split('\n')
    want = {}
    for l in listing[2:]:
        f = l.split()
        if len(f) >= 4 and f[2].startswith('DIS'):
            want[f[0]] = (2 if 'VAR' in f[2] else 1, int(f[1]), int(f[3]))
    m, cpu = boot(img)
    REC, ENT = W + 100, W + 200
    put(m, W, lp('DSK1.'))
    r = call(m, cpu, 'FCATOP', {1: REC, 2: W})
    chk(r[0] == 0, 'FCATOP opens the catalog of DSK1 (error %d)' % r[0])
    got, guard = {}, 0
    while guard < 20:
        r = call(m, cpu, 'FCATNX', {1: REC, 2: ENT})
        if r[0] != 0:
            break
        nm = bytes(m.rb(ENT + 1 + i) for i in range(m.rb(ENT))).decode()
        got[nm] = (m.rw(ENT + 12), m.rw(ENT + 14), m.rw(ENT + 16))
        guard += 1
    chk(r[0] == 0xFE and got == want and len(got) == 3, 'FCATNX returns each file with its type, sectors and record length, then FCEND: %s' % got)
    res = {}
    for nm in ('DSK1.' + k for k in want):
        put(m, W, lp(nm)); res[nm] = call(m, cpu, 'FEXIST', {2: W})[0]
    for nm in ('DSK1.NOSUCH', 'DSK1.ALPHA/TX', 'DSK1.BETA/A9'):
        put(m, W, lp(nm)); res[nm] = call(m, cpu, 'FEXIST', {2: W})[0]
    for nm in ('XYZ9.FILE', 'NODOT'):
        put(m, W, lp(nm)); res[nm] = call(m, cpu, 'FEXIST', {2: W})[0]
    ok = all(res['DSK1.' + k] == 0 for k in want)
    chk(ok and res['DSK1.NOSUCH'] == 7 and res['DSK1.ALPHA/TX'] == 7 and res['DSK1.BETA/A9'] == 7 and res['XYZ9.FILE'] == 0xFF and res['NODOT'] == 0xFF,
          'FEXIST: every file on the disk exists, a missing one answers 7 (a shorter name too), a bad device or no device >FF: %s' % res)
    # the same through the catalog (FEXCAT), for a device that does not answer STATUS
    res2 = {}
    for nm in ['DSK1.' + k for k in want] + ['DSK1.NOSUCH', 'DSK1.ALPHA/TX', 'XYZ9.FILE', 'NODOT']:
        put(m, W, lp(nm)); res2[nm] = call(m, cpu, 'FEXCAT', {2: W})[0]
    chk(all(res[k] == v for k, v in res2.items()), 'FEXCAT (the catalog scan) gives the same answers as FEXIST (STATUS) for every name above: %s' % {k: (res[k], v) for k, v in res2.items() if res.get(k) != v})
    # why not just open it?  TI's controller answers 2 for a missing file in every mode, and for a file of the wrong kind
    def opn(name, flags, rl):
        put(m, W, lp(name)); call(m, cpu, 'FSEL', {0: 0})
        r = call(m, cpu, 'FOPEN', {0: flags, 1: rl, 2: W})[0]; call(m, cpu, 'FCLOSE'); return r
    miss = [opn('DSK1.NOSUCH', f, rl) for f, rl in ((0x1400, 80), (0x0500, 32), (0x0400, 32), (0x1C00, 80))]
    wrong = opn('DSK1.ALPHA/TXT', 0x0500, 32)
    want_miss = 7 if 'Myarc' in label else 2        # the Myarc DSR answers 7 for a missing file; TI's and the CorComp's answer 2
    chk(miss == [want_miss] * 4 and wrong == 2, 'opening a missing file answers %d in every mode tried (%s) and a file of the wrong kind 2 (%d): the cards differ, so FEXIST asks STATUS, which they all answer alike' % (want_miss, miss, wrong))
    # relative records: write records out of order, read them back by number
    put(m, W, lp('DSK1.RELFILE'))
    call(m, cpu, 'FSEL', {0: 0})
    r = call(m, cpu, 'FOPEN', {0: 0x0200 | 0x0100, 1: 32, 2: W})     # FOUT + FREL: fixed records of 32
    opened = r[0]
    chk(opened == 0, 'FOPEN of a new RELATIVE file (FOUT+FREL, fixed records of 32): error %d' % opened)
    order = [5, 2, 9, 0, 7]
    errs = 0
    for k in order:
        put(m, REC, ('record %d' % k).ljust(32).encode())
        errs += call(m, cpu, 'FRWRITE', {1: REC, 2: 32, 3: k})[0]
    call(m, cpu, 'FCLOSE')
    chk(errs == 0, 'FRWRITE puts records 5, 2, 9, 0 and 7 in that order without error')
    put(m, W, lp('DSK1.RELFILE'))
    r = call(m, cpu, 'FOPEN', {0: 0x0400 | 0x0100, 1: 32, 2: W})
    back = {}
    for k in sorted(order, reverse=True):
        for i in range(32): m.wb(REC + i, 0)
        rr = call(m, cpu, 'FRREAD', {1: REC, 3: k})
        back[k] = (rr[0], bytes(m.rb(REC + i) for i in range(32)).decode('latin-1').rstrip())
    call(m, cpu, 'FCLOSE')
    chk(r[0] == 0 and all(v == (0, 'record %d' % k) for k, v in back.items()), 'FRREAD reads them back by number, in a different order (9, 7, 5, 2, 0): %s' % back)
    put(m, W, lp('DSK1.RELFILE'))
    call(m, cpu, 'FOPEN', {0: 0x0400 | 0x0100, 1: 32, 2: W})
    rr = call(m, cpu, 'FRREAD', {1: REC, 3: 100})
    call(m, cpu, 'FCLOSE')
    chk(rr[0] != 0, 'a record far past the end is an error (%d), not silent garbage' % rr[0])
    put(m, W, lp('DSK1.RELFILE'))
    chk(call(m, cpu, 'FEXIST', {2: W})[0] == 0, 'FEXIST sees the relative file, whatever kind it is')

    # FSYNC
    def disk(name):
        try:
            return tifdc.read_file(m.tifdc.image, name)
        except Exception:
            return None
    m, cpu = boot(bytearray(open(p, 'rb').read()))
    put(m, W, lp('DSK1.SYNC')); call(m, cpu, 'FSEL', {0: 0})
    chk(call(m, cpu, 'FOPEN', {0: 0x0200 | 0x1000, 1: 80, 2: W})[0] == 0, 'FSYNC: a new DIS/VAR 80 file opened for output')
    recs = [('record %d of the synced file' % i).encode() for i in range(1, 6)]
    for r_ in recs[:3]:
        put(m, REC, r_); call(m, cpu, 'FWRITE', {1: REC, 2: len(r_)})
    before = disk('SYNC')
    r = call(m, cpu, 'FSYNC')[0]
    after = disk('SYNC')
    chk(r == 0 and after == recs[:3] and before != recs[:3], 'FSYNC makes the three records written so far safe on the disk while the file stays open (before: %s; after: %s)' % (before, [x.decode()[:8] for x in after or []]))
    for r_ in recs[3:]:
        put(m, REC, r_); call(m, cpu, 'FWRITE', {1: REC, 2: len(r_)})
    r2 = call(m, cpu, 'FSYNC')[0]
    mid = disk('SYNC')
    call(m, cpu, 'FCLOSE')
    chk(r2 == 0 and mid == recs and disk('SYNC') == recs, 'writing goes on at the end after FSYNC: five records in order, safe after the second FSYNC and after the close')
    put(m, W, lp('DSK1.RSYNC')); call(m, cpu, 'FSEL', {0: 0})
    call(m, cpu, 'FOPEN', {0: 0x0300, 1: 32, 2: W})
    errs = 0
    for k in (0, 1):
        put(m, REC, ('rel %d' % k).ljust(32).encode()); errs += call(m, cpu, 'FRWRITE', {1: REC, 2: 32, 3: k})[0]
    errs += call(m, cpu, 'FSYNC')[0]
    for k in (2, 3):
        put(m, REC, ('rel %d' % k).ljust(32).encode()); errs += call(m, cpu, 'FRWRITE', {1: REC, 2: 32, 3: k})[0]
    errs += call(m, cpu, 'FSYNC')[0]
    call(m, cpu, 'FCLOSE')
    put(m, W, lp('DSK1.RSYNC')); call(m, cpu, 'FOPEN', {0: 0x0500, 1: 32, 2: W})
    got = []
    for k in range(4):
        call(m, cpu, 'FRREAD', {1: REC, 3: k}); got.append(bytes(m.rb(REC + i) for i in range(32)).decode().rstrip())
    call(m, cpu, 'FCLOSE')
    chk(errs == 0 and got == ['rel %d' % k for k in range(4)], 'FSYNC on a RELATIVE file (reopened for update): four records written across two syncs read back (errors %d, %s)' % (errs, got))
    put(m, W, lp('DSK1.ALPHA/TXT')); call(m, cpu, 'FOPEN', {0: 0x1400, 1: 80, 2: W})
    call(m, cpu, 'FREAD', {1: REC}); one = bytes(m.rb(REC + i) for i in range(19)).decode()
    rs = call(m, cpu, 'FSYNC')[0]
    call(m, cpu, 'FREAD', {1: REC}); two = bytes(m.rb(REC + i) for i in range(19)).decode()
    call(m, cpu, 'FCLOSE')
    chk(rs == 0 and one == 'line 0 of alpha.txt' and two == 'line 1 of alpha.txt', 'FSYNC on an INPUT file does nothing and the place is kept (%r then %r)' % (one, two))
    put(m, W, lp('DSK1.ALPHA/TXT')); call(m, cpu, 'FOPEN', {0: 0x1000, 1: 80, 2: W})
    rs = call(m, cpu, 'FSYNC')[0]
    call(m, cpu, 'FREAD', {1: REC}); first = bytes(m.rb(REC + i) for i in range(19)).decode()
    call(m, cpu, 'FCLOSE')
    chk(rs == 0xFD and first == 'line 0 of alpha.txt', 'FSYNC on a sequential UPDATE file answers FNOPL (%d) and leaves it open as it was (next record %r)' % (rs, first))

    # keys and music during file calls: the kernel polls after every DSR call (FCALL calls KIDLE)
    def read_all(m, cpu, name):
        put(m, W, lp(name)); call(m, cpu, 'FSEL', {0: 0})
        call(m, cpu, 'FOPEN', {0: 0x1400, 1: 80, 2: W})
        n = 0
        while call(m, cpu, 'FREAD', {1: REC})[0] == 0:
            n += 1
        call(m, cpu, 'FCLOSE')
        return n
    m, cpu = boot(bytearray(open(p, 'rb').read()), keys='<WAIT 50>q')      # a tap at frame 110, over in 4 frames
    n = read_all(m, cpu, 'DSK1.GAMMA/TXT')
    chk(n == 40 and m.rw(0x200E) == 1 and m.rb(0x2040) == 0x51, 'a key tapped while 40 records are being read is in the key buffer afterwards (%d records, buffer %d, code >%02X)' % (n, m.rw(0x200E), m.rb(0x2040)))
    cm = build('music')
    msyms = asmharness.symbols(os.path.join(ROOT, 'build', 'music', 'kernel.equ'))
    m = sim9900.Machine(cm); m.tifdc = make_card(bytearray(open(p, 'rb').read()))
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m); cpu.pc = m.rw(m.rw(0x6006) + 2)
    while m.insns < 100 * sim9900.VSYNC_INSNS:
        cpu.step()
    asmharness.call(m, cpu, msyms['muplay'], {0: msyms['pd_tune']})
    w0 = len(m.cpu_sound)
    syms_save = syms
    syms = msyms
    n = read_all(m, cpu, 'DSK1.GAMMA/TXT')
    syms = syms_save
    chk(n == 40 and len(m.cpu_sound) - w0 >= 10, 'the music plays on while files are read: the song wrote %d bytes to the sound chip during 40 reads' % (len(m.cpu_sound) - w0))

def fileapi():
    """The routines above on each disk controller the simulator has: TI's own (a 90K single-density disk)
    and the CorComp card (a 360K double-sided double-density disk), each through its own real DSR ROM."""
    cards = [('TI SSSD', 'sssd', lambda img: __import__('tifdc').TIFDC(image=img))]
    if __import__('ccfdc').available():
        cards.append(('CorComp DSDD', 'dsdd', lambda img: __import__('ccfdc').CCFDC(image=img)))
    else:
        print('  (the CorComp card is skipped: its ROMs are not found; CCFDC_U3, CCFDC_U4)')
    if __import__('myfdc').available():
        cards.append(('Myarc DDCC-1 DSDD', 'dsdd', lambda img: __import__('myfdc').MYFDC(image=img)))
    if __import__('hfdc').available():
        cards.append(('Myarc HFDC DSDD', 'dsdd', lambda img: __import__('hfdc').HFDC(image=img)))
    only = os.environ.get('TESTCARDS')
    if only:                                   # e.g. TESTCARDS=HFDC: just the cards whose label has one of these words
        cards = [c for c in cards if any(w in c[0] for w in only.split(','))]
    for label, geometry, make_card in cards:
        _fileapi(label, geometry, make_card)


def _dsdd(label, make_card):
    """A double-sided double-density disk through the CorComp card's real DSR ROM (tools/ccfdc.py, tools/fdc.py): a file
    that lies on the disk's second side (a filler of about 250K pushes it past sector 720) is read, a new file written
    there is on the disk record for record, and the free-sector count the catalog gives is the disk's, not a 90K disk's."""
    import tempfile, asmharness, skdisk, tifdc
    def chk(cond, msg):
        check(cond, '[%s] %s' % (label, msg))
    c = build('hello')
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'hello', 'kernel.equ'))
    d = tempfile.mkdtemp()
    open(d + '/filler.txt', 'w').write(''.join(('filler %05d ' % i).ljust(79, 'x') + '\n' for i in range(2300)))
    open(d + '/target.txt', 'w').write(''.join('target line %d\n' % i for i in range(25)))
    p = d + '/d.dsk'
    skdisk.make_disk(p, [d + '/filler.txt', d + '/target.txt'], None, 'DSDDSIDE1', 'dsdd')
    img = bytearray(open(p, 'rb').read())
    chk(len(img) == 368640, 'the image is 360K (%d bytes: 1,440 sectors)' % len(img))
    m = sim9900.Machine(c)
    card = make_card(img)
    m.tifdc = card
    reads, writes = [], []
    if hasattr(card, 'wd'):
        rs, ws = card.wd.read_sector_in, card.wd.write_sector_out
        card.wd.read_sector_in = lambda: (reads.append((card.wd.side, card.wd.track, card.wd.sector)), rs())[1]
        card.wd.write_sector_out = lambda: (writes.append((card.wd.side, card.wd.track, card.wd.sector)), ws())[1]
    else:                                      # the HFDC logs its own (head, cylinder, sector)
        reads, writes = card.sector_log['r'], card.sector_log['w']
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m); cpu.pc = m.rw(m.rw(0x6006) + 2)
    while m.insns < 100 * sim9900.VSYNC_INSNS:
        cpu.step()
    call = lambda n, r=None: asmharness.call(m, cpu, syms[n.lower()], r or {}, limit=60_000_000)
    W, REC = 0x2300 + 5000, 0x2300 + 5300
    def put(a, s):
        for i, b in enumerate(bytes([len(s)]) + s.encode()): m.wb(a + i, b)
    put(W, 'DSK1.TARGET/TXT'); call('FSEL', {0: 0})
    r = call('FOPEN', {0: 0x1400, 1: 80, 2: W})[0]
    got = []
    while call('FREAD', {1: REC})[0] == 0 and len(got) < 100:
        n = m.rb(REC - 0)  # (the record's text is at REC; its length is not needed)
        got.append(bytes(m.rb(REC + i) for i in range(14)).decode('latin-1').rstrip())
    call('FCLOSE')
    chk(r == 0 and len(got) == 25 and got[0].startswith('target line 0') and got[24].startswith('target line 24'),
          'a file on the second side is opened and its 25 records read (error %d, %d records)' % (r, len(got)))
    chk(any(sd == 1 for sd, tr, sc in reads), 'and the chip really read side 1 for it (sides read: %s)' % sorted(set(sd for sd, tr, sc in reads)))
    put(W, 'DSK1.NEWFILE'); call('FSEL', {0: 0})
    r = call('FOPEN', {0: 0x0200 | 0x1000, 1: 80, 2: W})[0]
    recs = [('new record %d' % i).encode() for i in range(60)]
    for x in recs:
        for i, b in enumerate(x): m.wb(REC + i, b)
        call('FWRITE', {1: REC, 2: len(x)})
    call('FCLOSE')
    chk(r == 0 and tifdc.read_file(img, 'NEWFILE') == recs and any(sd == 1 for sd, tr, sc in writes),
          'a new file written to the second side is on the disk record for record (%d sectors written, sides %s)' % (len(writes), sorted(set(sd for sd, tr, sc in writes))))
    put(W, 'DSK1.'); call('FSEL', {0: 0})
    REC2 = 0x2300 + 5600
    r = call('FCATOP', {1: REC2, 2: W})[0]
    size = call('FCNUM', {1: REC2, 2: 1})[0]
    free = call('FCNUM', {1: REC2, 2: 2})[0]
    call('FCLOSE')
    chk(r == 0 and size in (1438, 1440) and 0 < free < 700, 'the catalog says %d sectors, %d free: a 360K disk has 1,440 (the DSR does not count the volume block and file index; the single-density 90K disk has 360)' % (size, free))

def dsdd():
    """A double-sided double-density disk through the real DSR of each double-density card the simulator has: the CorComp
    (tools/ccfdc.py) and the Myarc DDCC-1 (tools/myfdc.py), on the chip model of tools/fdc.py: a file that lies on the
    disk's second side (a filler of about 250K pushes it past sector 720) is read, a new file written there is on the disk
    record for record, and the catalog gives the disk's size."""
    cards = []
    if __import__('ccfdc').available():
        cards.append(('CorComp', lambda img: __import__('ccfdc').CCFDC(image=img)))
    if __import__('myfdc').available():
        cards.append(('Myarc DDCC-1', lambda img: __import__('myfdc').MYFDC(image=img)))
    if __import__('hfdc').available():
        cards.append(('Myarc HFDC', lambda img: __import__('hfdc').HFDC(image=img)))
    only = os.environ.get('TESTCARDS')
    if only:
        cards = [c for c in cards if any(w in c[0] for w in only.split(','))]
    if not cards:
        print('  (skipped: the CorComp and Myarc ROMs are not found)')
    for label, make_card in cards:
        _dsdd(label, make_card)

def dsddworkbench():
    """The workbench on a 360K double-density disk, through each double-density card's real DSR: the catalog lists every
    program on the disk, and HELLO/A99 is assembled on the (simulated) TI and equals what xas99 makes of it.  The disk is
    built here as the distribution's workbench-360k.dsk is (tools/skdisk.py --geometry dsdd)."""
    import tempfile, asmharness, skdisk, ccfdc, myfdc
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    build('workbench')
    kequ = os.path.join(ROOT, 'build', 'workbench', 'kernel.equ')
    files = [os.path.join(ROOT, f) for f in (
        'examples/hello/hello.a99', 'examples/workbench/programs/beep.a99', 'examples/workbench/programs/mode.a99',
        'examples/workbench/programs/copy.a99', 'examples/workbench/programs/paging.a99', 'examples/workbench/programs/clock.a99',
        'examples/joystick/joy.a99', 'tests/asm/probe1.a99', 'examples/reversi/revers.a99', 'examples/modes/modes.a99',
        'examples/workbench/wb.a99', 'examples/workbench/ed.a99', 'examples/workbench/asm.a99')]
    d = tempfile.mkdtemp()
    p = d + '/w.dsk'
    open(d + '/SRC', 'w').write('a short sample text file\nfor COPY/A99 to copy\n')
    files.append(d + '/SRC')
    skdisk.make_disk(p, files, kequ, 'WORKBENCH', 'dsdd')
    disk = open(p, 'rb').read()
    want = asmharness.assemble(files[0], 'workbench')
    cards = []
    if ccfdc.available(): cards.append(('CorComp', lambda img: ccfdc.CCFDC(image=img)))
    if myfdc.available(): cards.append(('Myarc DDCC-1', lambda img: myfdc.MYFDC(image=img)))
    import hfdc
    if hfdc.available(): cards.append(('Myarc HFDC', lambda img: hfdc.HFDC(image=img)))
    only = os.environ.get('TESTCARDS')
    if only:
        cards = [c for c in cards if any(w in c[0] for w in only.split(','))]
    for label, make in cards:
        def hook(m, make=make):
            m.tifdc = make(bytearray(disk))
        m, img = asmharness.workbench_ui('<WAIT 10>c<WAIT 400>', 700, [], setup2=hook)
        text = ' '.join(sim9900.screen(m).split('\n'))
        names = ['HELLO/A99', 'REVERS/A99', 'MODES/A99', 'KERNEL/EQU', 'WB/A99', 'ED/A99', 'ASM/A99', 'SRC']
        check(all(n in text for n in names), '[%s] the catalog of the 360K disk lists the programs (%d of %d names seen)' % (label, sum(n in text for n in names), len(names)))
        m, img = asmharness.workbench_ui('<WAIT 10>nHELLO/A99<ENTER><WAIT 10>a<WAIT 2600>', 2900, [], setup2=hook)
        text = ' '.join(sim9900.screen(m).split('\n'))
        check('Assembled' in text and ('%d' % want.length) in text.replace(' ', ' '), '[%s] HELLO/A99 assembles on the TI from the 360K disk: %d bytes as xas99 makes it' % (label, want.length))

def hfdccru():
    """CRU bit order, as the HFDC card and its DSR use it: LDCR with fewer than 8 bits takes them from the high byte of the
    register, LSB first, from the CRU bit the R12 address names.  A 5-bit RAM page number starts at CRU bit 9 (R12 = base + >12);
    the ROM page is two bits, 3 (the MSB of the page) and 4 (the LSB), so SBZ 3 / SBO 4 equals LDCR R1,2 with R1 = >0200."""
    import hfdc
    if not hfdc.available():
        print('  (skipped: the HFDC ROM is not found)')
        return
    c = build('hello')
    m = sim9900.Machine(c)
    card = hfdc.HFDC()
    m.tifdc = card
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m)
    def run(words, regs):
        for r, v in regs.items(): cpu.setreg(r, v)
        for i, w in enumerate(words): m.ww(0x8320 + 2 * i, w)
        cpu.pc = 0x8320
        for _ in words: cpu.step()
    run([0x3041 | (5 << 6)], {12: 0x1112, 1: 0x1F00})                 # LDCR R1,5 at CRU bit 9
    check(card.ram_page[1] == 0x1F, 'LDCR R1,5 with R1=>1F00 at CRU bit 9 sets the RAM page at >5400 to >1F (%X)' % card.ram_page[1])
    run([0x3041 | (5 << 6)], {12: 0x1112 + 10, 1: 0x0500})            # bits 14-18: the page at >5800: 00101 LSB first
    check(card.ram_page[2] == 0x05, 'the same for the page at >5800 (bit 14): >05 (%X)' % card.ram_page[2])
    card.cru = [0] * 24; card.rom_page = 0
    run([0x1E03, 0x1D04], {12: 0x1100})                                # SBZ 3 ; SBO 4
    a = (card.cru[3], card.cru[4], card.rom_page)
    card.cru = [0] * 24; card.rom_page = 0
    run([0x3041 | (2 << 6)], {12: 0x1106, 1: 0x0200})                  # LDCR R1,2: bit 3 = 0, bit 4 = 1
    b = (card.cru[3], card.cru[4], card.rom_page)
    check(a == b == (0, 1, 1), 'SBZ 3 + SBO 4 and LDCR R1,2 (R1=>0200) at bit 3 are the same: CRU 3=0, 4=1, ROM page 1 (%s, %s)' % (a, b))

def linein():
    """LINEIN, the line editor (lib/linein.a99, an optional include, carried by the module of tests/apps/linein): typing, the cursor and function keys, insert and overtype, the length
    limit, the screen it draws (text, blanks, the cursor in swapped colours), ENTER and BACK, and the history in a pool page:
    older and newer lines, the line as typed coming back, a repeated line stored once, the ring of 50, slot B and the
    registers left as they were."""
    import asmharness
    c = build('tests/apps/linein')
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'linein', 'kernel.equ'))
    syms.update(asmharness.symbols(os.path.join(ROOT, 'build', 'linein', 'lin.equ')))      # the module's own: LINEIN and its helpers
    check('linein' in syms and syms['linein'] >= 0xC000 and syms['linein'] < 0xD000, 'LINEIN is in the module, not the kernel (>%04X)' % syms.get('linein', 0))
    NAMES = {'ENTER': 0x0D, 'BACK': 0xF9, 'LEFT': 0xD3, 'RIGHT': 0xC4, 'HOME': 0xF5, 'END': 0xF6, 'DEL': 0xF1, 'BS': 0x88,
             'ERASE': 0xF3, 'INS': 0xF2, 'UP': 0xC5, 'DOWN': 0xD8, 'F1': 0xB1}
    def codes(s):
        out, i = [], 0
        while i < len(s):
            if s[i] == '{':
                j = s.index('}', i)
                out.append(NAMES[s[i + 1:j]]); i = j + 1
            else:
                out.append(ord(s[i])); i += 1
        return out
    m = sim9900.Machine(c)
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m)
    cpu.pc = m.rw(m.rw(0x6006) + 2)
    while m.insns < 100 * sim9900.VSYNC_INSNS:
        cpu.step()
    W = 0x2300 + 3000
    def run(keys, start='', maxlen=20, hist=0, pos=5 * 80 + 10, attr=0x2100):
        for i, b in enumerate(bytes([len(start)]) + start.encode()):
            m.wb(W + i, b)
        ks = codes(keys)
        for i, k in enumerate(ks):
            m.wb(0x2040 + i, k)
        m.ww(0x200E, len(ks)); m.ww(0x2010, 0)
        r = asmharness.call(m, cpu, syms['linein'], {0: pos, 1: W, 2: attr, 3: maxlen, 4: hist, 9: 0x1234}, limit=50_000_000)
        n = m.rb(W)
        return r, bytes(m.rb(W + 1 + i) for i in range(n)).decode('latin-1')
    def ok(keys, want, **kw):
        r, got = run(keys, **kw)
        return got == want, got
    r, got = run('hello{ENTER}')
    check(got == 'hello' and r[0] == 0x0D00, 'typing "hello" and ENTER gives the line and KENTER (%r, >%04X)' % (got, r[0]))
    check(r[9] == 0x1234, 'R9 comes back as it was (>%04X)' % r[9])
    cases = [
        ('abcd{LEFT}{LEFT}X{ENTER}', 'abXcd', 'insert in the middle moves the rest right'),
        ('abcd{LEFT}{LEFT}X{DEL}{ENTER}', 'abXd', 'DEL deletes the character under the cursor'),
        ('abcd{LEFT}{LEFT}X{DEL}{BS}{ENTER}', 'abd', 'CTRL H deletes the one before it'),
        ('abcd{HOME}Z{ENTER}', 'Zabcd', 'BEGIN goes to the start'),
        ('abcd{HOME}{END}e{ENTER}', 'abcde', 'PROC\'D goes to the end'),
        ('abcd{HOME}{INS}XY{ENTER}', 'XYcd', 'INS switches to overtype'),
        ('abcd{HOME}{INS}{INS}X{ENTER}', 'Xabcd', 'INS again goes back to insert'),
        ('abc{INS}{HOME}{RIGHT}{RIGHT}{RIGHT}XY{ENTER}', 'abcXY', 'overtype past the end appends'),
        ('abcd{ERASE}xy{ENTER}', 'xy', 'ERASE empties the line'),
        ('{BS}{DEL}{LEFT}ab{ENTER}', 'ab', 'delete and left on an empty line do nothing'),
        ('abc{BS}{BS}{BS}{BS}x{ENTER}', 'x', 'CTRL H past the start stops there'),
        ('ab{F1}c{ENTER}', 'abc', 'a key the editor does not use is ignored'),
    ]
    for keys, want, what in cases:
        good, got = ok(keys, want)
        check(good, 'LINEIN: %s (%r)' % (what, got))
    good, got = ok('abcdefgh{ENTER}', 'abcde', maxlen=5)
    check(good, 'the line stops at the longest length, 5 (%r)' % got)
    good, got = ok('{LEFT}X{ENTER}', 'abcde', start='abcde', maxlen=5)
    check(good, 'an insert into a full line is ignored (%r)' % got)
    good, got = ok('d{ENTER}', 'abcd', start='abc')
    check(good, 'a start text is kept and the cursor begins at its end (%r)' % got)
    good, got = ok('{ENTER}', 'abcde', start='abcdefghij', maxlen=5)
    check(good, 'a start text longer than the field is cut (%r)' % got)
    good, got = ok('{ENTER}', 'x' * 79, start='x' * 100, maxlen=200)
    check(good, 'a longest length over 79 is taken as 79: a 100-character start text is cut to %d' % len(got))
    r, got = run('xy{BACK}')
    check(r[0] == 0xF900 and got == 'xy', 'BACK ends it with KBACK, the text typed so far kept (>%04X, %r)' % (r[0], got))
    # the screen
    r, got = run('hi{ENTER}', maxlen=6, pos=7 * 80 + 4, attr=0x2100)
    pos = 7 * 80 + 4
    namb = m.rw(syms['nambas'])
    atrt = syms['atrtab']
    text = bytes(m.vram[namb + pos: namb + pos + 8]).decode('latin-1')
    attrs = list(m.vram[atrt + pos: atrt + pos + 7])
    check(text == 'hi      ', 'the screen shows the text then blanks over the field and one cell more (%r)' % text)
    check(attrs == [0x21, 0x21, 0x12, 0x21, 0x21, 0x21, 0x21], 'the text and the blanks (to one cell past the field, 6 + 1) have the attribute, the cursor cell its swap >12: %s' % [hex(a) for a in attrs])
    # a scrolling field: width 10 (the high byte of R3), a line of up to 40
    def cells(pos, n):
        return bytes(m.vram[namb + pos + i] for i in range(n)).decode('latin-1')
    def attrs_of(pos, n):
        return [m.vram[atrt + pos + i] for i in range(n)]
    pos = 3 * 80 + 6
    typed = 'abcdefghijklmnopqrstuvwxy'
    r, got = run(typed + '{ENTER}', maxlen=10 * 256 + 40, pos=pos)
    check(got == typed and r[0] == 0x0D00, 'scrolling field: a 25-character line in a field of 10 is all in the buffer (%r)' % got)
    check(cells(pos, 10) == 'qrstuvwxy ', 'the field shows the last nine characters and the cursor cell: %r' % cells(pos, 10))
    check(attrs_of(pos, 11) == [0x21] * 9 + [0x12, 0x21], 'the cursor is the tenth cell, and the field is exactly ten cells wide: %s' % [hex(a) for a in attrs_of(pos, 11)])
    run(typed + '{HOME}{ENTER}', maxlen=10 * 256 + 40, pos=pos)
    check(cells(pos, 10) == 'abcdefghij' and attrs_of(pos, 2) == [0x12, 0x21], 'HOME scrolls back to the start: %r, the cursor in the first cell' % cells(pos, 10))
    run(typed + '{LEFT}' * 12 + '{ENTER}', maxlen=10 * 256 + 40, pos=pos)
    check(cells(pos, 10) == 'nopqrstuvw' and attrs_of(pos, 1) == [0x12], '12 steps left from the end scroll the window to start at the cursor: %r' % cells(pos, 10))
    r, got = run(typed + '{HOME}Z{ENTER}', maxlen=10 * 256 + 40, pos=pos)
    check(got == 'Z' + typed, 'typing at the start of a long line inserts there (%r)' % got)
    r, got = run(typed + '{HOME}{END}!{ENTER}', maxlen=10 * 256 + 40, pos=pos)
    check(got == typed + '!' and cells(pos, 10) == 'rstuvwxy! ', 'END scrolls to the end and typing goes on there (%r, %r)' % (got, cells(pos, 10)))
    run('abcde{ENTER}', maxlen=30 * 256 + 5, pos=pos)
    check(cells(pos, 6) == 'abcde ' and attrs_of(pos, 7)[5] == 0x12, 'a width larger than the longest line + 1 is the old field: 6 cells (%r)' % cells(pos, 7))
    run('abc{ENTER}', maxlen=1 * 256 + 5, pos=pos)
    check(cells(pos, 4) == 'abc ' and attrs_of(pos, 7)[3] == 0x12, 'a width of 1 is no scrolling either (%r)' % cells(pos, 4))
    # the history
    cpu_r = asmharness.call(m, cpu, syms['pinit'], {0: 0x40, 1: 0x60})
    page = asmharness.call(m, cpu, syms['palloc'])[0]
    page2 = asmharness.call(m, cpu, syms['palloc'])[0]
    check(page != 0 and page2 != 0 and page != page2, 'the pool gives two pages for the tests (>%02X, >%02X)' % (page, page2))
    for ln in ('one', 'two', 'three'):
        run(ln + '{ENTER}', hist=page)
    good, got = ok('{UP}{BACK}', 'three', hist=page)
    check(good, 'UP brings back the newest line (%r)' % got)
    good, got = ok('{UP}{UP}{BACK}', 'two', hist=page)
    check(good, 'UP twice the one before (%r)' % got)
    good, got = ok('{UP}{UP}{UP}{UP}{UP}{BACK}', 'one', hist=page)
    check(good, 'UP past the oldest stays on the oldest (%r)' % got)
    good, got = ok('par{UP}{UP}{DOWN}{DOWN}{BACK}', 'par', hist=page)
    check(good, 'DOWN past the newest brings back the line as it was typed (%r)' % got)
    good, got = ok('{UP}{UP}{DOWN}{BACK}', 'three', hist=page)
    check(good, 'DOWN steps forward again (%r)' % got)
    good, got = ok('{DOWN}x{BACK}', 'x', hist=page)
    check(good, 'DOWN with nothing newer does nothing (%r)' % got)
    good, got = ok('{UP}{HOME}Z{ENTER}', 'Zthree', hist=page)
    check(good, 'a recalled line can be edited (%r)' % got)
    # that edit was entered: it is the newest now; a repeat of it is stored once
    run('Zthree{ENTER}', hist=page)
    good, got = ok('{UP}{UP}{BACK}', 'three', hist=page)
    check(good, 'the same line entered twice in a row is stored once: UP twice reaches the line before it (%r)' % got)
    run('{ENTER}', hist=page)
    good2, got2 = ok('{UP}{BACK}', 'Zthree', hist=page)
    check(good2, 'an empty line is not stored: the newest is still Zthree (%r)' % got2)
    # a line from the history is cut to a shorter field
    good, got = ok('{UP}{BACK}', 'Zthr', hist=page, maxlen=4)
    check(good, 'a recalled line is cut to the field (%r)' % got)
    # the ring: 55 lines, only the newest 50 stay
    for i in range(1, 56):
        run('L%d{ENTER}' % i, hist=page2)
    good, got = ok('{UP}' * 60 + '{BACK}', 'L6', hist=page2)
    check(good, 'the history keeps the newest 50 of 55 lines: UP as far as it goes reaches L6 (%r)' % got)
    good, got = ok('{UP}{BACK}', 'L55', hist=page2)
    check(good, 'and the newest is L55 (%r)' % got)
    # slot B and the stack
    asmharness.call(m, cpu, syms['mape'], {0: 0x41})
    asmharness.call(m, cpu, syms['mapf'], {0: 0x42})
    before = (m.rw(syms['curbe']), m.rw(syms['curbf']))
    r10 = m.rw(0x8314)
    r, got = run('{UP}{DOWN}{UP}{ENTER}', hist=page)
    after = (m.rw(syms['curbe']), m.rw(syms['curbf']))
    check(before == after == (0x41, 0x42), 'slot B is as it was after history use: >E000 page >%02X, >F000 page >%02X' % after)
    check(r[10] == r10, 'the software stack is balanced (R10 >%04X before, >%04X after)' % (r10, r[10]))

def resident():
    """Resident code (docs/RESIDENT.md): app.json "resident" assembles a source INTO THE KERNEL's pages, so every module
    can BL to its exported routines.  tests/apps/resident: module A and module B each call RSUM on a table in their own
    code and RCALL with a callback in their own code (which MODCALL cannot do: the caller's module is unmapped), and module B
    reads a line with LINEIN carried once in the resident code.  Also: the exports reach the modules and nothing else
    does, and a build refuses an export that is not a label, a resident that does not fit, and a missing source."""
    import asmharness, shutil, tempfile
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), os.path.join(ROOT, 'tests', 'apps', 'resident')], capture_output=True, text=True)
    check(r.returncode == 0 and 'of which resident code' in r.stdout, 'the application with resident code builds and says how much of the kernel it is: %s' % [l.strip() for l in r.stdout.split('\n') if 'resident' in l][:1])
    c = open(glob.glob(os.path.join(ROOT, 'build', 'resident', '*8.bin'))[0], 'rb').read()
    equ = asmharness.symbols(os.path.join(ROOT, 'build', 'resident', 'ma.equ'))
    check(all(n in equ for n in ('rsum', 'rcall', 'linein')) and all(0xA000 <= equ[n] < 0xBE00 for n in ('rsum', 'rcall', 'linein')),
          'the modules see the three exports, at addresses in the kernel pages: %s' % {n: hex(equ[n]) for n in ('rsum', 'rcall', 'linein') if n in equ})
    check(not any(n in equ for n in ('rsu1', 'rcl1', 'lndraw', 'lnlen', 'kresb', 'krese')), 'and not the resident code\'s own labels or the kernel\'s')
    m, cpu, halt = sim9900.run(c, frames=700, keys='<WAIT 10>hi<ENTER>')       # real key presses, to the LINEIN in module B
    check(halt is None, 'the application runs both modules without a halt (%s)' % halt)
    ra = [m.rw(0x2300 + i) for i in (0, 2)]
    rb = [m.rw(0x2300 + 10 + i) for i in (0, 2, 4)]
    check(ra == [55, 30], 'module A: RSUM of a table in its own code is 55, RCALL with a callback in its own code is 0+1+4+9+16 = 30 (%s)' % ra)
    check(rb[:2] == [600, 18], 'module B: RSUM 100+200+300 = 600, RCALL with its own callback 0+3+6+9 = 18 (%s)' % rb[:2])
    n = m.rb(0x2300 + 100)
    got = bytes(m.rb(0x2300 + 101 + i) for i in range(n)).decode('latin-1')
    check(rb[2] == 0x0D00 and got.upper() == 'HI', 'module B: the resident LINEIN read "hi" and ENTER (>%04X, %r)' % (rb[2], got))
    # a build without resident code is unchanged
    r0 = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), os.path.join(ROOT, 'examples', 'hello')], capture_output=True, text=True)
    check('resident code' not in r0.stdout and 'kernel 6' in r0.stdout, 'an application without resident code builds as before (%s)' % [l for l in r0.stdout.split('\n') if l.startswith('kernel')][0][:60])
    def variant(edit_json=None, edit_res=None):
        d = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, 'tests', 'apps', 'resident'), d + '/app')
        if edit_json:
            j = json.load(open(d + '/app/app.json')); edit_json(j); json.dump(j, open(d + '/app/app.json', 'w'))
        if edit_res:
            open(d + '/app/resident.a99', 'a').write(edit_res)
        return subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/app', '--out', d + '/out'], capture_output=True, text=True)
    r1 = variant(lambda j: j['resident']['exports'].append('NOSUCH'))
    check(r1.returncode != 0 and 'NOSUCH' in (r1.stdout + r1.stderr), 'an export that is not a label is refused, by name')
    r2 = variant(edit_res='       BSS  2000\n')
    check(r2.returncode != 0 and 'page-pool bitmap' in (r2.stdout + r2.stderr), 'a resident that does not fit is refused: it runs into the pool bitmap')
    r3 = variant(lambda j: j['resident'].update(source='missing.a99'))
    check(r3.returncode != 0 and 'missing.a99' in (r3.stdout + r3.stderr), 'a missing resident source is refused, by name')
    r4 = variant(lambda j: j['resident'].update(exports=['bad name']))
    check(r4.returncode != 0 and 'not a label' in (r4.stdout + r4.stderr), 'an export that is not even a name is refused')

def poolmax():
    """app.json "pool_max_pages": the pool's bitmap has a bit per page up to that number only, so it is smaller (pages/8 bytes,
    at the top of the kernel's pages) and the kernel may be longer.  A build with it makes room for resident code that the default
    does not, PINIT hands out no page from the limit up and never writes outside the smaller bitmap, PRELS ignores such a
    page, and bad values are refused."""
    import asmharness, shutil, tempfile
    def build_variant(edit_json=None, edit_res=None):
        d = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, 'tests', 'apps', 'resident'), d + '/app')
        if edit_json:
            j = json.load(open(d + '/app/app.json')); edit_json(j); json.dump(j, open(d + '/app/app.json', 'w'))
        if edit_res:
            open(d + '/app/resident.a99', 'a').write(edit_res)
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/app', '--out', d + '/out'], capture_output=True, text=True)
        return r, d + '/out'
    big = '       BSS  300\n'
    r, out = build_variant(lambda j: j.pop('pool_max_pages', None))
    check(r.returncode != 0 and 'page-pool bitmap' in (r.stdout + r.stderr), 'with the default bitmap (512 bytes) the test application\'s resident code (LINEIN, with its scrolling field, is about 1,050 bytes) does not fit: %s' % (r.stdout + r.stderr).strip().split('\n')[-1][:90])
    r, out = build_variant(lambda j: j.update(pool_max_pages=256), big)
    check(r.returncode == 0 and 'at >BFE0' in r.stdout, 'with "pool_max_pages": 256 (a 32-byte bitmap at >BFE0) it fits with 300 more bytes: %s' % [l for l in r.stdout.split('\n') if l.startswith('kernel')])
    syms = asmharness.symbols(os.path.join(out, 'kernel.equ'))
    check(syms['poolbm'] == 0xBFE0 and syms['poolmx'] == 256 and syms['poolwd'] == 16, 'kernel.equ says: POOLBM >%04X, POOLMX %d, POOLWD %d' % (syms['poolbm'], syms['poolmx'], syms['poolwd']))
    c = open(glob.glob(out + '/*8.bin')[0], 'rb').read()
    m = sim9900.Machine(c)
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m)
    cpu.pc = m.rw(m.rw(0x6006) + 2)
    while m.insns < 100 * sim9900.VSYNC_INSNS:
        cpu.step()
    call = lambda n, regs=None: asmharness.call(m, cpu, syms[n], regs or {}, limit=20_000_000)
    for i in range(32):                                  # the bytes just below the bitmap: PINIT must leave them alone
        m.wb(0xBFC0 + i, 0xAA)
    call('pinit', {0: 0x20, 1: 4096})
    check(m.rw(syms['poolhi']) == 256 and m.rw(syms['freect']) == 256 - 0x20, 'PINIT with 4096 as its end is cut to 256: POOLHI %d, %d pages free (%d)' % (m.rw(syms['poolhi']), m.rw(syms['freect']), 256 - 0x20))
    check(all(m.rb(0xBFC0 + i) == 0xAA for i in range(32)), 'and it did not write below the bitmap (the 32 bytes under it are as they were)')
    pages = []
    while True:
        p = call('palloc')[0]
        if p == 0:
            break
        pages.append(p)
    check(len(pages) == 224 and min(pages) == 0x20 and max(pages) == 255 and len(set(pages)) == 224, 'PALLOC hands out 224 distinct pages, >20 to 255, and then says 0 (%d pages, %s-%s)' % (len(pages), hex(min(pages)), hex(max(pages))))
    call('prels', {0: 300})
    call('prels', {0: 4000})
    check(m.rw(syms['freect']) == 0, 'PRELS of a page the bitmap has no bit for (300, 4000) is ignored: still %d free' % m.rw(syms['freect']))
    call('prels', {0: 100})
    check(m.rw(syms['freect']) == 1 and call('palloc')[0] == 100, 'PRELS of a pool page works: page 100 comes back')
    # the default bitmap is unchanged
    r0 = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), os.path.join(ROOT, 'examples', 'hello'), '--out', tempfile.mkdtemp()], capture_output=True, text=True)
    check('at >BE00' in r0.stdout, 'an application without the field still has the 512-byte bitmap at >BE00')
    # bad values
    for val, why in ((100, 'not a multiple of 64'), (8192, 'more than 4096'), (0, 'none'), ('lots', 'not a number')):
        r, _ = build_variant(lambda j, v=val: j.update(pool_max_pages=v))
        check(r.returncode != 0 and 'pool_max_pages' in (r.stdout + r.stderr), 'pool_max_pages %r (%s) is refused' % (val, why))
    r, _ = build_variant(lambda j: (j.update(pool_max_pages=64), j['modules'][1].update(page='0x60')))
    check(r.returncode != 0 and 'pool would be empty' in (r.stdout + r.stderr), 'a limit at or below the first free page is refused: the pool would be empty')

def editorapp():
    """examples/editor: the workbench's editor module as a program of its own, behind a small front module that asks for a file
    name with LINEIN: a missing name is refused, a name opens an empty buffer, typing and CTRL S write the file to the disk,
    CTRL X comes back to the prompt with the name kept, and the history page is not a pool page."""
    import tempfile, skdisk, tifdc
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    c = build('editor')
    d = tempfile.mkdtemp(); p = d + '/d.dsk'
    skdisk.make_disk(p, [])
    img = bytearray(open(p, 'rb').read())
    box = {}
    def setup(m):
        box['f'] = tifdc.TIFDC(image=img); m.tifdc = box['f']
    m, cpu, halt = sim9900.run(c, frames=900, keys='<WAIT 30>T1<ENTER><WAIT 40>hello<C-s><WAIT 80><C-x><WAIT 60>', setup=setup)
    ln = [l.strip() for l in sim9900.screen(m).split('\n')]
    check(halt is None, 'the editor application runs (%s)' % halt)
    check(tifdc.read_file(box['f'].image, 'T1') == [b'HELLO'], 'a name typed at the prompt opens an empty buffer; typing and CTRL S write DSK1.T1 on the disk: %s' % tifdc.read_file(box['f'].image, 'T1'))
    check(any(l.startswith('File:') and l.endswith('DSK1.T1') for l in ln), 'CTRL X comes back to the prompt with the name kept: %r' % [l for l in ln if l.startswith('File:')])
    m, cpu, halt = sim9900.run(c, frames=400, keys='<WAIT 30><ENTER><WAIT 40>', setup=setup)
    ln = [l.strip() for l in sim9900.screen(m).split('\n')]
    check(any('needs more after the dot' in l for l in ln) and any(l.startswith('File:') for l in ln), 'ENTER on the bare device is refused with a message, and the prompt stays: %r' % [l for l in ln if 'needs more' in l or l.startswith('File:')])

def sourcesdisk():
    """tools/mksources.py: the 360K disk of the kernel's sources for the TI.  Every name fits a TI disk, the four long names
    are shortened with the COPY lines that name them changed to match (and the repository's files are not touched), every file a
    source COPYs is on the disk except the three the build writes for each application, and the disk reads back."""
    import re, tempfile, subprocess, mksources, tifdc
    d = tempfile.mkdtemp(); out = d + '/s.dsk'
    names = mksources.build(out)
    check(all(len(n) <= 10 for n in names), 'every file name fits a TI disk (%d files, longest %d characters)' % (len(names), max(len(n) for n in names)))
    k = names['KERNEL/A99']
    check('COPY "module.a99"' in k and 'COPY "modules.a99"' not in k and 'COPY "kres.a99"' in k, 'in the disk copy of kernel.a99 the COPY lines name the shortened files')
    check('modules.a99' in open(os.path.join(ROOT, 'kernel', 'kernel.a99')).read(), 'and the repository\'s kernel.a99 is as it was')
    have = {n.split('/')[0].lower() for n in names}
    missing = set()
    for n, text in names.items():
        for m in re.finditer(r'^\s+COPY\s+"([^"]+)\.a99"', text, re.M):
            if m.group(1).lower() not in have:
                missing.add(m.group(1).lower())
    check(missing == {'appcfg', 'appname', 'appmsg'}, 'every COPY target is on the disk except the three the build writes for each application: %s' % sorted(missing))
    info = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.environ['XAS99']), 'xdm99.py'), out], capture_output=True, text=True).stdout.split('\n')[0]
    used = int(re.search(r':\s+(\d+) used\s+(\d+) free', info).group(1))
    check('SOURCES' in info and '2S/2D' in info and used < 1300, 'a double-density disk named SOURCES with room to spare: %s' % info.strip())
    back = tifdc.read_file(bytearray(open(out, 'rb').read()), 'SRCNOTES')
    check(b'\n'.join(back).decode('latin-1').rstrip() == mksources.NOTES.rstrip(), 'SRCNOTES reads back from the image record for record')

def jumpcheck():
    """tools/jumpcheck.py: the jumps close to the edge of their range, from an assembler listing."""
    import tempfile, jumpcheck as jc
    build('hello')
    rows = jc.scan(os.path.join(ROOT, 'build', 'hello', 'kernel.lst'))
    check(len(rows) > 200 and rows[0][0] >= 0, 'the kernel listing has %d jumps, the tightest with %d words to spare' % (len(rows), rows[0][0]))
    d = tempfile.mkdtemp(); p = d + '/t.lst'
    open(p, 'w').write('0001 A000 137F  14        JEQ  FAR                 forward, the longest reach\n'
                       '0002 A002 1080  14        JMP  BACK                back, the longest reach\n'
                       '0003 A004 1301  14        JEQ  NEAR                two words on\n'
                       '0004 A006 0201  14        LI   R1,>1234            not a jump\n'
                       '0005 A008 1D00  14        SBO  0                   not a jump either\n')
    got = jc.scan(p)
    check([(s, dsp) for s, _, dsp in got] == [(0, 127), (0, -128), (126, 1)], 'a synthetic listing: the two longest reaches have 0 words to spare, the near one 126, and non-jumps are ignored: %s' % [(s, dsp) for s, _, dsp in got])

def trim():
    """app.json "omit": parts of the kernel an application leaves out (music, files, pool).  Each makes the kernel smaller and the
    application still runs; leaving out the pool also frees its bitmap's 512 bytes, so a kernel may then be 8,192 bytes; a module that
    uses a routine that was left out is refused by name; bad lists are refused."""
    import shutil, tempfile
    def variant(src_dir, edit_json=None, edit_file=None):
        d = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, src_dir), d + '/app')
        if edit_json:
            j = json.load(open(d + '/app/app.json')); edit_json(j); json.dump(j, open(d + '/app/app.json', 'w'))
        if edit_file:
            edit_file(d + '/app')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/app', '--out', d + '/out'], capture_output=True, text=True)
        size = None
        for l in r.stdout.split('\n'):
            if l.startswith('kernel '):
                size = int(l.split()[1])
        img = glob.glob(d + '/out/*8.bin')
        return r, size, (open(img[0], 'rb').read() if img else None)
    def echoes(img):
        m, cpu, halt = sim9900.run(img, frames=300, keys='hi')
        return halt is None and any(l.strip() == 'HI' for l in sim9900.screen(m).split('\n'))
    r, base, img = variant('examples/hello')
    check(base is not None and echoes(img), 'the unchanged application: a kernel of %s bytes, and it runs and echoes keys' % base)
    for words, least in ((['music'], 480), (['files'], 1900), (['pool'], 150), (['music', 'files', 'pool'], 2600)):
        r, size, img = variant('examples/hello', lambda j, w=words: j.update(omit=w))
        check(r.returncode == 0 and size is not None and base - size >= least and echoes(img),
              'omit %s: the kernel is %s bytes, %s smaller (at least %d), and the application still runs' % (words, size, base - size if size else '?', least))
    r, size, img = variant('examples/hello', lambda j: j.update(omit=['music', 'files', 'pool']))
    check('in its 8K: no pool, no bitmap' in r.stdout and 'left out of the kernel (app.json "omit"): music, files, pool' in r.stdout, 'the build says what was left out and that there is no bitmap: %s' % [l.strip() for l in r.stdout.split('\n') if 'left out' in l or 'in its 8K' in l])
    def uses(routine):
        def f(d):
            s = open(d + '/hello.a99').read()
            s = s.replace('INIT   .enter', 'INIT   .enter\n       BL   @%s' % routine, 1) if 'INIT   .enter' in s else s + '\n       BL   @%s\n' % routine
            open(d + '/hello.a99', 'w').write(s)
        return f
    for routine, word in (('FOPEN', 'files'), ('PINIT', 'pool'), ('MUPLAY', 'music')):
        r, size, img = variant('examples/hello', lambda j, w=word: j.update(omit=[w]), uses(routine))
        check(r.returncode != 0 and routine in (r.stdout + r.stderr) and ('"%s"' % word) in (r.stdout + r.stderr), 'a module that BLs %s, with "%s" left out, is refused by name: %s' % (routine, word, (r.stdout + r.stderr).strip().split('\n')[-1][:100]))
    r, size, img = variant('examples/hello', lambda j: j.update(omit=['music']), uses('FOPEN'))
    check(r.returncode == 0, 'and using a routine that is NOT left out is fine (FOPEN with only music omitted)')
    r, size, img = variant('examples/hello', lambda j: j.update(omit=['sound']))
    check(r.returncode != 0 and 'omit' in (r.stdout + r.stderr), 'an unknown part is refused')
    r, size, img = variant('examples/hello', lambda j: j.update(omit=['pool'], pool_max_pages=256))
    check(r.returncode != 0 and 'pool_max_pages' in (r.stdout + r.stderr), '"omit": ["pool"] with "pool_max_pages" is refused: one or the other')
    # room for resident code: the resident test application (LINEIN: about 1,050 bytes) with 500 more bytes does not fit with a pool and
    # fits without one
    big = lambda d: open(d + '/resident.a99', 'a').write('       BSS  500\n')
    r, size, img = variant('tests/apps/resident', lambda j: j.pop('pool_max_pages', None), big)
    check(r.returncode != 0 and 'page-pool bitmap' in (r.stdout + r.stderr), 'resident code with 500 more bytes does not fit beside a full-size pool bitmap')
    r, size, img = variant('tests/apps/resident', lambda j: (j.pop('pool_max_pages', None), j.update(omit=['pool'])), big)
    check(r.returncode == 0 and size is not None and size > 7680, 'with the pool left out the same kernel fits: %s bytes, more than the 7,680 the bitmap allows' % size)

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

    # the file-name cursor is the cell right after the last character typed
    m, img = asmharness.workbench_ui('<WAIT 10>nAB<WAIT 20>', 200, [])
    row = [m.vram[2 * 80 + c] for c in range(0, 30)]
    end = 8 + 7                     # 'DSK1.AB' starts at column 8: the next cell is 15
    check(row[end] == 0x15 and row[end - 1] == ord('B') and row[end + 1] == 32,
          'the name\'s cursor (glyph >15) is at column %d, right after the B at %d' % (row.index(0x15), end - 1))

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

GROUPS = [('sources', sources), ('dbg', dbg), ('sams16', sams16), ('tipi', tipi), ('hfdccru', hfdccru), ('linein', linein), ('resident', resident), ('poolmax', poolmax), ('trim', trim), ('editorapp', editorapp), ('sourcesdisk', sourcesdisk), ('jumpcheck', jumpcheck), ('fileapi', fileapi), ('dsdd', dsdd), ('dsddworkbench', dsddworkbench), ('editorpages', editorpages), ('reversi', reversi), ('reversiti', reversiti), ('joystick', joystick), ('files2', files2), ('native', native), ('nativemods', nativemods), ('nativedisk', nativedisk), ('tiprograms', tiprograms), ('workbench', workbench), ('workbenchfull', workbenchfull), ('boot', boot), ('refusal', refusal), ('ram', ram), ('keys', keys), ('quit', quit_), ('modules', modules),
          ('files', files), ('browser', browser), ('modes', modes), ('modesquit', modes_quit), ('music', music), ('rom', rom), ('realdsr', realdsr)]

if __name__ == '__main__':
    want = sys.argv[1:] or [g for g, _ in GROUPS]
    for name, fn in GROUPS:
        if name in want:
            print(name); fn()
    print('\n%d failed' % len(FAILS) if FAILS else '\nall passed')
    sys.exit(1 if FAILS else 0)
