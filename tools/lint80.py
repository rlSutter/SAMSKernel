#!/usr/bin/env python3
"""lint80.py - are the sources safe to edit on a TI?

    python3 tools/lint80.py [--fix] [FILE ...]      (no files: kernel/*.a99, lib/*.a99 and examples/*/*.a99)

A TI text file (DIS/VAR 80) holds 80 columns of ASCII, and an editor on the TI cuts, splits or refuses a longer
line: a trailing comment would be lost, but a string or a DATA list would be damaged.  So every source line must be
at most 80 columns, plain ASCII, with no tabs.  --fix repairs what it can without changing a byte of the program:
a comment past column 80 moves to comment lines above the instruction, a long whole-line comment is re-wrapped,
a long STRI becomes BYTE and TEXT lines, a long DATA or BYTE list becomes several.  The build's images must come out
identical; tests/test_kernel.py (group "sources") checks the lint, and skbuild's output is how you check the fix.
"""
import glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 80
NOOPERAND = {'RT', 'RTWP', 'NOP', 'IDLE', 'RSET', 'CKON', 'CKOF', 'LREX', 'EVEN', '.ENTER', '.LEAVE', '.INTSVC', '.ENDM', 'END'}


def split_line(line):
    """-> (label, opcode, operand, comment, widths) for an assembler line, or None for a comment/blank."""
    if not line.strip() or line.startswith('*'):
        return None
    m = re.match(r'^(\S*)(\s+)(\S+)(\s*)', line)
    if not m:
        return None
    label, sp1, op, sp2 = m.group(1), m.group(2), m.group(3), m.group(4)
    rest = line[m.end():]
    if op.upper() in NOOPERAND or not rest:
        operand, comment = '', (sp2 + rest).strip()
        return label, op, operand, comment
    # the operand ends at the first blank outside quotes
    i, inq = 0, False
    while i < len(rest):
        ch = rest[i]
        if ch == "'":
            inq = not inq
        elif ch == ' ' and not inq:
            break
        i += 1
    return label, op, rest[:i], rest[i:].strip()


def wrap_comment(text, indent, width=LIMIT - 1):
    words, out, cur = text.split(), [], ''
    for w in words:
        if cur and len(indent) + len(cur) + 1 + len(w) > width:
            out.append(cur); cur = w
        else:
            cur = (cur + ' ' + w) if cur else w
    if cur: out.append(cur)
    return [indent + l for l in out]


def fix_line(line):
    if len(line) <= LIMIT:
        return [line]
    if line.startswith('*'):
        m = re.match(r'^(\*\s*)(.*)$', line)
        lead = m.group(1)
        lead = lead if len(lead) <= 12 else '* '
        return wrap_comment(m.group(2), lead)
    parts = split_line(line)
    if not parts:
        return [line]
    label, op, operand, comment = parts
    lab = (label + ' ' * max(1, 7 - len(label))) if label else ' ' * 7
    code = lab + op.ljust(5) + ' ' + operand if operand else lab + op
    code = code.rstrip()
    up = op.upper()
    if len(code) <= LIMIT:
        out = wrap_comment(comment, '* ') if comment else []
        return out + [code]
    if up == 'STRI':
        s = operand[1:-1]
        raw = s.replace("''", "'")
        chunks, cur = [], ''
        for ch in raw:
            cur += ch
            if len(cur) >= 56: chunks.append(cur); cur = ''
        if cur: chunks.append(cur)
        # the length is the difference of two labels, so editing the text later cannot leave it stale
        base = label if label else 'S%04d' % (abs(hash(operand)) % 10000)
        out = [lab + 'BYTE %sE-%sB' % (base, base)]
        lb = '%sB' % base
        out += [lb + ' ' * max(1, 7 - len(lb)) + 'TEXT \'' + chunks[0].replace("'", "''") + '\'']
        out += ['       TEXT \'' + c.replace("'", "''") + '\'' for c in chunks[1:]]
        out += ['%sE' % base]
        return out
    if up in ('DATA', 'BYTE'):
        items = operand.split(',')
        out, first = [], True
        for k in range(0, len(items), 8):
            lab2 = lab if first else ' ' * 7
            out.append(lab2 + up.ljust(5) + ' ' + ','.join(items[k:k + 8])); first = False
        return out
    return [line]


def problems(path):
    out = []
    for i, l in enumerate(open(path, 'rb').read().split(b'\n'), 1):
        l = l.rstrip(b'\r')
        if len(l) > LIMIT: out.append((i, 'over %d columns (%d)' % (LIMIT, len(l))))
        if any(b > 127 for b in l): out.append((i, 'not ASCII'))
        if b'\t' in l: out.append((i, 'a tab'))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    files = args or sorted(glob.glob(os.path.join(ROOT, 'kernel', '*.a99')) + glob.glob(os.path.join(ROOT, 'lib', '*.a99')) + glob.glob(os.path.join(ROOT, 'examples', '*', '*.a99')))
    files = [g for f in files for g in (sorted(glob.glob(os.path.join(f, '*.a99'))) if os.path.isdir(f) else [f])]
    bad = 0
    for f in files:
        if '--fix' in sys.argv:
            lines = open(f, encoding='latin-1').read().split('\n')
            new = []
            for l in lines: new += fix_line(l)
            open(f, 'w', encoding='latin-1').write('\n'.join(new))
        for ln, what in problems(f):
            print('%s:%d: %s' % (os.path.relpath(f, ROOT), ln, what)); bad += 1
    print('%d problems in %d files' % (bad, len(files)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
