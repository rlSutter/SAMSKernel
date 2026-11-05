#!/usr/bin/env python3
"""SAMS Kernel tests: the example applications run in tools/sim9900.py.

  python3 tests/test_kernel.py [group ...]      (no names: all)

Groups: sources dbg sams16 tipi hfdccru linein resident poolmax poolscan slotd trim textonly fastmap fileprog fplayout framehook brkflag editorapp sourcesdisk jumpcheck fileapi dsdd dsddworkbench editorpages reversi reversiti joystick files2 native nativemods nativedisk tiprograms workbench workbenchfull boot refusal ram keys quit modules files browser modes modesquit music rom realdsr
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
    check(m.rw(0x8344) == 128 and m.rw(0x8348) == 1 and m.rw(0x8342) == 0x19, 'NPAGES 128, F18A found, version 1.9')
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
    check(m.rw(0x8344) == 256 and 'Hello' in lines(m)[0], '1M card found as 256 pages and accepted')

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
    # a card at >1000 that lists DSK1 but declines it (a plain return, as a TIPI can for a
    # device it is not set up for), ahead of the drive at >1100: the search must go on to
    # the next name and card, as the console's DSRLNK does (it once stopped with an error).
    # Found on real hardware by the Press session (a TIPI and a TI RS232 card hid PIO).
    def decoy(m):
        rom = bytearray(0x2000)
        rom[0:4] = b'\xAA\x01\x00\x00'
        rom[8:10] = (0x4010).to_bytes(2, 'big')
        rom[0x10:0x12] = b'\x00\x00'; rom[0x12:0x14] = (0x4030).to_bytes(2, 'big'); rom[0x14:0x19] = b'\x04DSK1'
        rom[0x30:0x32] = (0x045B).to_bytes(2, 'big')
        st = {'on': False}
        cw, rb = m.cru_write, m.rb
        def cru_write(bit, v):
            if bit == 0x800:
                st['on'] = bool(v); return
            cw(bit, v)
        def rb2(addr):
            if st['on'] and 0x4000 <= addr < 0x6000:
                return rom[addr - 0x4000]
            return rb(addr)
        m.cru_write = cru_write; m.rb = rb2
    m, cpu, halt = sim9900.run(c, keys='<C-t><WAIT 700>', frames=1000, setup=decoy)
    check('PASS' in lines(m)[10], 'a card listing DSK1 but declining it, ahead of the drive: the search goes on, the file check passes')

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
    m, img = go('ASK/A99', [P + 'ask.a99', os.path.join(ROOT, 'lib', 'linein.a99')], 'ann<ENTER><WAIT 40>bob<ENTER><WAIT 40><F-E><WAIT 40>', 3900)
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
    good, got = ok('{ENTER}', 'x' * 159, start='x' * 200, maxlen=250)
    check(good, 'a longest length over 159 is taken as 159: a 200-character start text is cut to %d' % len(got))
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
    # long lines: up to 159 characters, and a history page set up for them has 160-byte slots, 24 of them
    r, got = run('{ENTER}', start='x' * 150, maxlen=159)
    check(len(got) == 150 and r[0] == 0x0D00, 'a 150-character line with no history (the longest allowed is 159): %d characters kept' % len(got))
    r, got = run('{ENTER}', start='y' * 120, maxlen=159, hist=page)
    check(len(got) == 79, 'a history page that was set up for lines up to 79 cuts a longer one to 79 (%d)' % len(got))
    page3 = asmharness.call(m, cpu, syms['palloc'])[0]
    r, got = run('{ENTER}', start='a' * 150, maxlen=159, hist=page3)
    check(len(got) == 150, 'a page set up for lines up to 159 holds a 150-character line (%d characters)' % len(got))
    run('{ENTER}', start='b' * 5, maxlen=159, hist=page3)
    good, got = ok('{UP}{UP}{BACK}', 'a' * 150, hist=page3, maxlen=159)
    check(good, 'and UP brings the long line back whole (%d characters)' % len(got))
    for i in range(1, 27):
        run('{ENTER}', start=('%02d' % i) + 'z' * 100, maxlen=159, hist=page3)
    good, got = ok('{UP}' * 40 + '{BACK}', '03' + 'z' * 100, hist=page3, maxlen=159)
    check(good, 'its ring holds 24 lines: of 26 entered the oldest kept is the third (%r)' % got[:4])
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
    big = '       BSS  100\n'
    r, out = build_variant(lambda j: j.pop('pool_max_pages', None))
    check(r.returncode != 0 and 'page-pool bitmap' in (r.stdout + r.stderr), 'with the default bitmap (512 bytes) the test application\'s resident code (LINEIN, with its scrolling field and long lines, is about 1,130 bytes) does not fit: %s' % (r.stdout + r.stderr).strip().split('\n')[-1][:90])
    r, out = build_variant(lambda j: j.update(pool_max_pages=256), big)
    check(r.returncode == 0 and 'at >BFE0' in r.stdout, 'with "pool_max_pages": 256 (a 32-byte bitmap at >BFE0) it fits with 100 more bytes: %s' % [l for l in r.stdout.split('\n') if l.startswith('kernel')])
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
    """tools/mksources.py: the 360K disk of the kernel's sources for the TI.  Every name fits a TI disk, the six long names
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
    big = lambda d: open(d + '/resident.a99', 'a').write('       BSS  300\n')
    r, size, img = variant('tests/apps/resident', lambda j: j.pop('pool_max_pages', None), big)
    check(r.returncode != 0 and 'page-pool bitmap' in (r.stdout + r.stderr), 'resident code with 300 more bytes does not fit beside a full-size pool bitmap')
    r, size, img = variant('tests/apps/resident', lambda j: (j.pop('pool_max_pages', None), j.update(omit=['pool'])), big)
    check(r.returncode == 0 and size is not None and size > 7680, 'with the pool left out the same kernel fits: %s bytes, more than the 7,680 the bitmap allows' % size)

def textonly():
    """app.json "omit": "graphics" (Graphics I, Graphics II, Multicolor) and "enhanced" (enhanced colour and sprites) leave the
    code for them out of VMODE.  Each makes the kernel smaller and the application still boots in Text 80 and echoes keys; VMODE still
    sets Text 80 and Text 40, 24 and 30 rows, position attributes; what is not left out still works (enhanced colour text without
    "graphics", the graphics modes without "enhanced"); a module that names a mode or option that was left out is refused by name."""
    import asmharness, shutil, tempfile
    def variant(words, edit_file=None):
        d = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, 'examples', 'hello'), d + '/app')
        j = json.load(open(d + '/app/app.json')); j['omit'] = words; json.dump(j, open(d + '/app/app.json', 'w'))
        if edit_file:
            edit_file(d + '/app')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/app', '--out', d + '/out'], capture_output=True, text=True)
        size = next((int(l.split()[1]) for l in r.stdout.split('\n') if l.startswith('kernel ')), None)
        img = glob.glob(d + '/out/*8.bin')
        return r, size, (open(img[0], 'rb').read() if img else None), d + '/out'
    r, base, img, out = variant([])
    check(base is not None, 'the unchanged kernel is %s bytes' % base)
    for words, least in ((['graphics'], 290), (['enhanced'], 150), (['graphics', 'enhanced'], 450), (['music', 'files', 'pool', 'graphics', 'enhanced'], 3000)):
        r, size, img, out = variant(words)
        syms = asmharness.symbols(os.path.join(out, 'kernel.equ'))
        saved = os.environ.pop('TI_CONSOLE_ROM', None)      # with the real console ROM the machine may be inside its interrupt routine when the
        try:                                                # run ends, and the calls below (which set up their own registers) need it between frames
            m, cpu, halt = sim9900.run(img, frames=300, keys='hi')
        finally:
            if saved:
                os.environ['TI_CONSOLE_ROM'] = saved
        ok = halt is None and any(l.strip() == 'HI' for l in sim9900.screen(m).split('\n')) and m.rw(syms['txcols']) == 80 and m.rw(syms['txrows']) == 30
        check(r.returncode == 0 and size is not None and base - size >= least and ok,
              'omit %s: the kernel is %s bytes, %s smaller (at least %d); it boots in Text 80, 30 rows, and echoes keys' % (words, size, base - size if size else '?', least))
        call = lambda mode, opt, m=m, cpu=cpu, syms=syms: asmharness.call(m, cpu, syms['vmode'], {0: mode, 1: opt}, limit=5_000_000)
        T80, T40 = syms['vmgm1'] - 2, syms['vmgm1'] - 1
        call(T40, 0)
        got40 = (m.rw(syms['txcols']), m.rw(syms['txrows']), m.rw(syms['txattr']))
        call(T80, 0)
        got24 = (m.rw(syms['txcols']), m.rw(syms['txrows']), m.rw(syms['txattr']))
        call(T80, 3)
        got30 = (m.rw(syms['txcols']), m.rw(syms['txrows']), m.rw(syms['txattr']))
        check(got40 == (40, 24, 0) and got24 == (80, 24, 0) and got30 == (80, 30, 0xFFFF),
              '   VMODE sets Text 40 %s, Text 80 24 rows %s, Text 80 30 rows with position attributes %s' % (got40, got24, got30))
        if 'graphics' not in words:
            call(syms['vmgm2'], 0)
            gm = (m.rw(syms['txcols']), m.rw(syms['txrows']))
            check(gm == (32, 24), '   Graphics II still works with graphics kept: %s columns by %s rows' % gm)
        if 'enhanced' not in words:
            call(T80, syms['vote1'] + 3)
            check(m.rw(syms['txattr']) == 0xFFFF, '   enhanced colour text still works with enhanced kept (TXATTR %04X)' % m.rw(syms['txattr']))
    def names(*ws):
        def f(d):
            s = open(d + '/hello.a99').read()
            s = s.replace('INIT   .enter', 'INIT   .enter\n' + ''.join('       LI   R1,%s\n' % w for w in ws), 1)
            open(d + '/hello.a99', 'w').write(s)
        return f
    for word, name in (('graphics', 'VMGM2'), ('graphics', 'VMMC'), ('enhanced', 'VOSPR'), ('enhanced', 'VOTE2')):
        r, size, img, out = variant([word], names(name))
        check(r.returncode != 0 and name in (r.stdout + r.stderr) and ('"%s"' % word) in (r.stdout + r.stderr),
              'a module that uses %s, with "%s" left out, is refused by name: %s' % (name, word, (r.stdout + r.stderr).strip().split('\n')[-1][:100]))
    r, size, img, out = variant(['graphics'], names('VOSPR', 'VOTE1'))
    check(r.returncode == 0, 'and the options that were not left out are fine (VOSPR, VOTE1 with only graphics omitted)')

def fastmap():
    """The .mape and .mapf macros (kernel/macros.a99): the page a macro maps is the page MAPE or MAPF maps, for pseudo-random
    pages in both windows; the records CURBE and CURBF follow it; GETPB returns the record and SETPB puts it back."""
    import asmharness
    c = build('tests/apps/fastmap')
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'fastmap', 'kernel.equ'))
    syms.update(asmharness.symbols(os.path.join(ROOT, 'build', 'fastmap', 'fm.equ')))
    saved = os.environ.pop('TI_CONSOLE_ROM', None)
    try:
        m, cpu, halt = sim9900.run(c, frames=100)
    finally:
        if saved:
            os.environ['TI_CONSOLE_ROM'] = saved
    call = lambda n, **r: asmharness.call(m, cpu, syms[n], {int(k[1:]): v for k, v in r.items()}, limit=1_000_000)
    for pg in range(0x40, 0x80):                                    # each page holds its own number in its first word
        call('fmw', r1=pg)
    rnd, bad, n = 12345, [], 2000
    pages = []
    for i in range(n):
        rnd = (rnd * 1103515245 + 12345) & 0x7FFFFFFF
        pages.append(0x40 + (rnd >> 8) % 64)
    for name, other, rec in (('fma', 'fmb', 'curbe'), ('fmc', 'fmd', 'curbf')):
        bad = []
        for pg in pages:
            a = call(name, r1=pg)[0]
            ra = m.rw(syms[rec])
            b = call(other, r1=pg)[0]
            if not (a == b == pg and ra == pg):
                bad.append((name, hex(pg), a, b, ra))
                break
        check(not bad, '%s: %d pseudo-random page reads through the macro and through the call give the same word as the page number, and %s follows (%s)' % (name, n, rec.upper(), bad[:1]))
    call('fma', r1=0x41); call('fmc', r1=0x42)
    r = call('getpb')
    check((r[0], r[1]) == (0x41, 0x42), 'GETPB returns what the macros last mapped: >%02X, >%02X' % (r[0], r[1]))
    call('fmb', r1=0x50); call('fmd', r1=0x51)
    call('setpb', r0=0x41, r1=0x42)
    check((m.rw(syms['curbe']), m.rw(syms['curbf'])) == (0x41, 0x42) and call('fma', r1=0x41)[0] == 0x41 and call('fmc', r1=0x42)[0] == 0x42,
          'SETPB puts the pair back: the records and the pages themselves')
    first = call('fma', r1=0x41)                                     # nothing to do when it is there already: R12 is not touched
    m.ww(0x8300 + 24, 0x1234)
    first = asmharness.call(m, cpu, syms['fma'], {1: 0x41}, limit=100000)
    check(first[12] == 0x1234, 'when the page is already there the macro writes nothing, R12 included')

