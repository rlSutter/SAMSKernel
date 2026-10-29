#!/usr/bin/env python3
"""asmharness.py - run the workbench's native assembler in the simulator on a source file.

    import asmharness
    r = asmharness.assemble('examples/hello/hello.a99', kernel_app='hello')
    r.errors, r.image           # the number of errors, the bytes
Used by tests/test_kernel.py (group "native") to check the on-TI assembler against xas99.
"""
import glob, os, re, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import sim9900, skdisk


class Result:
    pass


def symbols(path):
    t = open(path).read().lower()
    return {m.group(1): int(m.group(2), 16) for m in re.finditer(r'^(\S+):\s*\n\s*equ\s+>([0-9a-f]+)', t, re.M)}


def build_workbench():
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), os.path.join(ROOT, 'examples', 'workbench')],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stdout + r.stderr)
    b = os.path.join(ROOT, 'build', 'workbench')
    return open(glob.glob(os.path.join(b, '*8.bin'))[0], 'rb').read(), symbols(os.path.join(b, 'asm.equ')), os.path.join(b, 'kernel.equ')


def call(m, cpu, addr, regs=None, limit=60_000_000):
    """Call the routine at addr as BL would, in the running machine; returns the register file."""
    saved = (cpu.wp, cpu.pc, cpu.st, cpu.limi, [cpu.reg(i) for i in range(16)])
    cpu.limi = 0
    sentinel = 0x7FFE
    cpu.wp = 0x8300
    for i, v in (regs or {}).items():
        cpu.setreg(i, v)
    cpu.setreg(11, sentinel)
    cpu.pc = addr
    start = m.insns
    while cpu.pc != sentinel:
        cpu.step()
        if m.insns - start > limit:
            raise RuntimeError('the routine at >%04X ran %d instructions without returning (PC=%04X)' % (addr, limit, cpu.pc))
    out = [cpu.reg(i) for i in range(16)]
    cpu.wp, cpu.pc, cpu.st, cpu.limi, regs0 = saved
    for i, v in enumerate(regs0):
        cpu.m.ww(0x8300 + 2 * i, v)
    return out


def assemble(source, kernel_app, extra=(), name=None, rom=None):
    """Assemble `source` (a host file) on the simulated TI with the workbench's assembler; the files in
    `extra` are put on the disk too, with the kernel.equ of examples/<kernel_app>."""
    import tifdc
    cart, syms, own_equ = build_workbench()
    equ = os.path.join(ROOT, 'build', kernel_app, 'kernel.equ')
    if not os.path.exists(equ):
        subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'skbuild.py'), os.path.join(ROOT, 'examples', kernel_app)], capture_output=True)
    d = tempfile.mkdtemp()
    img_path = os.path.join(d, 'disk.dsk')
    skdisk.make_disk(img_path, [source] + list(extra), equ)
    img = bytearray(open(img_path, 'rb').read())
    m = sim9900.Machine(cart)
    if rom:
        m.console_rom = sim9900.load_console_rom(rom)
    m.tifdc = tifdc.TIFDC(image=img)
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m)
    cpu.pc = m.rw(m.rw(0x6006) + 2)
    while m.insns < 100 * sim9900.VSYNC_INSNS:
        cpu.step()
    fname = (name or ('DSK1.' + os.path.basename(source).upper().replace('.', '/'))).encode('ascii')
    base = 0x2300
    m.vram  # (the machine is live)
    for i, b in enumerate(bytes([len(fname)]) + fname):
        m.wb(base + i, b)
    pg = int(re.search(r'pg_asm:\s*equ\s+>([0-9a-f]+)', open(own_equ).read().lower()).group(1), 16)
    m.map[0xC], m.map[0xD] = pg, pg + 1          # the assembler's pages in slot C, as MODCALL would put them
    r0 = call(m, cpu, syms['asmgo'])
    res = Result()
    res.errors = r0[0]
    res.length = m.rw(base + 524)
    res.org = m.rw(base + 520)
    res.image = bytes(m.rb(base + 1024 + i) for i in range(res.length))
    res.errtab = [(m.rw(base + 640 + 4 * i), m.rw(base + 642 + 4 * i)) for i in range(min(res.errors, 24))]
    res.machine = m
    return res


# ---- driving the workbench itself: keys in, screen and disk out -----------------------------------
def workbench_ui(keys, frames, files=(), rom=None, setup2=None):
    """Boot the workbench with a disk holding `files` (and KERNEL.EQU), play the key script; returns
    (machine, the disk image as it ends)."""
    import tifdc
    cart, syms, own_equ = build_workbench()
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'disk.dsk')
    skdisk.make_disk(p, list(files), own_equ)
    img = bytearray(open(p, 'rb').read())
    box = {}

    def setup(m):
        box['fdc'] = tifdc.TIFDC(image=img)
        m.tifdc = box['fdc']
        if setup2:
            setup2(m)
    m, cpu, halt = sim9900.run(cart, keys=keys, frames=frames, setup=setup, rom=rom)
    if halt:
        raise RuntimeError(halt)
    return m, box['fdc'].image


def editor_lines(m):
    """The editor's buffer, line by line, read out of SAMS."""
    pgfree = int(re.search(r'pgfree:\s*equ\s+>([0-9a-f]+)', open(os.path.join(ROOT, 'build', 'workbench', 'kernel.equ')).read().lower()).group(1), 16)
    n = m.rw(0x2300 + 128)
    o = m.ams[(pgfree + 20) * 4096:(pgfree + 20) * 4096 + 2 * n]
    out = []
    for i in range(n):
        s = o[2 * i] << 8 | o[2 * i + 1]
        pg, off = pgfree + 4 + s // 51, (s % 51) * 80
        out.append(bytes(m.ams[pg * 4096 + off:pg * 4096 + off + 80]).rstrip().decode('latin-1'))
    return out


def assemble_standin(files, main, kernel_app='workbench'):
    """Assemble `main` (a TI name like 'SUB.MAIN/A99' on DSK1) on the simulated TI whose drive is the simulator's
    stand-in (so a name may have directories, as on a TIPI): `files` maps TI names to lists of lines."""
    cart, syms, own_equ = build_workbench()
    m = sim9900.Machine(cart)
    for name, lines in files.items():
        m.dvfiles[name] = [l.encode('latin-1') for l in lines]
    m.dvfiles['KERNEL/EQU'] = [l.encode('latin-1') for l in skdisk.equ_lines(own_equ).split('\n') if l]
    m.presses, m.toggles, end = sim9900.schedule([])
    cpu = sim9900.CPU(m)
    cpu.pc = m.rw(m.rw(0x6006) + 2)
    while m.insns < 100 * sim9900.VSYNC_INSNS:
        cpu.step()
    fname = ('DSK1.' + main).encode('ascii')
    base = 0x2300
    for i, b in enumerate(bytes([len(fname)]) + fname):
        m.wb(base + i, b)
    pg = int(re.search(r'pg_asm:\s*equ\s+>([0-9a-f]+)', open(own_equ).read().lower()).group(1), 16)
    m.map[0xC], m.map[0xD] = pg, pg + 1
    r0 = call(m, cpu, syms['asmgo'], limit=200_000_000)
    res = Result()
    res.errors = r0[0]
    res.length = m.rw(base + 524)
    res.image = bytes(m.rb(base + 1024 + i) for i in range(res.length))
    res.errtab = [(m.rw(base + 640 + 4 * i), m.rw(base + 642 + 4 * i)) for i in range(min(res.errors, 24))]
    res.machine = m
    return res
