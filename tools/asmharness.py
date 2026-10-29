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
    r0 = call(m, cpu, syms['asmgo'])
    res = Result()
    res.errors = r0[0]
    res.length = m.rw(base + 524)
    res.org = m.rw(base + 520)
    res.image = bytes(m.rb(base + 1024 + i) for i in range(res.length))
    res.errtab = [(m.rw(base + 640 + 4 * i), m.rw(base + 642 + 4 * i)) for i in range(min(res.errors, 24))]
    res.machine = m
    return res