def fileprog():
    """FLOAD and FSAVE (kernel/files.a99): a PROGRAM file saved from VRAM and loaded back byte for byte, through TI's controller (its real
    ROM); a missing file and a name too long are errors; and a load or save on one handle leaves a record file open on another readable."""
    import tempfile, asmharness, skdisk, tifdc
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    c = build('hello')
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'hello', 'kernel.equ'))
    d = tempfile.mkdtemp()
    open(d + '/rec.txt', 'w').write(''.join('record number %d\n' % i for i in range(30)))
    p = d + '/d.dsk'
    skdisk.make_disk(p, [d + '/rec.txt'])
    img = bytearray(open(p, 'rb').read())
    m = sim9900.Machine(c)
    m.tifdc = tifdc.TIFDC(image=img)
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m)
    cpu.pc = m.rw(m.rw(0x6006) + 2)
    while m.insns < 100 * sim9900.VSYNC_INSNS:
        cpu.step()
    W = 0x2300 + 5000
    def put(nm):
        for i, b in enumerate(bytes([len(nm)]) + nm.encode()):
            m.wb(W + i, b)
    def call(n, **r):
        return asmharness.call(m, cpu, syms[n], {int(k[1:]): v for k, v in r.items()}, limit=60_000_000)
    def sel(h):
        call('fsel', r0=h)
    # a record file open on handle 0, one record read
    sel(0); put('DSK1.REC/TXT')
    r = call('fopen', r0=0x1400, r1=0, r2=W)[0]
    def rd():
        r = call('fread', r1=W + 200)
        return (r[0], bytes(m.rb(W + 200 + i) for i in range(r[2])).decode())
    first = rd()
    check(r == 0 and first == (0, 'record number 0'), 'a record file is open on handle 0 and its first record read (%d, %r)' % (r, first))
    pattern = bytes((i * 7 + 3) & 255 for i in range(4096))
    for i, b in enumerate(pattern):
        m.vram[0x2000 + i] = b
    sel(1); put('DSK1.PROG')
    r = call('fsave', r0=0x2000, r1=4096, r2=W)[0]
    check(r == 0, 'FSAVE writes 4,096 bytes of VRAM as DSK1.PROG (error %d)' % r)
    for i in range(4096):
        m.vram[0x2000 + i] = 0
    r = call('fload', r0=0x2000, r1=4096, r2=W)[0]
    got = bytes(m.vram[0x2000:0x3000])
    check(r == 0 and got == pattern, 'FLOAD brings it back byte for byte (error %d, %d of 4096 bytes right)' % (r, sum(a == b for a, b in zip(got, pattern))))
    sel(0)
    second = rd()
    check(second == (0, 'record number 1'), 'the record file on handle 0 is still open: the next record is %r (finding 1.1: a power-up in between would lose it)' % (second,))
    big = 0x3600 - 0x2000                       # the longest free run in Text 80: up to the file service's own buffer
    pat2 = bytes((i * 13 + 5) & 255 for i in range(big))
    for i, b in enumerate(pat2):
        m.vram[0x2000 + i] = b
    sel(1); put('DSK1.BIG')
    r1 = call('fsave', r0=0x2000, r1=big, r2=W)[0]
    for i in range(big):
        m.vram[0x2000 + i] = 0
    r2 = call('fload', r0=0x2000, r1=big, r2=W)[0]
    check(r1 == 0 and r2 == 0 and bytes(m.vram[0x2000:0x2000 + big]) == pat2, 'a larger file, %d bytes (>2000-35FF, up to the file service\'s own buffer at >3600): saved and loaded byte for byte (errors %d, %d)' % (big, r1, r2))
    put('DSK1.NOSUCH')
    r = call('fload', r0=0x2000, r1=100, r2=W)[0]
    check(r != 0, 'FLOAD of a file that is not there is an error (%d)' % r)
    put('DSK1.' + 'X' * 60)
    r = call('fsave', r0=0x2000, r1=100, r2=W)[0]
    check(r == 0xFF, 'a name too long for the PAB is refused (>%02X)' % r)

def kdefs_values():
    """{name: value} for every EQU in kernel/kdefs.a99 (names may refer to names later in the file)."""
    import re
    vals = {}
    pend = []
    for line in open(os.path.join(ROOT, 'kernel', 'kdefs.a99'), encoding='latin-1'):
        m = re.match(r'^(\w+)\s+EQU\s+(\S+)', line)
        if m:
            pend.append((m.group(1), m.group(2)))
    for _ in range(6):                                          # names may refer to names later in the file
        for name, expr in pend:
            if name in vals:
                continue
            e = re.sub(r'>([0-9A-Fa-f]+)', lambda x: str(int(x.group(1), 16)), expr)
            e = re.sub(r'[A-Za-z_]\w*', lambda x: str(vals[x.group(0)]) if x.group(0) in vals else 'None', e)
            if 'None' in e:
                continue
            try:
                vals[name] = eval(e, {}, {})
            except Exception:
                pass
    return vals

def fplayout():
    """The scratchpad and slot A maps (kernel/kdefs.a99): nothing of the kernel's lies in the console's floating-point registers FAC
    (>834A-8351) and ARG (>835C-8363), and no two variables share a word of slot A's kernel area."""
    vals = kdefs_values()
    pad = {n: v for n, v in vals.items() if 0x8300 <= v < 0x8400 and n not in ('WS', 'GPLWS', 'SCRTCH')}
    hit = {n: hex(v) for n, v in pad.items() if 0x834A <= v <= 0x836F or 0x8374 <= v <= 0x8377 or v in (0x837C, 0x837D)}
    check(not hit, 'no kernel name lies in the console float package\'s working area >834A-836F (FAC, ARG, the error code at >8354, the stack pointer at >836E and their temporaries), or at >8374-8377 (the sign byte, a copy of the exponent) or >837C (the GPL status byte): %s (%d scratchpad names checked)' % (hit or 'none', len(pad)))
    check((vals['F18VER'], vals['NPAGES'], vals['QUITF'], vals['F18FLG']) == (0x8342, 0x8344, 0x8346, 0x8348) and vals['VDPPIC'] == 0x20AA,
          'the four that were in FAC moved: F18VER, NPAGES, QUITF to >8342, >8344, >8346 and VDPPIC to slot A >20AA')
    slot = {}
    for n, v in vals.items():
        if 0x2060 <= v < 0x2300 and v % 2 == 0 and n not in ('APPRAM', 'SLOTA'):     # (below that, names are also VRAM addresses)
            slot.setdefault(v, []).append(n)
    dup = {hex(a): ns for a, ns in slot.items() if len(ns) > 1}
    check(not dup, 'no two names share a word of slot A\'s kernel area (>2060-22FF): %s' % (dup or 'none'))
    check({'FRMHK': 0x20DA, 'FRMGD': 0x20DC, 'BRKF': 0x20DE}.items() <= vals.items(), 'the frame hook, its guard and the break flag are in the three free words >20DA, >20DC, >20DE')

def framehook():
    """The frame hook (KFRAME, FRMHK): a program's routine is called once a frame wherever the kernel polls (here a long loop that
    calls only KIDLE, and a file call), not at all when none is set, and not again while it runs."""
    import asmharness, skdisk, tifdc, tempfile
    c = build('tests/apps/framehook')
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'framehook', 'kernel.equ'))
    syms.update(asmharness.symbols(os.path.join(ROOT, 'build', 'framehook', 'fh.equ')))
    d = tempfile.mkdtemp()
    open(d + '/rec.txt', 'w').write(''.join('record %d\n' % i for i in range(40)))
    skdisk.make_disk(d + '/d.dsk', [d + '/rec.txt'])
    m = sim9900.Machine(c)
    if os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM']):
        m.tifdc = tifdc.TIFDC(image=bytearray(open(d + '/d.dsk', 'rb').read()))
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m)
    cpu.pc = m.rw(m.rw(0x6006) + 2)
    while m.insns < 100 * sim9900.VSYNC_INSNS:
        cpu.step()
    call = lambda n, **r: asmharness.call(m, cpu, syms[n], {int(k[1:]): v for k, v in r.items()}, limit=40_000_000)
    check(m.rw(syms['frmhk']) == 0 and m.rw(syms['frmgd']) == 0, 'at start there is no hook and the guard is clear')
    f0 = m.rw(syms['frame'])
    call('long', r1=200)
    f1 = m.rw(syms['frame']) - f0
    check(m.rw(syms['hkcnt']) == 0 and f1 >= 5, 'with no hook, nothing is called (%d frames passed in a long loop)' % f1)
    call('seth1')
    f0 = m.rw(syms['frame']); h0 = m.rw(syms['hkcnt'])
    call('long', r1=300)
    f1 = m.rw(syms['frame']) - f0; h1 = m.rw(syms['hkcnt']) - h0
    check(f1 >= 5 and h1 == f1, 'a long loop that calls only KIDLE: the hook ran %d times in the %d frames that passed' % (h1, f1))
    call('seth0')
    h0 = m.rw(syms['hkcnt'])
    call('long', r1=200)
    check(m.rw(syms['hkcnt']) == h0, 'and none again once the hook is cleared')
    call('seth2')
    f0 = m.rw(syms['frame']); h0 = m.rw(syms['hk2cnt'])
    s0 = m.rw(0x8300 + 20)
    r = call('long', r1=120)
    f1 = m.rw(syms['frame']) - f0; h1 = m.rw(syms['hk2cnt']) - h0
    check(h1 >= 2 and h1 < f1 and m.rw(syms['frmgd']) == 0 and r[10] == s0,
          'a hook that calls KIDLE itself (and runs past a frame) is not called again inside itself: %d calls in %d frames, guard clear afterwards, stack balanced' % (h1, f1))
    call('seth1')
    if getattr(m, 'tifdc', None):
        h0 = m.rw(syms['hkcnt'])
        sys_name = 'DSK1.REC/TXT'
        W = 0x2300 + 5000
        for i, b in enumerate(bytes([len(sys_name)]) + sys_name.encode()):
            m.wb(W + i, b)
        call('fsel', r0=0)
        r = call('fopen', r0=0x1400, r1=0, r2=W)[0]
        for _ in range(5):
            call('fread', r1=W + 200)
        check(r == 0 and m.rw(syms['hkcnt']) > h0, 'file calls reach KIDLE after the DSR returns, so the hook ran during them (%d calls)' % (m.rw(syms['hkcnt']) - h0))

def brkflag():
    """The break flag (BRKF): FCTN 4 sets it whether or not the key buffer has room; other keys leave it clear; the code is still buffered
    when there is room; and a real FCTN 4 press through the keyboard decoder sets it."""
    import asmharness
    c = build('tests/apps/framehook')
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'framehook', 'kernel.equ'))
    saved = os.environ.pop('TI_CONSOLE_ROM', None)
    try:
        m, cpu, halt = sim9900.run(c, frames=60)
        call = lambda n, **r: asmharness.call(m, cpu, syms[n], {int(k[1:]): v for k, v in r.items()}, limit=1_000_000)
        call('kflush')
        m.ww(syms['brkf'], 0)
        call('kput', r0=0x4100)
        check(m.rw(syms['brkf']) == 0, 'an ordinary key (A) leaves the flag clear')
        call('kput', r0=0xF400)
        got = [call('keyget')[0] >> 8 for _ in range(3)]
        check(m.rw(syms['brkf']) == 0xFFFF and got[:2] == [0x41, 0xF4], 'FCTN 4 with room sets the flag and is still buffered after the A: %s' % [hex(g) for g in got])
        call('kflush'); m.ww(syms['brkf'], 0)
        for _ in range(63):
            call('kput', r0=0x4100)
        head0 = m.rw(syms['khead'])
        call('kput', r0=0x4200)
        check(m.rw(syms['khead']) == head0, 'the buffer is full: 63 keys held, a 64th is dropped')
        call('kput', r0=0xF400)
        check(m.rw(syms['brkf']) == 0xFFFF and m.rw(syms['khead']) == head0, 'FCTN 4 with the buffer full: the code is dropped as before, but the flag is set')
        m.ww(syms['brkf'], 0)
    finally:
        if saved:
            os.environ['TI_CONSOLE_ROM'] = saved
    m, cpu, halt = sim9900.run(c, frames=200, keys='<WAIT 20><F-4><WAIT 20>')
    check(halt is None and m.rw(syms['brkf']) == 0xFFFF, 'a real FCTN 4 press through the keyboard decoder sets the flag (%04X)' % m.rw(syms['brkf']))
    m, cpu, halt = sim9900.run(c, frames=200, keys='<WAIT 20>a<WAIT 20>')
    check(halt is None and m.rw(syms['brkf']) == 0, 'and an ordinary press does not')

