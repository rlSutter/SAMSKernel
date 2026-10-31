#!/usr/bin/env python3
"""mksources.py - a 360K TI disk of the kernel's sources, to read and edit on the TI.

    python3 tools/mksources.py out.dsk

The disk (volume SOURCES, double-sided double-density: for a CorComp, Myarc or HFDC card, a TIPI or CF7+,
js99er's generic controller) holds kernel/*.a99, lib/*.a99, the generated gen/font.a99 and gen/keytab.a99,
the kernel's stub for "no resident code" (KRES/A99), hello and the editor example's front module, and
a text file, SRCNOTES, that says how it differs from the repository.

A TI file name is at most 10 characters, "NAME/A99" for NAME.a99, so a source file whose name is longer than
six characters does not fit: three kernel files, amsinit, databank and modules, are stored as AMSINI, DATABK and
MODULE (and the kresident.a99 that the build writes, as KRES), and the COPY lines that name them are changed in the
copies on the disk to match (the repository's files are not touched).  Not on the disk: appcfg.a99, appname.a99 and appmsg.a99, which tools/skbuild.py writes for each
application, so the kernel cannot yet be assembled on the TI from this disk; SRCNOTES says what else stands in the way.
"""
import glob, os, re, shutil, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import skdisk

RENAMES = {'amsinit': 'amsini', 'databank': 'databk', 'modules': 'module', 'kresident': 'kres'}
NOTES = """SOURCES - the SAMS Kernel's sources, to read and edit on the TI.

Every file is DIS/VAR 80.  Open one in the workbench: N, the name, then E.
(NAME/A99 on the disk is NAME.a99 in the repository.)

FOUR FILES HAVE SHORTER NAMES: a TI file name has 10 characters at most.
   MODULE/A99  is modules.a99      AMSINI/A99  is amsinit.a99
   DATABK/A99  is databank.a99     KRES/A99    is kresident.a99
The COPY lines that name them are changed in the copies here to match.

ALSO HERE: the generated FONT/A99 and KEYTAB/A99 (tools/font.py and keytab.py
write them), and KRES/A99, the stub that stands in for an application's
resident code when it has none (the build writes one for each application).
LINEIN/A99 (lib/linein.a99) is the optional line editor.  HELLO/A99 and
FRONT/A99 (the editor example's front module) are two programs for the
workbench's disk.

NOT HERE: APPCFG/A99, APPNAME/A99 and APPMSG/A99.  The build writes them for
each application from its app.json.  So the kernel cannot be assembled on the
TI from this disk yet.  What else stands in the way: the TI assembler's output
is at most 4,096 bytes (the kernel is about 6,700); its symbol table holds 580
names (the kernel has about 600); and the cartridge image has to be packed
from the banks, which tools/skbuild.py does on the PC.

A change here is not in the repository until it is copied back.
"""


def build(out):
    """Write the disk image to OUT; returns {disk name: text} of every file on it."""
    tmp = tempfile.mkdtemp()
    names, files = {}, []
    srcs = (sorted(glob.glob(os.path.join(ROOT, 'kernel', '*.a99'))) + sorted(glob.glob(os.path.join(ROOT, 'lib', '*.a99'))) +
            sorted(glob.glob(os.path.join(ROOT, 'gen', '*.a99'))) +
            [os.path.join(ROOT, 'examples', 'hello', 'hello.a99'), os.path.join(ROOT, 'examples', 'editor', 'front.a99')])
    for f in srcs:
        base = os.path.basename(f)[:-4]
        text = open(f, encoding='latin-1').read()
        for long_, short in RENAMES.items():
            text = re.sub(r'(COPY\s+")%s\.a99"' % long_, r'\g<1>%s.a99"' % short, text)
        disk = RENAMES.get(base, base)
        if len(disk) + 4 > 10:
            sys.exit('mksources: %s.a99 has no short name' % base)
        names[disk.upper() + '/A99'] = text
    names['KRES/A99'] = '* no resident code\nKRESB\nKRESE\n'
    names['SRCNOTES'] = NOTES
    for n, text in sorted(names.items()):
        p = os.path.join(tmp, n.replace('/', '.').lower())
        open(p, 'w', encoding='latin-1').write(text)
        files.append(p)
    skdisk.make_disk(out, files, None, 'SOURCES', 'dsdd')
    shutil.rmtree(tmp, ignore_errors=True)
    return names


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    n = build(sys.argv[1])
    print('wrote %s: %d files' % (sys.argv[1], len(n)))
