#!/usr/bin/env python3
"""jumpcheck.py - which jumps in an assembler listing are close to the edge of their range?

    python3 tools/jumpcheck.py LISTING [LISTING ...] [--margin N] [--top N]

A TMS9900 jump (JMP, JEQ, JNE, JL, JH, JHE, JLE, JGT, JLT, JOC, JNC, JNO, JOP) reaches 128 words back or
127 forward.  Adding code between a jump and its target pushes it out of range, and the assembler's message
("Out of range: LABEL +/- 0x81") appears in whichever file the jump happens to be in, far from the change that
caused it.  This lists the jumps with N words or fewer to spare (default 6), tightest first, so that the next
one to break is known before it does.  LISTING is a .lst file the build keeps (build/APP/kernel.lst,
build/APP/MODULE.lst).  Exit status 0 always: it reports, it does not judge.
"""
import re, sys

JUMPS = {'JMP', 'JEQ', 'JNE', 'JL', 'JH', 'JHE', 'JLE', 'JGT', 'JLT', 'JOC', 'JNC', 'JNO', 'JOP'}
LINE = re.compile(r'^(\d+):?\s*(\d{4})\s+([0-9A-F]{4})\s+([0-9A-F]{4})\s+\S+\s+(?:(\S+)\s+)?([A-Z]+)\s+(\S+)')


def scan(path):
    """[(spare words, line text, displacement)] for every jump in the listing."""
    out = []
    for n, raw in enumerate(open(path, encoding='latin-1'), 1):
        m = re.match(r'^(\d{4})\s+([0-9A-F]{4})\s+([0-9A-F]{4})\s+(\S+)\s+(.*)$', raw.rstrip('\n'))
        if not m:
            continue
        word = int(m.group(3), 16)
        rest = m.group(5)
        # the mnemonic is the first token that is a jump (a label may come before it)
        toks = rest.split()
        op = next((t for t in toks[:2] if t.upper() in JUMPS), None)
        if not op or (word & 0xFF00) not in range(0x1000, 0x1E00):
            continue
        disp = word & 0xFF
        if disp > 127:
            disp -= 256
        spare = 127 - disp if disp >= 0 else 128 + disp
        out.append((spare, '%s line %s: %s' % (path, m.group(1), ' '.join(toks[:4])), disp))
    return sorted(out)


def main(argv):
    margin, top, files = 6, 20, []
    i = 0
    while i < len(argv):
        if argv[i] == '--margin':
            margin = int(argv[i + 1]); i += 2
        elif argv[i] == '--top':
            top = int(argv[i + 1]); i += 2
        else:
            files.append(argv[i]); i += 1
    if not files:
        print(__doc__)
        return 0
    rows = []
    for f in files:
        rows += scan(f)
    rows.sort()
    near = [r for r in rows if r[0] <= margin]
    print('%d jumps; %d with %d words or fewer to spare' % (len(rows), len(near), margin))
    for spare, text, disp in near[:top]:
        print('  %3d to spare (%+d)  %s' % (spare, disp, text))
    if len(near) > top:
        print('  ... and %d more' % (len(near) - top))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
