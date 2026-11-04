#!/usr/bin/env python3
"""exprcheck.py - find assembler expressions that xas99 would evaluate differently from arithmetic.

xas99 evaluates an expression strictly left to right, with no precedence: `STGEO+8*16+14` is ((STGEO+8)*16)+14, not STGEO+(8*16)+14.  In Press, `MOV @STGEO+8*16+14,R1`
meant a style's line height and assembled as a word of the kernel's own code: it gave the right value until the kernel moved 12 bytes.  This reports every operand where a `+` or `-`
is followed by a `*` or `/` outside parentheses (parenthesised parts are safe).  Written by the Press session (4 November 2026, MIT) and taken in from its note.

    python3 tools/exprcheck.py FILE...        prints file:line: the line, for each hazard; exit 1 if any
"""
import re
import sys


def hazards(lines):
    """(line number, text) of operands xas99 would evaluate differently from arithmetic."""
    for n, line in enumerate(lines, 1):
        if line.startswith('*') or not line.strip():
            continue
        parts = line.rstrip('\n').split(None, 3) if not line[0].isspace() else [''] + line.split(None, 2)
        if len(parts) < 3 or parts[1].upper() in ('TEXT', 'STRI', 'TITL', 'IDT', 'COPY'):
            continue
        operand = re.sub(r"'[^']*'", 'Q', parts[2].split(None, 1)[0] if parts[2].strip() else '')
        while re.search(r'\([^()]*\)', operand):
            operand = re.sub(r'\([^()]*\)', 'P', operand)
        if re.search(r'[+\-][^,]*[*/]', operand):
            yield n, line.strip()


def main(argv):
    bad = 0
    for path in argv:
        for n, text in hazards(open(path, encoding='latin-1').read().split('\n')):
            print('%s:%d: %s' % (path, n, text))
            bad += 1
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