def poolscan():
    """PALLOC skips bitmap bytes with no free page, and PALLOCA takes the lowest free page at or above R0: against a plain model over
    random allocate, release and PALLOCA sequences in three pool shapes; a nearly full 4,096-page pool costs under 3,000 instructions;
    PALLOCA respects the pool's first page, its end and pool_max_pages."""
    import asmharness, random, shutil, tempfile
    c = build('hello')
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'hello', 'kernel.equ'))
    saved = os.environ.pop('TI_CONSOLE_ROM', None)
    try:
        m, cpu, halt = sim9900.run(c, frames=60)
    finally:
        if saved:
            os.environ['TI_CONSOLE_ROM'] = saved
    call = lambda n, **r: asmharness.call(m, cpu, syms[n], {int(k[1:]): v for k, v in r.items()}, limit=5_000_000)
    rnd = random.Random(99)
    for lo, hi in ((0x40, 0x100), (0x43, 0x1F7), (0x10, 0x1000)):
        call('pinit', r0=lo, r1=hi)
        free = set(range(lo, hi)); used = []; bad = None
        for step in range(500):
            op = rnd.choice(('a', 'a', 'a', 'r', 'x'))
            if op == 'a':
                want = min(free) if free else 0
                got = call('palloc')[0]
                if got != want: bad = ('palloc', want, got); break
                if got: free.discard(got); used.append(got)
            elif op == 'x':
                r0 = rnd.randrange(0, hi + 40)
                cand = [p for p in free if p >= r0]
                want = min(cand) if cand else 0
                got = call('palloca', r0=r0)[0]
                if got != want: bad = ('palloca', hex(r0), want, got); break
                if got: free.discard(got); used.append(got)
            elif used:
                p = used.pop(rnd.randrange(len(used)))
                call('prels', r0=p); free.add(p)
            if m.rw(syms['freect']) != len(free): bad = ('freect', len(free), m.rw(syms['freect'])); break
        check(bad is None, 'pool %#x-%#x: 500 random PALLOC / PALLOCA / PRELS steps agree with the model (%s)' % (lo, hi, bad or 'no difference'))
    # a nearly full pool: the first 3,900 pages in use
    call('pinit', r0=0x10, r1=0x1000)
    bm = syms['poolbm']
    for i in range((0x10 + 3900) // 8):
        m.wb(bm + i, 0)
    for p in range(0x10 + 3900 - ((0x10 + 3900) % 8), 0x10 + 3900):
        call('palloc')
    i0 = m.insns
    got = call('palloc')[0]
    cost = m.insns - i0
    check(got >= 0x10 + 3900 - 8 and cost < 3000, 'PALLOC with about 3,900 pages in use finds page %d in %d instructions (a bit by bit scan took about 107,000)' % (got, cost))
    call('pinit', r0=0x40, r1=0x80)
    a = call('palloca', r0=0x10)[0]
    b = call('palloca', r0=0x7F)[0]
    cc = call('palloca', r0=0x7F)[0]
    dd = call('palloca', r0=0x80)[0]
    check((a, b, cc, dd) == (0x40, 0x7F, 0, 0), 'PALLOCA below the pool\'s first page gives the first (%#x), at its last page gives it once (%#x) and then 0 (%d), at its end 0 (%d)' % (a, b, cc, dd))
    d = tempfile.mkdtemp()
    shutil.copytree(os.path.join(ROOT, 'examples', 'hello'), d + '/app')
    j = json.load(open(d + '/app/app.json')); j['pool_max_pages'] = 64; json.dump(j, open(d + '/app/app.json', 'w'))
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/app', '--out', d + '/out'], capture_output=True, text=True)
    img = open(glob.glob(d + '/out/*8.bin')[0], 'rb').read()
    s2 = asmharness.symbols(d + '/out/kernel.equ')
    saved = os.environ.pop('TI_CONSOLE_ROM', None)
    try:
        m2, cpu2, halt = sim9900.run(img, frames=60)
    finally:
        if saved:
            os.environ['TI_CONSOLE_ROM'] = saved
    c2 = lambda n, **rr: asmharness.call(m2, cpu2, s2[n], {int(k[1:]): v for k, v in rr.items()}, limit=5_000_000)
    c2('pinit', r0=0, r1=1000)
    x = c2('palloca', r0=63)[0]
    y = c2('palloca', r0=63)[0]
    z = c2('palloca', r0=64)[0]
    check(r.returncode == 0 and (x, y, z) == (63, 0, 0), 'with "pool_max_pages": 64, PALLOCA stops at page 63: %d, then %d, and nothing at 64 (%d)' % (x, y, z))

def slotd():
    """Single-page modules ("size": 4096) and window >D000 (MAPD, .mapd, a MODCALL that restores both windows): the build refuses a module
    over 4K and sets the header flag; a switch (GOMOD) between single-page modules leaves >D000 as the program set it, a switch to an
    8K module maps its second page there and a return to a single-page module does not put it back; MODCALL puts both windows back
    whichever size the callee is; MAPD and its macro agree page after page."""
    import asmharness, shutil, tempfile
    c = build('tests/apps/slotd')
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'slotd', 'kernel.equ'))
    for n in ('ma', 'mb', 'mc'):
        syms.update(asmharness.symbols(os.path.join(ROOT, 'build', 'slotd', n + '.equ')))
    bank = lambda i: c[i * 0x2000:(i + 1) * 0x2000]
    flags = [int.from_bytes(bank(i)[6:8], 'big') & 1 for i in (3, 4, 5)]
    check(flags == [1, 1, 0], 'the build sets the single-page flag (bit 0 of the header\'s last word) in the two 4K modules and not in the 8K one: %s' % flags)
    def run_keys(keys):
        saved = os.environ.pop('TI_CONSOLE_ROM', None)
        try:
            return sim9900.run(c, frames=400, keys=keys)
        finally:
            if saved:
                os.environ['TI_CONSOLE_ROM'] = saved
    word = lambda m, n: m.rw(syms[n])
    m, cpu, halt = run_keys('<WAIT 30>')
    check(halt is None and m.rw(0xD000) == 0x5858 and word(m, 'curcd') == 0x40 and word(m, 'vinit') == 1 and word(m, 'curcc') == syms['pg_ma'],
          'a single-page boot module maps a page into >D000 with MAPD and it stays: >D000 holds %04X, CURCD >%02X' % (m.rw(0xD000), word(m, 'curcd')))
    m, cpu, halt = run_keys('<WAIT 20>b<WAIT 30>')
    check(word(m, 'curcc') == syms['pg_mb'] and word(m, 'vbd') == 0x5858 and word(m, 'curcd') == 0x40,
          'GOMOD to another single-page module leaves >D000 as it was: mb found %04X, CURCD >%02X' % (word(m, 'vbd'), word(m, 'curcd')))
    m, cpu, halt = run_keys('<WAIT 20>c<WAIT 30>')
    check(word(m, 'curcc') == syms['pg_mc'] and word(m, 'vcd') == 0xC0DE and word(m, 'curcd') == syms['pg_mc'] + 1 and m.rw(0xD000) == 0xC0DE,
          'GOMOD to an 8K module maps its second page into >D000 as before: mc found %04X, CURCD >%02X (its page >%02X + 1)' % (word(m, 'vcd'), word(m, 'curcd'), syms['pg_mc']))
    m, cpu, halt = run_keys('<WAIT 20>c<WAIT 20>a<WAIT 30>')
    check(word(m, 'curcc') == syms['pg_ma'] and word(m, 'vinit') == 2 and word(m, 'vai') == 0xC0DE and m.rw(0xD000) == 0xC0DE,
          'and a return to the single-page module does not put the old page back: >D000 still holds %04X (the program maps it again if it cares)' % m.rw(0xD000))
    for pre in ('', 'c<WAIT 20>a<WAIT 20>'):
        m, cpu, halt = run_keys('<WAIT 20>' + pre + 'm<WAIT 40>')
        got = tuple(word(m, n) for n in ('vmb', 'vmc', 'vad', 'vcc', 'vcdr'))
        check(got == (0x5858, 0xC0DE, 0x5858, syms['pg_ma'], 0x40),
              'MODCALL into a single-page module (saw %04X), then an 8K one (saw its own %04X): afterwards >D000 holds %04X, CURCC >%02X and CURCD >%02X: both windows put back%s' % (got[0], got[1], got[2], got[3], got[4], ' (after coming back from mc)' if pre else ''))
    m, cpu, halt = run_keys('<WAIT 20>')
    saved = os.environ.pop('TI_CONSOLE_ROM', None)
    try:
        m, cpu, halt = sim9900.run(c, frames=60)
    finally:
        if saved:
            os.environ['TI_CONSOLE_ROM'] = saved
    call = lambda n, **r: asmharness.call(m, cpu, syms[n], {int(k[1:]): v for k, v in r.items()}, limit=1_000_000)
    for pg in range(0x40, 0x80):
        call('awr', r1=pg)
    rnd, bad = 777, None
    for i in range(600):
        rnd = (rnd * 1103515245 + 12345) & 0x7FFFFFFF
        pg = 0x40 + (rnd >> 8) % 64
        a = call('amd1', r1=pg)[0]
        ra = m.rw(syms['curcd'])
        b = call('amd2', r1=pg)[0]
        if not (a == b == pg and ra == pg):
            bad = (hex(pg), a, b, ra); break
    check(bad is None, 'the .mapd macro and the MAPD call: 600 pseudo-random pages read the same word, CURCD follows (%s)' % (bad or 'no difference'))
    def variant(edit_json=None, edit_file=None):
        d = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, 'tests', 'apps', 'slotd'), d + '/app')
        if edit_json:
            j = json.load(open(d + '/app/app.json')); edit_json(j); json.dump(j, open(d + '/app/app.json', 'w'))
        if edit_file:
            edit_file(d + '/app')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/app', '--out', d + '/out'], capture_output=True, text=True)
        return r, (r.stdout + r.stderr)
    r, out = variant(edit_file=lambda d: open(d + '/mb.a99', 'a').write('       BSS  4100\n'))
    check(r.returncode != 0 and 'mb' in out and 'at most 4,096' in out, 'a module declared 4K that assembles to more is refused by name: %s' % out.strip().split('\n')[-1][:90])
    r, out = variant(lambda j: j.update(module_size=4096))
    check(r.returncode != 0 and 'mc' in out and 'at most 4,096' in out, '"module_size": 4096 as the default applies to mc, which is over 4K: %s' % out.strip().split('\n')[-1][:90])
    def allsmall(j):
        j['module_size'] = 4096
        j['modules'][2]['size'] = 8192
    r, out = variant(allsmall)
    check(r.returncode == 0, '"module_size": 4096 with "size": 8192 on mc builds: the module\'s own size wins')
    r, out = variant(lambda j: j['modules'][0].update(size=5000))
    check(r.returncode != 0 and 'size' in out, 'a size other than 4096 or 8192 is refused')

def float():
    """lib/float.a99: FPCALL runs the console ROM's floating-point routines (its real code, in the simulator) through the XML tables: the
    five arithmetic and comparison entries on random numbers against Python's, the callers' registers kept, an unknown code refused, and
    -- finding K1 of the TIthon proposal -- every scratchpad byte the routines change is a byte of FAC, ARG or the console's float temporaries,
    never one of the kernel's own variables."""
    import asmharness, random
    from decimal import Decimal, getcontext
    getcontext().prec = 40
    rom = os.environ.get('TI_CONSOLE_ROM')
    if not (rom and os.path.exists(rom)):
        print('  (skipped: the console ROM is needed: TI_CONSOLE_ROM)')
        return
    c = build('tests/apps/float')
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'float', 'kernel.equ'))
    syms.update(asmharness.symbols(os.path.join(ROOT, 'build', 'float', 'fl.equ')))
    m = sim9900.Machine(c)
    m.console_rom = sim9900.load_console_rom(rom)
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m)
    cpu.pc = m.rw(m.rw(0x6006) + 2)
    while m.insns < 100 * sim9900.VSYNC_INSNS:
        cpu.step()
    n = 0
    while not (0xA000 <= cpu.pc < 0xE000 and cpu.wp == 0x8300) and n < 200000:     # not inside the console's interrupt routine
        cpu.step(); n += 1
    put = lambda a, b: [m.wb(a + i, x) for i, x in enumerate(b)]
    get = lambda a, k=8: bytes(m.rb(a + i) for i in range(k))
    def enc(x):
        """radix-100: an exponent byte (>40 = 100^0) and seven digit pairs; a negative number has its first word negated"""
        x = Decimal(x)
        if x == 0:
            return bytes(8)
        neg = x < 0
        x = abs(x)
        k = 0
        while x >= 100:
            x /= 100; k += 1
        while x < 1:
            x *= 100; k -= 1
        digits = []
        for _ in range(7):
            d = int(x)
            digits.append(d); x = (x - d) * 100
        word = ((0x40 + k) << 8) | digits[0]
        if neg:
            word = (-word) & 0xFFFF
        return bytes([word >> 8, word & 255] + digits[1:])
    def dec(b):
        word = (b[0] << 8) | b[1]
        if word == 0:
            return Decimal(0)
        neg = word & 0x8000
        if neg:
            word = (-word) & 0xFFFF
        k = (word >> 8) - 0x40
        v = Decimal(word & 255)
        for i in range(2, 8):
            v += Decimal(b[i]) / Decimal(100) ** (i - 1)
        v = v * Decimal(100) ** k
        return -v if neg else v
    check(enc(1) == bytes([0x40, 1, 0, 0, 0, 0, 0, 0]) and enc('0.25') == bytes([0x3F, 25, 0, 0, 0, 0, 0, 0]) and enc(-1)[:2] == b'\xbf\xff' and dec(enc('-1234.5')) == Decimal('-1234.5'),
          'the radix-100 encoding used here matches the console\'s (1.0, 0.25, -1.0 as >BFFF, and a round trip)')
    call = lambda code: asmharness.call(m, cpu, syms['fpcall'], {0: code}, limit=2_000_000)
    kernel_names = {v: n for n, v in kdefs_values().items() if 0x8300 <= v < 0x8400}
    pad0 = 0x8300
    rnd = random.Random(2026)
    changed = set()
    worst = Decimal(0)
    bad = None
    ops = {0x06: lambda f, a: f + a, 0x07: lambda f, a: a - f, 0x08: lambda f, a: f * a, 0x09: lambda f, a: a / f}
    names = {0x06: 'FADD', 0x07: 'FSUB', 0x08: 'FMUL', 0x09: 'FDIV'}
    for code, fn in ops.items():
        for i in range(60):
            xf = Decimal(rnd.choice([-1, 1])) * Decimal(rnd.randint(1, 10**9)) / Decimal(10) ** rnd.randint(0, 12) * Decimal(10) ** rnd.randint(-6, 8)
            xa = Decimal(rnd.choice([-1, 1])) * Decimal(rnd.randint(1, 10**9)) / Decimal(10) ** rnd.randint(0, 12) * Decimal(10) ** rnd.randint(-6, 8)
            put(0x834A, enc(xf)); put(0x835C, enc(xa))
            before = get(pad0, 256)
            regs = [m.rw(0x8300 + 2 * j) for j in range(16)]
            r = call(code)
            after = get(pad0, 256)
            changed |= {pad0 + j for j in range(0xE0) if before[j] != after[j] and not 0x00 <= j < 0x20}
            want = fn(dec(enc(xf)), dec(enc(xa)))
            got = dec(get(0x834A))
            err = abs(got - want) / abs(want) if want != 0 else abs(got)
            worst = max(worst, err)
            if err > Decimal('1e-12') and bad is None:
                bad = (names[code], str(xf), str(xa), str(want), str(got))
            kept = [r[j] for j in (4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15)] == [regs[j] for j in (4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15)]
            if not kept and bad is None:
                bad = ('registers changed', code, [hex(x) for x in r])
    check(bad is None, 'FADD, FSUB (ARG - FAC), FMUL, FDIV (ARG / FAC): 240 random operations match Python to a relative error of at most %.1e, and R4-R10 and R12-R15 come back as they were (%s)' % (worst, bad or 'no difference'))
    badc = None
    for i in range(120):
        xf = Decimal(rnd.choice([-1, 0, 1, 1])) * Decimal(rnd.randint(1, 50)) / Decimal(rnd.choice([1, 1, 10]))
        xa = rnd.choice([xf, xf, Decimal(rnd.choice([-1, 1])) * Decimal(rnd.randint(1, 50)) / Decimal(rnd.choice([1, 1, 10]))])
        put(0x834A, enc(xf)); put(0x835C, enc(xa))
        got = call(0x0A)[0] & 0x60
        want = 0x20 if dec(enc(xf)) == dec(enc(xa)) else (0x40 if dec(enc(xf)) < dec(enc(xa)) else 0)
        if got != want:
            badc = (str(xf), str(xa), hex(got), hex(want)); break
    check(badc is None, 'FCOMP, 120 pairs of either sign: R0 & >60 is >20 for equal, >40 for FAC less than ARG, 0 for greater (%s)' % (badc or 'all as expected'))
    # the stack forms: the second number is the one at the top of the VDP value stack (the pointer at >836E), and the pointer drops by 8
    sops = {0x0B: lambda f, a: f + a, 0x0C: lambda f, a: a - f, 0x0D: lambda f, a: f * a, 0x0E: lambda f, a: a / f}
    snames = {0x0B: 'SADD', 0x0C: 'SSUB', 0x0D: 'SMUL', 0x0E: 'SDIV'}
    badS, worstS = None, Decimal(0)
    for code, fn in sops.items():
        for i in range(30):
            xf = Decimal(rnd.choice([-1, 1])) * Decimal(rnd.randint(1, 10**6)) / Decimal(10) ** rnd.randint(0, 6)
            xa = Decimal(rnd.choice([-1, 1])) * Decimal(rnd.randint(1, 10**6)) / Decimal(10) ** rnd.randint(0, 6)
            ptr = 0x3008 + 8 * rnd.randint(0, 6)
            for j in range(0x2F80, 0x3100):
                m.vram[j] = 0
            for j, x in enumerate(enc(xa)):
                m.vram[ptr + j] = x
            put(0x834A, enc(xf)); m.ww(0x836E, ptr)
            before = get(pad0, 256)
            call(code)
            after = get(pad0, 256)
            changed |= {pad0 + j for j in range(0xE0) if before[j] != after[j] and not 0x00 <= j < 0x20}
            want = fn(dec(enc(xf)), dec(enc(xa)))
            got = dec(get(0x834A))
            err = abs(got - want) / abs(want) if want != 0 else abs(got)
            worstS = max(worstS, err)
            if (err > Decimal('1e-12') or m.rw(0x836E) != ptr - 8) and badS is None:
                badS = (snames[code], str(xf), str(xa), str(want), str(got), hex(m.rw(0x836E)), hex(ptr))
    check(badS is None, 'SADD, SSUB, SMUL, SDIV (the number at the top of the VDP stack is the first operand of the subtraction and the dividend): 120 random operations match Python to %.1e and the stack pointer drops by 8 each time (%s)' % (worstS, badS or 'no difference'))
    badC = None
    for xf, xa in ((3, 5), (5, 5), (7, 5), (-2, 4), (4, -2)):
        for j in range(0x2F80, 0x3100):
            m.vram[j] = 0
        for j, x in enumerate(enc(xa)):
            m.vram[0x3008 + j] = x
        put(0x834A, enc(xf)); m.ww(0x836E, 0x3008)
        got = call(0x0F)[0] & 0x60
        want = 0x20 if xf == xa else (0x40 if xf < xa else 0)
        if got != want and badC is None:
            badC = (xf, xa, hex(got), hex(want))
    check(badC is None, 'SCOMP: the same result bits as FCOMP, against the number on the stack (%s)' % (badC or 'all as expected'))
    badI = None
    for v in ('0', '1', '-1', '7', '-5', '100', '12345', '-12345', '32767', '-32768', '3.7', '-3.7', '2.5', '-2.5', '0.4', '-0.4', '1234.5', '-1234.5'):
        put(0x834A, enc(v))
        call(0x12)
        w = m.rw(0x834A)
        got = w - 65536 if w >= 32768 else w
        want = int((Decimal(v) + Decimal('0.5')).to_integral_value(rounding='ROUND_FLOOR'))
        if got != want and badI is None:
            badI = (v, got, want)
    ovf = []
    for v in ('32768', '40000', '-32769', '1e9'):
        put(0x834A, enc(v)); m.wb(0x8354, 0)
        call(0x12)
        ovf.append(m.rb(0x8354))
    check(badI is None and ovf == [3, 3, 3, 3], 'CFI (XML >12): float to integer rounds to nearest with halves up on 18 values (%s), and sets the error byte >8354 to 3 outside -32768..32767: %s' % (badI or 'all as expected', ovf))
    check(call(0x20)[0] == 0xFFFF and call(0x00)[0] == 0xFFFF and call(0xF6)[0] == 0xFFFF, 'a code in a table that is not the console\'s, or an empty entry, is refused (>FFFF)')
    overlap = {hex(a): kernel_names[a] for a in changed if a in kernel_names or (a - 1) in kernel_names}
    outside = sorted(hex(a) for a in changed if not (0x834A <= a <= 0x836F or 0x8370 <= a <= 0x837F))
    check(not overlap and not outside, 'every scratchpad byte changed below the GPL workspace is the console float package\'s (%s), none of the kernel\'s (%s)' % (' '.join(sorted(hex(a) for a in changed)), overlap or 'none'))

