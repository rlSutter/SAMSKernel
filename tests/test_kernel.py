#!/usr/bin/env python3
"""Lantern Kernel tests: the example applications run in tools/sim9900.py.

  python3 tests/test_kernel.py [group ...]      (no names: all)

Groups: boot refusal ram keys quit modules files browser rom
Builds the examples first (tools/lkbuild.py; XAS99 or ./xdt99 needed).
The 'rom' group runs the real console ROM's interrupt routine when
TI_CONSOLE_ROM names your own copy of the 8K console ROM (a raw dump, or
an EA5 image); without it the group is skipped.  The ROM is TI's code and
is never part of this repository.
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
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'lkbuild.py'),
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
    check('Hello, Lantern Kernel' in lines(m)[0], 'the module drew its title')
    check(m.rw(0x834C) == 128 and m.rw(0x8348) == 1 and m.rw(0x834A) == 0x19, 'NPAGES 128, F18A found, version 1.9')
    check(m.scratch[0xC2] == 0x50 and m.scratch[0xFC] == 1, 'ISR flags >50, frame increment set')
    check(m.palette.get(1) == 0x23A and m.palette.get(2) == 0xDDE, 'colour scheme 0 in the palette')
    check(bytes(m.vram[0x1000 + 65 * 8:0x1000 + 66 * 8]) == bytes([0x70, 0x88, 0x88, 0x88, 0xF8, 0x88, 0x88, 0]), 'glyph A in the pattern table')
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

GROUPS = [('boot', boot), ('refusal', refusal), ('ram', ram), ('keys', keys), ('quit', quit_), ('modules', modules),
          ('files', files), ('browser', browser), ('rom', rom)]

if __name__ == '__main__':
    want = sys.argv[1:] or [g for g, _ in GROUPS]
    for name, fn in GROUPS:
        if name in want:
            print(name); fn()
    print('\n%d failed' % len(FAILS) if FAILS else '\nall passed')
    sys.exit(1 if FAILS else 0)