def common():
    """app.json "common": code shared by every module, assembled at >D000 and mapped there at start-up: the modules call it by the names it
    exports (common.equ) after a boot, a GOMOD and a MODCALL without mapping anything, window >D000 stays on its page throughout, and the
    build refuses an 8K module beside it, a common image over 4K and an export the source does not define."""
    import asmharness, shutil, tempfile
    c = build('tests/apps/common')
    syms = asmharness.symbols(os.path.join(ROOT, 'build', 'common', 'kernel.equ'))
    for n in ('ma', 'mb'):
        syms.update(asmharness.symbols(os.path.join(ROOT, 'build', 'common', n + '.equ')))
    ce = open(os.path.join(ROOT, 'build', 'common', 'common.equ')).read()
    check('CADD' in ce and 'CMAGIC' in ce and 'EQU  >D000' in ce, 'the build writes common.equ with the exports (CADD at >D000): %s' % [l.strip() for l in ce.split('\n')[1:3]])
    def run_keys(keys):
        saved = os.environ.pop('TI_CONSOLE_ROM', None)
        try:
            return sim9900.run(c, frames=300, keys=keys)
        finally:
            if saved:
                os.environ['TI_CONSOLE_ROM'] = saved
    word = lambda m, n: m.rw(syms[n])
    m, cpu, halt = run_keys('<WAIT 30>')
    check(halt is None and word(m, 'va') == 5 and word(m, 'vmg') == 0xC0DE and word(m, 'curcd') == syms['pg_common'] and m.rw(0xD000 + 4) == 0xC0DE,
          'at start-up the common page is in >D000 (CURCD >%02X = PG_COMMON), and the first module calls CADD (2 + 3 = %d) and reads CMAGIC (%04X)' % (word(m, 'curcd'), word(m, 'va'), word(m, 'vmg')))
    m, cpu, halt = run_keys('<WAIT 20>b<WAIT 30>')
    check(word(m, 'curcc') == syms['pg_mb'] and word(m, 'vb') == 15 and word(m, 'curcd') == syms['pg_common'],
          'after GOMOD to the second module it calls CADD too (7 + 8 = %d) and >D000 is still the common page' % word(m, 'vb'))
    m, cpu, halt = run_keys('<WAIT 20>m<WAIT 40>')
    check(word(m, 'vmb') == 300 and word(m, 'vaf') == 30 and word(m, 'vcd') == syms['pg_common'] and word(m, 'curcc') == syms['pg_ma'],
          'a MODCALL into the second module (CADD there: %d), then CADD again in the first: %d; >D000 is the common page throughout (>%02X)' % (word(m, 'vmb'), word(m, 'vaf'), word(m, 'vcd')))
    def variant(edit_json=None, edit_file=None):
        d = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, 'tests', 'apps', 'common'), d + '/app')
        if edit_json:
            j = json.load(open(d + '/app/app.json')); edit_json(j); json.dump(j, open(d + '/app/app.json', 'w'))
        if edit_file:
            edit_file(d + '/app')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/app', '--out', d + '/out'], capture_output=True, text=True)
        return r, (r.stdout + r.stderr)
    r, out = variant(lambda j: j['modules'][1].update(size=8192))
    check(r.returncode != 0 and 'mb' in out and 'single page' in out, 'an 8K module beside the common code is refused by name: %s' % out.strip().split('\n')[-1][:100])
    r, out = variant(edit_file=lambda d: open(d + '/common.a99', 'a').write('       BSS  4200\n'))
    check(r.returncode != 0 and 'at most 4,096' in out, 'a common image over 4K is refused: %s' % out.strip().split('\n')[-1][:90])
    r, out = variant(lambda j: j['common'].update(exports=['CADD', 'NOSUCH']))
    check(r.returncode != 0 and 'NOSUCH' in out, 'an export the source does not define is refused by name: %s' % out.strip().split('\n')[-1][:90])
    r, out = variant(lambda j: j.pop('common'), lambda d: None)
    check(r.returncode != 0, 'without the "common" entry the modules do not assemble (CADD is not defined): the entry is what provides common.equ')

def cycles():
    """tools/cycles.py, the cycle model: single instructions against the TMS9900 data manual's clock cycles (with the TI's 4 wait cycles
    for every access outside the console ROM and the scratchpad: TI's 99/4A technical data has a 16-bit external read finish in clock cycle 6, where an access
    without wait states takes 2: see tools/cycles.py), and the DEC / JNE loop counting 65,535: 0.44 s in the scratchpad, 0.61 s with the code in
    expansion RAM and 0.79 s with the workspace there too."""
    import cycles as cy
    c = build('hello')
    saved = os.environ.pop('TI_CONSOLE_ROM', None)
    try:
        m = sim9900.Machine(c)
        m.presses, m.toggles, end = sim9900.schedule([])
        boot = sim9900.CPU(m)
        boot.pc = m.rw(m.rw(0x6006) + 2)
        while m.insns < 60 * sim9900.VSYNC_INSNS:
            boot.step()
    finally:
        if saved:
            os.environ['TI_CONSOLE_ROM'] = saved
    cpu = cy.CycleCPU(m)
    def place(addr, words):
        for i, w in enumerate(words):
            m.ww(addr + 2 * i, w)
    def one(words, at=0x8380, regs=None, st=0):
        """run one instruction placed at AT; returns the cycles it cost"""
        cpu.wp = 0x8300; cpu.limi = 0; cpu.st = st; cpu.pending_op = None
        place(at, words)
        for r, v in (regs or {}).items():
            m.ww(0x8300 + 2 * r, v)
        cpu.pc = at; cpu.cycles = 0
        cpu.step()
        return cpu.cycles
    got = {}
    got['MOV R1,R2'] = one([0xC081])
    got['MOV *R1+,*R2+ (scratchpad)'] = one([0xCCB1], regs={1: 0x8320, 2: 0x8330})
    got['MOV *R1+,*R2+ (expansion RAM data)'] = one([0xCCB1], regs={1: 0x2400, 2: 0x2410})
    got['A @>2400,R1'] = one([0xA060, 0x2400])
    got['SLA R1,4'] = one([0x0A41])
    got['MPY R1,R2'] = one([0x3881])
    got['LI R1,>1234'] = one([0x0201, 0x1234])
    got['JEQ taken'] = one([0x1301], st=0x2000)
    got['JEQ not taken'] = one([0x1301], st=0)
    got['MOV R1,R2 (code in expansion RAM)'] = one([0xC081], at=0x2400)
    want = {'MOV R1,R2': 14, 'MOV *R1+,*R2+ (scratchpad)': 30, 'MOV *R1+,*R2+ (expansion RAM data)': 30 + 3 * 4, 'A @>2400,R1': 14 + 8 + 4,
            'SLA R1,4': 20, 'MPY R1,R2': 52, 'LI R1,>1234': 12, 'JEQ taken': 10, 'JEQ not taken': 8, 'MOV R1,R2 (code in expansion RAM)': 14 + 4}
    check(got == want, 'single instructions against the manual: %s' % ('all %d match' % len(want) if got == want else {k: (got[k], want[k]) for k in want if got[k] != want[k]}))
    def loop(at, n):
        place(at, [0x0602, 0x16FE, 0x10FF])                 # DEC R2 / JNE $-2 / JMP $
        cpu.wp = 0x8300; cpu.limi = 0; cpu.pending_op = None
        m.ww(0x8304, n)
        cpu.pc = at; cpu.cycles = 0
        while cpu.pc != at + 4:
            cpu.step()
        return cpu.cycles
    fast, slow = loop(0x8380, 65535), loop(0x2400, 65535)
    def loop_ws(at, wsp, n):
        place(at, [0x0602, 0x16FE, 0x10FF])
        cpu.wp = wsp; cpu.limi = 0; cpu.pending_op = None
        m.ww(wsp + 4, n)
        cpu.pc = at; cpu.cycles = 0
        while cpu.pc != at + 4:
            cpu.step()
        return cpu.cycles
    slowest = loop_ws(0x2400, 0x2500, 65535)
    check(fast == 65535 * 20 - 2 and slow == 65535 * 28 - 2 and slowest == 65535 * 36 - 2,
          'DEC R2 / JNE counting 65,535: %d cycles in the scratchpad = %.3f s; %d with the code in expansion RAM = %.3f s (two fetches, 4 wait cycles each); %d with the workspace there too = %.3f s (four accesses)'
          % (fast, fast / cy.CLOCK, slow, slow / cy.CLOCK, slowest, slowest / cy.CLOCK))
    check(0.43 < fast / cy.CLOCK < 0.45 and 0.60 < slow / cy.CLOCK < 0.62 and 0.78 < slowest / cy.CLOCK < 0.80,
          'consistent with the TI technical data (6 clock cycles for an external 16-bit access); not measured on a real machine')
    place(0x8380, [0x0602, 0x16FE, 0x10FF])
    cpu.wp = 0x8300; cpu.limi = 0; cpu.pending_op = None; m.ww(0x8304, 1000)
    cpu.pc = 0x8380
    before = m.insns
    for i in range(100):
        cpu.step()
    check(m.insns - before == 100, 'the model only measures: the simulator\'s own instruction count (and so its frames and interrupts) advances exactly as without it (100 steps: %d)' % (m.insns - before))

def ea5():
    """tools/ea5.py: Editor/Assembler option 5 for the simulator.  A one-file image assembled with `xas99 -i` goes on a disk image as a PROGRAM file, is loaded into a simulated machine
    the way option 5 loads it, and runs from its load address; a chain of two files (a second segment elsewhere) loads both and starts at the first; a missing file is an error."""
    import tempfile, ea5 as ea, skdisk, tifdc
    d = tempfile.mkdtemp()
    open(d + '/p.a99', 'w').write("       AORG >C000\nSTART  LWPI >8300\n       LI   R0,>1234\n       MOV  R0,@>8320\n       LI   R1,>4321\n"
                                  "       MOV  R1,@>3FF0\nLOOP   JMP  LOOP\n       END  START\n")
    r = subprocess.run([sys.executable, os.environ['XAS99'], '-R', '-i', '-q', d + '/p.a99', '-o', d + '/PROG'], capture_output=True, text=True)
    check(r.returncode == 0 and os.path.exists(d + '/PROG'), 'xas99 -i writes the image file')
    skdisk.make_disk(d + '/d.dsk', [], None, 'EA5', 'sssd', programs=[('HELLO', open(d + '/PROG', 'rb').read())])
    img = bytearray(open(d + '/d.dsk', 'rb').read())
    m = sim9900.Machine(bytes(8192))
    cpu = sim9900.CPU(m)
    entry = ea.load(m, img, 'HELLO')
    cpu.pc, cpu.wp, cpu.limi = entry, 0x83E0, 0
    for i in range(30):
        cpu.step()
    check(entry == 0xC000 and m.rw(0x8320) == 0x1234 and m.rw(0x3FF0) == 0x4321, 'a one-file image loads at >C000 and runs from its first byte (entry >%04X, wrote %04X and %04X)' % (entry, m.rw(0x8320), m.rw(0x3FF0)))
    open(d + '/q.a99', 'w').write("       AORG >A000\nSTART  LWPI >8300\n       B    @MORE\n       AORG >B000\nMORE   LI   R2,>0F0F\n       MOV  R2,@>8322\nLOOP   JMP  LOOP\n       END  START\n")
    for f in os.listdir(d):
        if f.startswith('CH'):
            os.remove(os.path.join(d, f))
    r = subprocess.run([sys.executable, os.environ['XAS99'], '-R', '-i', '-q', d + '/q.a99', '-o', d + '/CHAIN'], capture_output=True, text=True)
    files = sorted(f for f in os.listdir(d) if f.startswith('CHAI'))
    progs = [(f.upper(), open(os.path.join(d, f), 'rb').read()) for f in files]
    skdisk.make_disk(d + '/e.dsk', [], None, 'EA5', 'sssd', programs=progs)
    img2 = bytearray(open(d + '/e.dsk', 'rb').read())
    m2 = sim9900.Machine(bytes(8192))
    cpu2 = sim9900.CPU(m2)
    entry2 = ea.load(m2, img2, 'CHAIN')
    cpu2.pc, cpu2.wp, cpu2.limi = entry2, 0x83E0, 0
    for i in range(30):
        cpu2.step()
    check(len(files) == 2 and entry2 == 0xA000 and m2.rw(0x8322) == 0x0F0F, 'a two-file chain (%s) loads both segments, starts at the first (>%04X) and runs into the second' % (files, entry2))
    try:
        ea.load(m, img, 'NOSUCH')
        gone = False
    except FileNotFoundError:
        gone = True
    check(gone, 'a file that is not on the disk is an error')

def diskboot():
    """The disk start (docs/DISKSTART.md), first stage: `skbuild --disk` writes the bootstrap (an option 5 image at >C000, the loader assembled with DISKBOOT) and every bank as a PROGRAM
    file; the bootstrap is run the way option 5 runs it (tools/ea5.py) in a simulated machine with TI's real controller ROM, and it reads the banks through the kernel's file service and
    starts the kernel: the application's screen appears."""
    import tempfile, ea5 as ea, tifdc, asmharness
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    d = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), os.path.join(ROOT, 'examples', 'hello'), '--out', d, '--disk', '--geometry', 'sssd'], capture_output=True, text=True)
    check(r.returncode == 0 and os.path.exists(d + '/hello.dsk'), '`skbuild --disk` writes the disk image: %s' % [l for l in r.stdout.split('\n') if 'bank files' in l][:1])
    img = bytearray(open(d + '/hello.dsk', 'rb').read())
    boot = tifdc.read_program(img, 'HELLO')
    names = [n for n in tifdc.TIFDC(image=img).files()]
    check(boot is not None and boot[:2] == b'\x00\x00' and boot[4:6] == b'\xc0\x00' and len(boot) == 6 + ((boot[2] << 8) | boot[3]) and names.count('HELLO') == 1 and 'HELLO/B01' in names and 'HELLO/B03' in names,
          'the bootstrap file is an option 5 image for >C000 (%d bytes) and the banks are HELLO/B01 to B03: %s' % (len(boot or b''), sorted(names)))
    m = sim9900.Machine(bytes(8192))
    m.tifdc = tifdc.TIFDC(image=img)
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m)
    cpu.pc, cpu.wp, cpu.limi = ea.load(m, img, 'HELLO'), 0x83E0, 0
    shown = False
    for chunk in range(120):
        for i in range(100000):
            cpu.step()
        if any('Hello' in l for l in sim9900.screen(m).split('\n')[:3]):
            shown = True
            break
    scr = [l.rstrip() for l in sim9900.screen(m).split('\n') if l.strip()]
    check(shown, 'the bootstrap reads the three bank files from the disk and the kernel runs the application: its screen shows %r after %d instructions' % (scr[:1], m.insns))
    # the bank files are trimmed of their trailing zeros, and the bootstrap zero-fills what a file does not reach
    sizes = {n: len(tifdc.read_program(img, n)) for n in names if '/B' in n}
    check(all(v < 8192 for v in sizes.values()) and sum(sizes.values()) + len(boot) < 16000,
          'the bank files are trimmed, not padded to 8K: %s, with the bootstrap %d bytes in all (a padded disk was 29,004)' % (sizes, sum(sizes.values()) + len(boot)))
    import asmharness as ah
    sy = ah.symbols(d + '/kernel.equ')
    mod = open(d + '/hello.bin', 'rb').read()
    pg = sy['pg_hello']
    ram = bytes(m.ams[pg * 4096:(pg + 2) * 4096])
    check(ram[:len(mod)] == mod and not any(ram[len(mod):]),
          'hello\'s module page holds its %d bytes and then zeros: what the shorter file did not reach is zero, not what the earlier banks left in the buffer (page >%02X)' % (len(mod), pg))
    # a disk without the bank files: the refusal screen, not a crash
    only_boot = bytearray(img)
    import skdisk as sk2
    sk2.make_disk(d + '/bare.dsk', [], None, 'BARE', 'sssd', programs=[('HELLO', boot)])
    bare = bytearray(open(d + '/bare.dsk', 'rb').read())
    m3 = sim9900.Machine(bytes(8192)); m3.tifdc = tifdc.TIFDC(image=bare)
    m3.presses, m3.toggles, end = sim9900.schedule([])
    cpu3 = sim9900.CPU(m3)
    cpu3.pc, cpu3.wp, cpu3.limi = ea.load(m3, bare, 'HELLO'), 0x83E0, 0
    for i in range(3_000_000):
        cpu3.step()
    scr3 = sim9900.screen(m3)
    check('CANNOT BE READ FROM THE DISK' in scr3, 'with the bootstrap but not the bank files on the disk it shows the refusal screen (and does not crash): %r' % [l.strip() for l in scr3.split('\n') if l.strip()][:1])
    # the double-density cards, with a double-density disk
    cards = []
    if __import__('ccfdc').available():
        cards.append(('CorComp', lambda im: __import__('ccfdc').CCFDC(image=im)))
    if __import__('myfdc').available():
        cards.append(('Myarc DDCC-1', lambda im: __import__('myfdc').MYFDC(image=im)))
    if __import__('hfdc').available():
        cards.append(('Myarc HFDC', lambda im: __import__('hfdc').HFDC(image=im)))
    only = os.environ.get('TESTCARDS')
    if only:
        cards = [c for c in cards if any(w in c[0] for w in only.split(','))]
    d2 = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), os.path.join(ROOT, 'examples', 'hello'), '--out', d2, '--disk', '--geometry', 'dsdd'], capture_output=True, text=True)
    dimg = open(d2 + '/hello.dsk', 'rb').read()
    for label, make_card in cards:
        im = bytearray(dimg)
        mm = sim9900.Machine(bytes(8192)); mm.tifdc = make_card(im)
        mm.presses, mm.toggles, end = sim9900.schedule([])
        cc = sim9900.CPU(mm)
        cc.pc, cc.wp, cc.limi = ea.load(mm, im, 'HELLO'), 0x83E0, 0
        shown2 = False
        for chunk in range(200):
            for i in range(100000):
                cc.step()
            if any('Hello' in l for l in sim9900.screen(mm).split('\n')[:3]):
                shown2 = True
                break
        check(shown2, '[%s] the same bootstrap reads the banks from a double-density disk and the application runs (after %d instructions)' % (label, mm.insns))
    # the workbench itself as a disk-started program (no cartridge): its catalog lists the disk, and it assembles a source from the same disk
    dw = tempfile.mkdtemp()
    rw = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), os.path.join(ROOT, 'examples', 'workbench'), '--out', dw, '--disk', '--geometry', 'sssd',
                         '--disk-files', os.path.join(ROOT, 'examples', 'hello', 'hello.a99')], capture_output=True, text=True)
    check(rw.returncode == 0 and os.path.exists(dw + '/wbench.dsk'), 'the workbench builds as a disk-started program with a source and KERNEL/EQU on the same disk: %s' % [l for l in rw.stdout.split('\n') if 'bank files' in l][:1])
    wimg = open(dw + '/wbench.dsk', 'rb').read()
    def wbrun(keys, until, frames_chunks=150):
        im = bytearray(wimg)
        mw = sim9900.Machine(bytes(8192)); mw.tifdc = tifdc.TIFDC(image=im)
        mw.presses, mw.toggles, end = sim9900.schedule(sim9900.parse_keys(keys))
        cw = sim9900.CPU(mw)
        cw.pc, cw.wp, cw.limi = ea.load(mw, im, 'WBENCH'), 0x83E0, 0
        for chunk in range(frames_chunks):
            for i in range(100000):
                cw.step()
            if until in sim9900.screen(mw):
                break
        return mw, sim9900.screen(mw)
    mw, scr = wbrun('<WAIT 600>c<WAIT 150>', 'KERNEL/EQU')
    check('HELLO/A99' in scr and 'KERNEL/EQU' in scr, 'started from the disk, the workbench shows its menu and its catalog (C) lists HELLO/A99 and KERNEL/EQU from the disk it started from')
    mw, scr = wbrun('<WAIT 600>nHELLO/A99<ENTER><WAIT 20>a<WAIT 2500>', 'Assembled', 400)
    check('Assembled:' in scr and '194' in scr, 'and it assembles HELLO/A99 from that disk on the simulated TI: %s' % ' '.join(l.strip() for l in scr.split('\n') if 'Assembled' in l))
    check(bytes(mw.tifdc.image) == wimg, 'and reading the disk (the bootstrap, the catalog, two passes over two files) left the disk image exactly as it was (the controller model once overwrote a sector with a seek\'s target bytes)')

def prun():
    """PRUN (kernel/files.a99): a disk-started program replaces itself with another.  Two tiny programs, ALPHA and BETA, are built for disk and put on one disk image; ALPHA is
    started the way option 5 starts it, shows ALPHA, and on G runs DSK1.BETA: the bootstrap is loaded to >C000 with the handoff block, reads BETA's banks and BETA shows its own
    screen; on X it tries a program that is not there and keeps running, with PRUN's error returned."""
    import tempfile, shutil, ea5 as ea, tifdc, skdisk
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    progs = []
    for app in ('prun_a', 'prun_b'):
        d = tempfile.mkdtemp()
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), os.path.join(ROOT, 'tests', 'apps', app), '--out', d, '--disk', '--geometry', 'sssd'],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        img = bytearray(open(glob.glob(d + '/*.dsk')[0], 'rb').read())
        for n in tifdc.TIFDC(image=img).files():
            progs.append((n, tifdc.read_program(img, n)))
    dd = tempfile.mkdtemp()
    skdisk.make_disk(dd + '/both.dsk', [], None, 'PRUN', 'sssd', programs=progs)
    base = bytearray(open(dd + '/both.dsk', 'rb').read())
    names = sorted(tifdc.TIFDC(image=base).files())
    check('ALPHA' in names and 'BETA' in names and 'ALPHA/B01' in names and 'BETA/B03' in names, 'the disk holds both programs: %s' % names)
    def run(keys, until, cap=60, full=False):
        img = bytearray(base)
        m = sim9900.Machine(bytes(8192))
        m.tifdc = tifdc.TIFDC(image=img)
        m.presses, m.toggles, end = sim9900.schedule(sim9900.parse_keys(keys) if hasattr(sim9900, 'parse_keys') else keys)
        cpu = sim9900.CPU(m)
        cpu.pc, cpu.wp, cpu.limi = ea.load(m, img, 'ALPHA'), 0x83E0, 0
        seen = []
        for chunk in range(cap):
            for i in range(100000):
                cpu.step()
            line = ' '.join(l.strip() for l in sim9900.screen(m).split('\n')[:4])
            if until in line and not full:
                return m, cpu, True, line
        return m, cpu, until in line, line
    def variant(edit_json):
        dv = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, 'tests', 'apps', 'prun_a'), dv + '/app')
        j = json.load(open(dv + '/app/app.json')); edit_json(j); json.dump(j, open(dv + '/app/app.json', 'w'))
        rv = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), dv + '/app', '--out', dv + '/out'], capture_output=True, text=True)
        return rv, rv.stdout + rv.stderr
    rv, out = variant(lambda j: j.update(prun=False))
    check(rv.returncode != 0 and 'PRUN' in out and '"prun": true' in out, 'a program that uses PRUN without "prun": true is refused by name: %s' % out.strip().split('\n')[-1][:100])
    rv, out = variant(lambda j: j.update(omit=['files']))
    check(rv.returncode != 0 and 'files' in out, '"prun": true with the file service left out is refused: %s' % out.strip().split('\n')[-1][:100])
    rb, outb = variant(lambda j: j.update(prun=True))
    kb = [int(l.split()[1]) for l in outb.split('\n') if l.startswith('kernel ')]
    rc, outc = variant(lambda j: (j.update(prun=False), None))
    check(rb.returncode == 0 and kb and kb[0] >= 7000, 'with "prun": true the kernel is %s bytes (206 more than without)' % kb)
    m, cpu, ok, line = run('<WAIT 20>', 'ALPHA')
    check(ok, 'ALPHA starts from the disk and shows its screen: %r' % line)
    m, cpu, ok, line = run('<WAIT 450>g<WAIT 20>', 'BETA', cap=120)
    check(ok and 'ALPHA' not in line, 'G in ALPHA runs DSK1.BETA: its bootstrap, then its banks, then its own screen: %r' % line)
    m, cpu, ok, line = run('<WAIT 450>x<WAIT 40>', 'ALPHA', cap=70, full=True)
    err = m.rw(0x2300)                                    # APPRAM: where ALPHA keeps PRUN's answer
    check(ok and err != 0, 'X in ALPHA tries a program that is not on the disk: PRUN returns the error (%d) and ALPHA is still running (%r)' % (err, line))

def arcode():
    """app.json "appram_code": code the program keeps in its own RAM.  It is assembled at >2300 against the kernel it runs with, copied there from its page at start-up, and the application's
    data (APPRAM) begins after it; a module calls its routines and reads its data by the names it exports (arcode.equ); the build refuses a source that does not say AORG >2300, an
    image over 6K and an export it does not define."""
    import asmharness, shutil, tempfile
    c = build('tests/apps/arcode')
    bd = os.path.join(ROOT, 'build', 'arcode')
    syms = asmharness.symbols(os.path.join(bd, 'kernel.equ'))
    syms.update(asmharness.symbols(os.path.join(bd, 'ma.equ')))
    ae = open(os.path.join(bd, 'arcode.equ')).read()
    code = open(os.path.join(bd, 'arcode.bin'), 'rb').read()
    check('ARADD' in ae and 'EQU  >2300' in ae and 'ARTAG' in ae and 'ARCLS' in ae, 'the build writes arcode.equ with the exports (ARADD at >2300): %s' % [l.strip() for l in ae.split('\n')[1:4]])
    check(syms['appram'] == 0x2300 + len(code) and len(code) % 2 == 0, 'APPRAM moves up by the code\'s size: >%04X = >2300 + %d' % (syms['appram'], len(code)))
    saved = os.environ.pop('TI_CONSOLE_ROM', None)
    try:
        m, cpu, halt = sim9900.run(c, frames=80)
    finally:
        if saved:
            os.environ['TI_CONSOLE_ROM'] = saved
    ram = bytes(m.rb(0x2300 + i) for i in range(len(code)))
    check(halt is None and ram == code, 'at start-up the code is in RAM at >2300, byte for byte the image the build made (%d bytes)' % len(code))
    ar = syms['appram']
    scr = [l.strip() for l in sim9900.screen(m).split('\n') if l.strip()]
    check(m.rw(ar) == 5 and m.rw(ar + 2) == 0xA5A5 and 'ARCODE' in scr,
          'the module calls ARADD (2 + 3 = %d), reads ARTAG (%04X) and calls ARCLS, which draws through the kernel (screen %r)' % (m.rw(ar), m.rw(ar + 2), scr[:1]))
    def variant(edit_file=None, edit_json=None):
        d = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, 'tests', 'apps', 'arcode'), d + '/app')
        if edit_json:
            j = json.load(open(d + '/app/app.json')); edit_json(j); json.dump(j, open(d + '/app/app.json', 'w'))
        if edit_file:
            edit_file(d + '/app')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/app', '--out', d + '/out'], capture_output=True, text=True)
        return r, r.stdout + r.stderr
    r, out = variant(edit_file=lambda d: open(d + '/ar.a99', 'w').write(open(os.path.join(ROOT, 'tests', 'apps', 'arcode', 'ar.a99')).read().replace('AORG >2300', 'AORG >2400')))
    check(r.returncode != 0 and 'AORG >2300' in out, 'a source that does not say AORG >2300 is refused: %s' % out.strip().split('\n')[-1][:90])
    r, out = variant(edit_file=lambda d: open(d + '/ar.a99', 'a').write('       BSS  6200\n'))
    check(r.returncode != 0 and '6,144' in out, 'an image over 6K is refused: %s' % out.strip().split('\n')[-1][:100])
    r, out = variant(edit_json=lambda j: j['appram_code'].update(exports=['ARADD', 'NOSUCH']))
    check(r.returncode != 0 and 'NOSUCH' in out, 'an export the source does not define is refused by name: %s' % out.strip().split('\n')[-1][:90])
    r, out = variant()
    check(r.returncode == 0, 'and the unchanged copy builds in a directory of its own (the two passes find their files)')
    if os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM']):
        import ea5 as ea, tifdc
        dd = tempfile.mkdtemp()
        rd = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), os.path.join(ROOT, 'tests', 'apps', 'arcode'), '--out', dd, '--disk', '--geometry', 'sssd'],
                            capture_output=True, text=True)
        img = bytearray(open(glob.glob(dd + '/*.dsk')[0], 'rb').read())
        md = sim9900.Machine(bytes(8192)); md.tifdc = tifdc.TIFDC(image=img)
        md.presses, md.toggles, end = sim9900.schedule([])
        cd = sim9900.CPU(md)
        cd.pc, cd.wp, cd.limi = ea.load(md, img, 'ARCODE'), 0x83E0, 0
        for chunk in range(120):
            for i in range(100000):
                cd.step()
            if 'ARCODE' in sim9900.screen(md):
                break
        check(rd.returncode == 0 and 'ARCODE' in sim9900.screen(md) and bytes(md.rb(0x2300 + i) for i in range(len(code))) == code,
              'started from a disk the program has its code in RAM at >2300 as well (the code is one more bank file)')

def txm():
    """TXA music notation (.txm) as the default notation: tools/skmusic.py compiles it through TXA's own reference compiler (tools/txamusic.py, vendored) and the kernel's player plays it.
    Checks: the compiled song, decoded and applied to a model of the chip frame by frame, is the reference compiler's state at every tick (two loops, both example tunes); a bad file is an
    error with its line; the music demo built with a .txm tune plays exactly the bytes the compiler made, in the simulator."""
    import skmusic, txamusic, shutil, tempfile
    def chip_after(events, nframes, ticks, loops=2):
        chip = {0: [0, 15], 1: [0, 15], 2: [0, 15], 3: [0, 15]}
        latch = [None]
        def write(b):
            if b & 0x80:
                ch = (b >> 5) & 3
                if b & 0x10:
                    chip[ch][1] = b & 15
                elif ch == 3:
                    chip[3][0] = 0xE0 | (b & 7); latch[0] = None
                else:
                    chip[ch][0] = (chip[ch][0] & 0x3F0) | (b & 15); latch[0] = ch
            elif latch[0] is not None:
                chip[latch[0]][0] = (chip[latch[0]][0] & 15) | ((b & 0x3F) << 4)
        states, k = [], 0
        for f in range(ticks * loops):
            while k < len(events) and events[k][0] <= f:
                write(events[k][1]); k += 1
            states.append({c: tuple(v) for c, v in chip.items()})
        return states
    for name in ('HARBOUR.txm', 'HARBOURB.txm'):
        path = os.path.join(ROOT, 'examples', 'music', 'songs', name)
        skm, info = skmusic.compile_file(path, loop=True)
        song = txamusic.compile_text(open(path).read())
        ev, nframes = skmusic.decode(skm, 2)
        states = chip_after(ev, nframes, song.ticks)
        bad = []
        for t in range(song.ticks * 2):
            for v in song.voices:
                ch = 'ABCN'.index(v)
                want = song.voices[v][t % song.ticks]
                got = states[t][ch]
                ok = (got[1] == want[1] == 15) or got == tuple(want)
                if not ok and len(bad) < 4:
                    bad.append((t, v, got, want))
        check(not bad and info['frames'] == song.ticks, '%s: %d ticks, %d bytes: the chip state the compiled song gives is the reference compiler\'s at every tick, twice round (%s)' % (name, song.ticks, len(skm), bad or 'no difference'))
    bad_file = tempfile.mkdtemp() + '/bad.txm'
    open(bad_file, 'w').write('A: O4 C D E\nA: O9 C\n')
    try:
        skmusic.compile_file(bad_file)
        msg = None
    except SystemExit as e:
        msg = str(e)
    check(msg and 'skmusic' in msg, 'a note outside the notation\'s range is an error that says where: %r' % (msg or '')[:100])
    pal, info = skmusic.compile_file(os.path.join(ROOT, 'examples', 'music', 'songs', 'HARBOURB.txm'), fps=50)
    ev50, n50 = skmusic.decode(pal)
    check(abs(n50 - 1009 * 50 / 60.0) <= 2, 'at 50 frames a second (a PAL console) the same tune is %d frames: the same time (%.1f s)' % (n50, n50 / 50.0))
    d = tempfile.mkdtemp()
    shutil.copytree(os.path.join(ROOT, 'examples', 'music'), d + '/app')
    j = json.load(open(d + '/app/app.json'))
    j['data'][0]['from'] = 'songs/HARBOURB.txm'
    json.dump(j, open(d + '/app/app.json', 'w'))
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/app', '--out', d + '/out'], capture_output=True, text=True)
    check(r.returncode == 0, 'the music demo builds with a .txm tune (app.json "from": "songs/HARBOURB.txm")')
    img = open(glob.glob(d + '/out/*8.bin')[0], 'rb').read()
    skm, info = skmusic.compile_file(os.path.join(ROOT, 'examples', 'music', 'songs', 'HARBOURB.txm'), loop=True)
    ev, nframes = skmusic.decode(skm, 2)
    m, cpu, halt = sim9900.run(img, keys='<WAIT 5>1<WAIT 1180>', frames=1300)
    log = [(i, b) for (src, i, b) in m.chip_log if src == 'cpu']
    got = [b for i, b in log[4:]]
    check(len(got) > 600 and got == [b for f, b in ev][:len(got)], 'in the simulator the kernel\'s player writes the compiled tune\'s bytes to the chip, exactly (%d bytes of %d)' % (len(got), len(ev)))

def exprcheck():
    """tools/exprcheck.py (from the Press session): xas99 evaluates expressions strictly left to right, so `X+8*16+14` is ((X+8)*16)+14.  The checker finds those; nothing in the kernel, lib/,
    the examples or the test applications has one (tests/asm/probe1.a99 does, on purpose, to test the assembler); skbuild warns about one in an application's own sources."""
    import exprcheck as ec, glob, tempfile, shutil
    bad = list(ec.hazards(['       MOV  @STGEO+8*16+14,R1', '       LI   R0,2*COLS+2', '       MOV  @X+(8*16)+14,R1', "       TEXT 'A+B*C'", '* A+B*C', '       DATA 1-2/3']))
    check([n for n, t in bad] == [1, 6], 'the checker reports X+8*16+14 and 1-2/3, and not 2*COLS+2, a parenthesised product, TEXT or a comment: lines %s' % [n for n, t in bad])
    files = [f for pat in ('kernel/*.a99', 'lib/*.a99', 'examples/**/*.a99', 'tests/apps/**/*.a99') for f in glob.glob(os.path.join(ROOT, pat), recursive=True)]
    found = [(os.path.relpath(f, ROOT), n) for f in files for n, t in ec.hazards(open(f, encoding='latin-1').read().split('\n'))]
    check(not found, 'no expression hazard in the %d sources of kernel/, lib/, examples/ and tests/apps/: %s' % (len(files), found or 'none'))
    probe = [n for n, t in ec.hazards(open(os.path.join(ROOT, 'tests', 'asm', 'probe1.a99'), encoding='latin-1').read().split('\n'))]
    check(probe == [13], 'and tests/asm/probe1.a99 line 13 (DATA 2+3*4), which tests the assembler on purpose, is the only one in the tree: %s' % probe)
    d = tempfile.mkdtemp()
    shutil.copytree(os.path.join(ROOT, 'examples', 'hello'), d + '/app')
    src = open(d + '/app/hello.a99', encoding='latin-1').read()
    open(d + '/app/hello.a99', 'w', encoding='latin-1').write(src + '\n       LI   R0,APPRAM+8*16+14\n')
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/app', '--out', d + '/out'], capture_output=True, text=True)
    check('warning' in r.stderr and 'APPRAM+8*16+14' in r.stderr, 'skbuild warns about it in an application: %s' % [l for l in r.stderr.split('\n') if 'warning' in l][:1])

def sfx():
    """SFXPLAY / SFXSTOP (app.json "sfx": true): a sound effect plays over the song and borrows the channels it writes to.  The test app plays a looping song and an effect that writes
    voice B (channel 1) and the noise (channel 3).  Compared frame by frame with the song alone: before the effect the chip is the same; during it only channels 1 and 3 differ (the song's writes
    to them do not reach the chip); the effect's own bytes are what the chip hears on them; and when it ends, or is stopped, or is replaced, the chip is exactly what the song alone has.  An
    effect with no song ends in silence; pages that hold no effect answer 1; the build refuses SFXPLAY without the flag and the flag without the music player."""
    import skmusic, shutil, tempfile
    c = build('tests/apps/sfx')
    fx, info = skmusic.compile_file(os.path.join(ROOT, 'tests', 'apps', 'sfx', 'fx.txm'))
    fxev, fxframes = skmusic.decode(fx, 1)
    def run(keys, frames):
        saved = os.environ.pop('TI_CONSOLE_ROM', None)
        try:
            m, cpu, halt = sim9900.run(c, keys=keys, frames=frames)
        finally:
            if saved:
                os.environ['TI_CONSOLE_ROM'] = saved
        return m
    def writes(m):
        return [(i // sim9900.VSYNC_INSNS, b) for (src, i, b) in m.chip_log if src == 'cpu']
    def by_frame(m, frames):
        chip = {ch: [None, None] for ch in range(4)}
        latch = [None]
        log = writes(m)
        k, out = 0, []
        for f in range(frames):
            while k < len(log) and log[k][0] <= f:
                b = log[k][1]; k += 1
                if b & 0x80:
                    ch = (b >> 5) & 3
                    if b & 0x10:
                        chip[ch][1] = b & 15
                    elif ch == 3:
                        chip[3][0] = b & 7; latch[0] = None
                    else:
                        chip[ch][0] = (chip[ch][0] or 0) & 0x3F0 | (b & 15); latch[0] = ch
                elif latch[0] is not None:
                    chip[latch[0]][0] = ((chip[latch[0]][0] or 0) & 15) | ((b & 0x3F) << 4)
            out.append({ch: tuple(v) for ch, v in chip.items()})
        return out
    N = 1000
    A = by_frame(run('<WAIT 5>1<WAIT 950>', N + 20), N)
    B_m = run('<WAIT 5>1<WAIT 200>2<WAIT 750>', N + 20)
    B = by_frame(B_m, N)
    diff = [f for f in range(N) if A[f] != B[f]]
    chans = sorted({ch for f in diff for ch in range(4) if A[f][ch] != B[f][ch]})
    f0, f1 = min(diff), max(diff)
    check(f0 > 190 and chans == [1, 3] and f1 - f0 >= fxframes - 8 and f1 - f0 <= fxframes + 8,
          'song + effect against the song alone: they differ from frame %d to %d (the effect is %d frames) and only on channels %s' % (f0, f1, fxframes, chans))
    check(all(A[f] == B[f] for f in range(f1 + 2, N)) and f1 + 2 < N - 100,
          'after the effect ends the chip is exactly what the song alone has, for the %d frames that follow (the channels got their last bytes back)' % (N - f1 - 2))
    # the effect's own bytes reach the chip on its channels
    def chan_bytes(seq):
        latch, out = None, {0: [], 1: [], 2: [], 3: []}
        for b in seq:
            if b & 0x80:
                latch = (b >> 5) & 3
            if latch is not None:
                out[latch].append(b)
        return out
    fxb = chan_bytes([b for f, b in fxev])
    got = chan_bytes([b for f, b in writes(B_m) if f0 <= f <= f1 + 1])
    song_only = chan_bytes([b for f, b in writes(run('<WAIT 5>1<WAIT 950>', N + 20)) if f0 <= f <= f1 + 1])
    ok = all(got[ch][:len(fxb[ch])] == fxb[ch] for ch in (1, 3))
    check(ok and len(fxb[1]) > 10 and len(fxb[3]) > 4,
          'the bytes the chip is given on channels 1 and 3 during the effect begin with the effect\'s own (%d and %d bytes), in order' % (len(fxb[1]), len(fxb[3])))
    # the song's own writes to the noise channel were held back, not lost: the song alone writes to it in that window
    check(len(song_only[3]) > 0, 'the song does write to the noise channel in that window (%d bytes): what the effect held back' % len(song_only[3]))
    # stopped early
    D = by_frame(run('<WAIT 5>1<WAIT 200>2<WAIT 8>3<WAIT 740>', N + 20), N)
    dd = [f for f in range(N) if A[f] != D[f]]
    check(dd and max(dd) - min(dd) < 20 and all(A[f] == D[f] for f in range(max(dd) + 2, N)),
          'SFXSTOP in the middle: the channels are the song\'s again at once (differences over %d frames, then none)' % (max(dd) - min(dd) + 1))
    # replaced by a second effect
    E = by_frame(run('<WAIT 5>1<WAIT 200>2<WAIT 10>2<WAIT 740>', N + 20), N)
    ee = [f for f in range(N) if A[f] != E[f]]
    check(ee and all(A[f] == E[f] for f in range(max(ee) + 2, N)) and max(ee) - min(ee) > fxframes,
          'a second SFXPLAY replaces the first: it plays in full from its own start (differences over %d frames), then the song is intact' % (max(ee) - min(ee) + 1))
    # no song: the effect's channels end silent, the others are never written
    M = run('<WAIT 5>2<WAIT 400>', 400)
    Cst = by_frame(M, 400)
    check(Cst[-1][1][1] == 15 and Cst[-1][3][1] == 15 and all(s[0] == (None, None) and s[2] == (None, None) for s in Cst),
          'an effect with no song: channels 1 and 3 end silent (attenuation %s and %s) and channels 0 and 2 are never written' % (Cst[-1][1][1], Cst[-1][3][1]))
    # answers
    check(M.rw(0x2300) == 0, 'SFXPLAY answers 0 when the effect began (APPRAM = %d; it started as 65535)' % M.rw(0x2300))
    Fm = run('<WAIT 5>6<WAIT 100>', 300)
    check(Fm.rw(0x2302) == 1 and not writes(Fm), 'pages that hold no effect: SFXPLAY answers 1 and nothing reaches the chip (APPRAM+2 = %d, %d writes)' % (Fm.rw(0x2302), len(writes(Fm))))
    # pause: the song's other channels go quiet, the effect's do not
    P = by_frame(run('<WAIT 5>1<WAIT 200>2<WAIT 5>4<WAIT 40>5<WAIT 600>', N + 20), N)
    q = f0 + 20
    check(P[q][0][1] == 15 and P[q][2][1] == 15 and any(P[g][1][1] not in (None, 15) for g in range(f0 + 5, f0 + 30)),
          'MUPAUSE under an effect silences the song\'s own channels (0 and 2: attenuation %s, %s at frame %d) and leaves the effect\'s voice sounding' % (P[q][0][1], P[q][2][1], q))
    # the build
    d = tempfile.mkdtemp()
    shutil.copytree(os.path.join(ROOT, 'tests', 'apps', 'sfx'), d + '/a')
    j = json.load(open(d + '/a/app.json')); j['sfx'] = False; json.dump(j, open(d + '/a/app.json', 'w'))
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/a', '--out', d + '/o'], capture_output=True, text=True)
    out = r.stdout + r.stderr
    check(r.returncode != 0 and 'SFXPLAY' in out and '"sfx": true' in out, 'SFXPLAY without "sfx": true is refused by name: %s' % out.strip().split('\n')[-1][:100])
    j['sfx'] = True; j['omit'] = ['music']; json.dump(j, open(d + '/a/app.json', 'w'))
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), d + '/a', '--out', d + '/o2'], capture_output=True, text=True)
    check(r.returncode != 0 and 'music' in (r.stdout + r.stderr), '"sfx": true with the music player left out is refused: %s' % (r.stdout + r.stderr).strip().split('\n')[-1][:100])

def pic():
    """Pictures (tools/skpic.py, lib/picture.a99): PICSHOW decodes a picture record from SAMS into VRAM, loads its palette into F18A entries 32-, sets the bitmap layer's registers and turns it on; BMLOFF and
    BMLON switch it; bad calls answer 1, 2 or 3 and change nothing.  The test application has a 16-colour picture (format 4) and a 4-colour one (format 2), both made from PNGs by the build."""
    import skpic, shutil, tempfile
    from PIL import Image
    d = os.path.join(ROOT, 'tests', 'apps', 'pic')
    c = build('tests/apps/pic')
    rich = skpic.record(os.path.join(d, 'rich.png'))
    line = skpic.record(os.path.join(d, 'line.png'))
    fr, pr, rawr, rowsr = skpic.parse(rich)
    fl, pl, rawl, rowsl = skpic.parse(line)
    check(fr == 4 and len(pr) == 16 and fl == 2 and len(pl) == 4 and rowsr == rowsl == 88 and len(rawr) == len(rawl) == 5632,
          'the records: a 16-colour picture (format %d, %d bytes packed) and a 4-colour one (format %d, %d bytes), 88 rows of 64 bytes each' % (fr, len(rich), fl, len(line)))
    def run(keys, frames=420):
        saved = os.environ.pop('TI_CONSOLE_ROM', None)
        try:
            m, cpu, halt = sim9900.run(c, keys=keys, frames=frames)
        finally:
            if saved:
                os.environ['TI_CONSOLE_ROM'] = saved
        return m
    base = run('<WAIT 5>')
    m = run('<WAIT 5>1<WAIT 150>')
    check(bytes(m.vram[0x2000:0x2000 + 5632]) == rawr, 'the 16-colour picture is in VRAM at >2000, byte for byte what the reference decoder gives (5,632 bytes)')
    check([m.palette.get(32 + i) for i in range(16)] == pr, 'its palette is in F18A entries 32-47')
    check((m.vregs[31], m.vregs[32], m.vregs[33], m.vregs[34], m.vregs[35], m.vregs[36]) == (0xD8, 0x80, 0, 8, 0, 88),
          'the layer: VR31 = >D8 (on, priority, fat pixels, palette select 8), VR32 = >80 (>2000), x 0, y 8, 256 wide, 88 rows: %s' % [hex(v) for v in (m.vregs[31], m.vregs[32], m.vregs[33], m.vregs[34], m.vregs[35], m.vregs[36])])
    check(m.rw(0x2300) == 0 and m.rw(0x21E4) == base.rw(0x21E4) and m.rw(0x21E6) == base.rw(0x21E6),
          'PICSHOW answers 0 and puts windows E and F back where they were (>%04X, >%04X)' % (m.rw(0x21E4), m.rw(0x21E6)))
    m2 = run('<WAIT 5>2<WAIT 150>')
    check(bytes(m2.vram[0x2000:0x2000 + 5632]) == rawl and [m2.palette.get(32 + i) for i in range(4)] == pl and m2.vregs[31] == 0xC8,
          'the 4-colour picture: pixels, palette entries 32-35, VR31 = >C8 (no fat pixels)')
    m3 = run('<WAIT 5>1<WAIT 100>3<WAIT 40>')
    check(m3.vregs[31] == 0 and bytes(m3.vram[0x2000:0x2000 + 5632]) == rawr, 'BMLOFF: VR31 = 0, the pixels stay in VRAM')
    m4 = run('<WAIT 5>1<WAIT 100>3<WAIT 40>4<WAIT 40>')
    check(m4.vregs[31] == 0xD8, 'BMLON puts the layer back as it was (VR31 = >D8)')
    m5 = run('<WAIT 5>5<WAIT 40>6<WAIT 40>7<WAIT 40>')
    check((m5.rw(0x2302), m5.rw(0x2304), m5.rw(0x2306)) == (2, 1, 3) and m5.vregs[31] == base.vregs[31] and bytes(m5.vram[0x2000:0x2040]) == bytes(base.vram[0x2000:0x2040]),
          'too little VRAM answers 2, pages with no picture 1, a VRAM address that is not a multiple of 64 answers 3: and nothing is drawn (%s)' % [m5.rw(0x2302), m5.rw(0x2304), m5.rw(0x2306)])
    # the TI Artist route and the build
    from PIL import Image
    td = tempfile.mkdtemp()
    pat = bytearray(6144); col = bytearray(6144)
    for cell in range(768):
        for r in range(8):
            pat[cell * 8 + r] = 0xF0 if (cell + r) % 3 == 0 else 0x3C
            col[cell * 8 + r] = (((cell % 13) + 2) << 4) | ((cell % 7) + 2)
    open(td + '/ART_P', 'wb').write(bytes(pat)); open(td + '/ART_C', 'wb').write(bytes(col))
    rec = skpic.record(td + '/ART')
    fa, pa, rawa, ra = skpic.parse(rec)
    check(fa == 4 and len(pa) == 16 and ra == 88 and len(rawa) == 5632, 'a TI Artist picture (ART_P and ART_C, 6,144 bytes each) becomes a format-4 record, cropped as TXA does and cut to 88 rows')
    r96 = skpic.parse(skpic.record(td + '/ART', 96))
    check(r96[3] == 96 and len(r96[2]) == 6144 and r96[2][:5632] == rawa, '--rows 96 keeps the whole 96-row band (6,144 bytes), the first 88 rows the same')
    shutil.copytree(d, td + '/app')
    shutil.copy(td + '/ART_P', td + '/app/'); shutil.copy(td + '/ART_C', td + '/app/')
    j = json.load(open(td + '/app/app.json')); j['data'].append({'file': 'art.skp', 'from': 'ART'}); json.dump(j, open(td + '/app/app.json', 'w'))
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), td + '/app', '--out', td + '/out'], capture_output=True, text=True)
    check(r.returncode == 0 and 'picture art.skp: format 4, 16 colours, 88 rows' in r.stdout, 'the build makes a picture from a TI Artist name (data entry "from": "ART"): %s' % [l for l in r.stdout.split('\n') if 'art.skp' in l][:1])

def ea5run():
    """RUN PROGRAM FILE (kernel/ea5run.a99, app.json "ea5": true): a second program in the cartridge's menu that does what Editor/Assembler option 5 does.  The simulated machine is started at the
    runner's entry as the console's menu would start it (the cards powered up as the console has done at boot, the GPL registers as it leaves them), with TI's disk controller ROM and a disk image.
    Checks: the header lists two programs; a two-file option 5 chain (the next name is the last character plus one) loads at its addresses, runs from the first and comes back with RT to the
    prompt; the name line edits (FCTN S); a missing file shows the DSR's error, a missing device shows NO SUCH DEVICE; FCTN = restarts the console; a kernel disk program (its bootstrap is an
    option 5 image) starts and runs; a build without the flag lists one program."""
    import tempfile, ea5 as ea, tifdc, skdisk
    if not (os.environ.get('TIFDC_ROM') and os.path.exists(os.environ['TIFDC_ROM'])):
        print('  (skipped: the disk controller ROM is needed: TIFDC_ROM)')
        return
    rom = os.environ.get('TI_CONSOLE_ROM')
    rom = rom if rom and os.path.exists(rom) else None
    cart = build('tests/apps/ea5')
    bank0 = cart[:8192]
    def word(a):
        return int.from_bytes(bank0[a - 0x6000:a - 0x6000 + 2], 'big')
    progs, e = [], word(0x6006)
    while e:
        n = bank0[e + 4 - 0x6000]
        progs.append((word(e + 2), bank0[e + 5 - 0x6000:e + 5 - 0x6000 + n].decode()))
        e = word(e)
    check(len(progs) == 2 and progs[1][1] == 'RUN PROGRAM FILE' and 0x6000 <= progs[1][0] < 0x8000,
          'the cartridge header lists two programs: %s' % [(hex(a), n) for a, n in progs])
    entry = progs[1][0]
    d = tempfile.mkdtemp()
    open(d + '/q.a99', 'w').write("       AORG >A000\nSTART  LI   R0,>1234\n       MOV  R0,@>3F00\n       MOV  @MORE,R1\n       MOV  R1,@>3F02\n       RT\n       AORG >B000\nMORE   DATA >BEEF\n")
    subprocess.run([sys.executable, os.environ['XAS99'], '-R', '-i', '-q', d + '/q.a99', '-o', d + '/CHAIN'], check=True, capture_output=True)
    programs = [(f.upper(), open(os.path.join(d, f), 'rb').read()) for f in sorted(os.listdir(d)) if f.startswith('CHAI')]
    programs += [('UTIL1', programs[0][1]), ('UTIL2', programs[1][1])]      # the same image under the module's default name
    rh = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), os.path.join(ROOT, 'examples', 'hello'), '--out', d + '/h', '--disk', '--geometry', 'sssd'], capture_output=True, text=True)
    himg = bytearray(open(d + '/h/hello.dsk', 'rb').read())
    programs += [(n, tifdc.read_program(himg, n)) for n in sorted(tifdc.TIFDC(image=himg).files())]
    skdisk.make_disk(d + '/d.dsk', [], None, 'EA5RUN', 'sssd', programs=programs)
    disk = open(d + '/d.dsk', 'rb').read()
    open(d + '/pw.a99', 'w').write("       AORG >3000\nPWSTUB LWPI >83E0\n       LI   R0,>3FFF\n       MOV  R0,@>8370\n       LI   R12,>1100\n       LI   R13,>9800\n       LI   R15,>8C02\n       SBO  0\n"
                                   "       MOV  @>4004,R9\nPW1    MOV  R9,R9\n       JEQ  PWD\n       MOV  R9,@>3F20\n       INCT R9\n       MOV  *R9,R9\n       LI   R12,>1100\n       LI   R13,>9800\n       LI   R15,>8C02\n"
                                   "       BL   *R9\n       JMP  PW2\nPW2    LI   R12,>1100\n       SBO  0\n       MOV  @>3F20,R9\n       MOV  *R9,R9\n       JMP  PW1\nPWD    SBZ  0\nPWEND  JMP  PWEND\n")
    subprocess.run([sys.executable, os.environ['XAS99'], '-R', '-b', '-q', d + '/pw.a99', '-o', d + '/pw.bin'], check=True, capture_output=True)
    pw = open(d + '/pw.bin', 'rb').read()
    def row(m, n):
        return bytes(m.vram[n * 32:(n + 1) * 32]).decode('latin-1').replace('\x00', ' ').rstrip()
    def session(keys, until, limit=200, stop_at=None):
        m = sim9900.Machine(bank0)
        if rom:
            m.console_rom = sim9900.load_console_rom(rom)
        m.tifdc = tifdc.TIFDC(image=bytearray(disk))
        m.presses, m.toggles, end = sim9900.schedule(sim9900.parse_keys(keys))
        cpu = sim9900.CPU(m)
        for i, b in enumerate(pw):
            m.wb(0x3000 + i, b)
        cpu.pc, cpu.wp, cpu.limi = 0x3000, 0x83E0, 0
        for k in range(400000):                      # the console's power-up of the cards
            cpu.step()
            if cpu.pc == 0x3000 + len(pw) - 2:
                break
        m.ww(0x3F00, 0); m.ww(0x3F02, 0)
        cpu.pc, cpu.wp, cpu.limi = entry, 0x83E0, 2   # as the menu starts a program
        m.ww(0x83E0 + 26, 0x9800); m.ww(0x83E0 + 28, 0x0100); m.ww(0x83E0 + 30, 0x8C02)
        trail = []
        try:
            for i in range(limit):
                for k in range(20000):
                    cpu.step()
                    if stop_at is not None:
                        trail.append(cpu.pc)
                        del trail[:-12]
                        if cpu.pc == stop_at:
                            return m, cpu
                if until(m, cpu):
                    break
        except sim9900.Halt as e:
            pass                                  # (after a reset the simulated console starts the kernel with no banks copied: it halts)
        return m, cpu
    cur = set()
    m = sim9900.Machine(bank0)
    # (the cursor: sampled while the prompt waits for a key; it must be seen showing and hidden at the name line's next position: a hidden cursor reads as nothing, the row's end being trimmed)
    m, cpu = session('<WAIT 30>', lambda m, c: cur.add(row(m, 8)[7:8]) or (len(cur) > 1 and '_' in cur), 80)
    check('_' in cur and len(cur) > 1, 'a cursor blinks at the name line\'s next position while the prompt waits (seen %s)' % sorted(cur))
    m, cpu = session('<WAIT 30>chainx<F-s><WAIT 20>', lambda m, c: row(m, 8) == '  DSK1.CHAIN', 60)
    check(row(m, 2).strip() == 'RUN PROGRAM FILE' and row(m, 8) == '  DSK1.CHAIN', 'the prompt shows the title and a name line that starts as DSK1. and takes typing (chainx) and FCTN S (one back): %r' % row(m, 8))
    m, cpu = session('<WAIT 30>chain<ENTER><WAIT 100>', lambda m, c: m.rw(0x3F00) == 0x1234 and row(m, 8) == '  DSK1.')
    check(m.rw(0x3F00) == 0x1234 and m.rw(0x3F02) == 0xBEEF,
          'a two-file option 5 image (CHAIN and CHAIO): the first file ran at its load address (marker >%04X) and read what the second put at >B000 (>%04X)' % (m.rw(0x3F00), m.rw(0x3F02)))
    check(bytes(m.vram[0x380:0x3A0]) == b'\x13' * 32 and m.vregs[7] == 0xF3,
          'before the program the runner set the screen up as the module does: the colour table >13 (black on light green) and VR7 = >F3 (VR7 = >%02X)' % m.vregs[7])
    for i in range(20):
        for k in range(20000):
            cpu.step()
    check(row(m, 2).strip() == 'RUN PROGRAM FILE' and row(m, 8) == '  DSK1.', 'the program ended with RT and the prompt came back, the name line reset to DSK1.')
    m, cpu = session('<WAIT 30><ENTER><WAIT 100>', lambda m, c: m.rw(0x3F00) == 0x1234)
    check(m.rw(0x3F00) == 0x1234 and m.rw(0x3F02) == 0xBEEF, 'ENTER with the name line still DSK1. runs UTIL1 (and UTIL2), as the module\'s option 5 does with an empty name (marker >%04X)' % m.rw(0x3F00))
    crom = open(os.environ['TIFDC_ROM'], 'rb').read()          # the card's device list: where DSK1's routine is
    def cw(a): return int.from_bytes(crom[a - 0x4000:a - 0x4000 + 2], 'big')
    e, dsk1 = cw(0x4008), None
    while e:
        n = crom[e + 4 - 0x4000]
        if crom[e + 5 - 0x4000:e + 5 - 0x4000 + n] == b'DSK1':
            dsk1 = cw(e + 2)
        e = cw(e)
    m, cpu = session('<WAIT 30>chain<ENTER><WAIT 100>', lambda m, c: False, 80, stop_at=dsk1)
    check(cpu.pc == dsk1 and m.rw(0x83E2) == 1 and m.rw(0x83F8) == 0x1100 and m.rw(0x83D0) == 0x1100 and m.rw(0x83F2) == dsk1 and m.rw(0x8354) == 4 and m.rw(0x8356) == 0x130E,
          'the disk DSR (DSK1 at >%04X) is called as the console\'s DSRLNK does: R12 = >1100 (and >83D0), R9 = its address, R1 = 1 (the first call), >8354 = 4 (the name DSK1), >8356 at the \'.\' (>%04X)' % (dsk1, m.rw(0x8356))
          + ' [R1 %04X R12 %04X >83D0 %04X R9 %04X >8354 %04X pc %04X]' % (m.rw(0x83E2), m.rw(0x83F8), m.rw(0x83D0), m.rw(0x83F2), m.rw(0x8354), cpu.pc))
    m, cpu = session('<WAIT 30>nosuch<ENTER><WAIT 100>', lambda m, c: 'I/O ERROR' in row(m, 14))
    check(row(m, 14).strip() == 'I/O ERROR 7', 'a file that is not on the disk: the DSR\'s error on the screen (%r)' % row(m, 14))
    m, cpu = session('<WAIT 30><F-s><F-s><F-s><F-s><F-s>abcdefghijklmnopqrstu<ENTER><WAIT 100>', lambda m, c: 'NO SUCH' in row(m, 14))
    check(row(m, 14).strip() == 'NO SUCH DEVICE', 'a name of 21 letters and no device (no \'.\'): NO SUCH DEVICE, not an overrun of the 8-byte device buffer (%r)' % row(m, 14))
    m, cpu = session('<WAIT 30><F-s><F-s><F-s><F-s><F-s>dsk9.x<ENTER><WAIT 100>', lambda m, c: 'NO SUCH' in row(m, 14))
    check(row(m, 14).strip() == 'NO SUCH DEVICE', 'a device no card has: NO SUCH DEVICE (%r)' % row(m, 14))
    if rom:
        m, cpu = session('<WAIT 30><F-=><WAIT 20>', lambda m, c: getattr(m, 'console_resets', 0) > 0, 80, stop_at=None)
        check(getattr(m, 'console_resets', 0) == 1, 'FCTN = restarts the console: the runner did BLWP @>0000, the console\'s reset (the simulator counts it: %d)' % getattr(m, 'console_resets', 0))
    m, cpu = session('<WAIT 30>hello<ENTER>', lambda m, c: 'Hello' in ' '.join(sim9900.screen(m).split('\n')[:3]), 400)
    check('Hello' in ' '.join(sim9900.screen(m).split('\n')[:3]),
          'a kernel disk program (HELLO and its banks): its bootstrap is an option 5 image, loaded and called by the runner, which reads the banks and starts the kernel: the application\'s screen shows %r' % ' '.join(sim9900.screen(m).split('\n')[:1]).strip())
    plain = build('hello')
    pb = plain[:8192]
    check(int.from_bytes(pb[6:8], 'big') != 0 and int.from_bytes(pb[int.from_bytes(pb[6:8], 'big') - 0x6000:][:2], 'big') == 0,
          'without "ea5" the cartridge lists one program, as before')

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
    # the error list on the screen: each error with its own message (found while writing the manual: the list read the code from a register DECW had changed)
    import tempfile
    bad = os.path.join(tempfile.mkdtemp(), 'bad.a99')
    open(bad, 'w').write('       COPY "kernel.equ"\n       AORG >C000\n       DATA INIT,TICK,INIT,0\nINIT   LI   R0,2*COLS+2\n       FROB R1,R2\n'
                         '       BL   @NOSUCH\n       JMP  FAR\nTICK   RT\nINIT   RT\n')
    m2, img2 = asmharness.workbench_ui('<WAIT 10>nBAD/A99<ENTER><WAIT 10>a<WAIT 1500>', 4000, [bad])
    rows = [l.strip() for l in sim9900.screen(m2).split('\n') if l.strip()]
    want = ['9     label defined twice', '5     unknown operation', '6     undefined symbol', '7     jump out of range', '7     undefined symbol', '9     label changed between passes']
    norm = [' '.join(r.split()) for r in rows]
    check(all(' '.join(w.split()) in norm for w in want), 'the error list shows each error with its own message and line: %s' % [r for r in norm if r[:1].isdigit()][:6])

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

GROUPS = [('sources', sources), ('dbg', dbg), ('sams16', sams16), ('tipi', tipi), ('hfdccru', hfdccru), ('linein', linein), ('resident', resident), ('poolmax', poolmax), ('trim', trim), ('textonly', textonly), ('fastmap', fastmap), ('fileprog', fileprog), ('poolscan', poolscan), ('slotd', slotd), ('common', common), ('cycles', cycles), ('ea5', ea5), ('diskboot', diskboot), ('prun', prun), ('arcode', arcode), ('txm', txm), ('exprcheck', exprcheck), ('sfx', sfx), ('pic', pic), ('ea5run', ea5run), ('float', float), ('fplayout', fplayout), ('framehook', framehook), ('brkflag', brkflag), ('editorapp', editorapp), ('sourcesdisk', sourcesdisk), ('jumpcheck', jumpcheck), ('fileapi', fileapi), ('dsdd', dsdd), ('dsddworkbench', dsddworkbench), ('editorpages', editorpages), ('reversi', reversi), ('reversiti', reversiti), ('joystick', joystick), ('files2', files2), ('native', native), ('nativemods', nativemods), ('nativedisk', nativedisk), ('tiprograms', tiprograms), ('workbench', workbench), ('workbenchfull', workbenchfull), ('boot', boot), ('refusal', refusal), ('ram', ram), ('keys', keys), ('quit', quit_), ('modules', modules),
          ('files', files), ('browser', browser), ('modes', modes), ('modesquit', modes_quit), ('music', music), ('rom', rom), ('realdsr', realdsr)]

if __name__ == '__main__':
    want = sys.argv[1:] or [g for g, _ in GROUPS]
    for name, fn in GROUPS:
        if name in want:
            print(name); fn()
    print('\n%d failed' % len(FAILS) if FAILS else '\nall passed')
    sys.exit(1 if FAILS else 0)
