#!/usr/bin/env python3
"""Press 2.0's keyboard tables -> gen/keytab.a99.

The TI-99/4A keyboard matrix: six columns (selected on 9901 outputs 18-20)
by eight rows (inputs 3-10).  Row r of column c is bit r of the byte the
scanner stores for that column (input 3 = bit 0).  Column 0 holds = SPACE
ENTER and the modifiers FCTN (row 4), SHIFT (row 5), CTRL (row 6).

Four tables of 48 codes (column * 8 + row), one per modifier:

    KTABN  no modifier: lower-case letters, digits, = SPACE ENTER . , / ;
    KTABS  SHIFT: capitals, ! @ # $ % ^ & * ( ), + < > : -
    KTABF  FCTN: the characters the keycaps show (| ` { } ? ' " [ ] _ ~ \\);
           every other key >C0 | (its code AND >3F)
    KTABC  CTRL: >80 | (the key's code AND >3F)

A 0 entry means no code (the modifiers themselves, unused positions).
ENTER is >0D with every modifier but CTRL (>8D).  ALPHA LOCK capitalises
letters in KTABN only, in the scanner.  Precedence: FCTN, then CTRL, then
SHIFT.  The same tables drive tools/m0_test.py's expectations.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MATRIX = [
    ['=', ' ', '\r', None, 'FCTN', 'SHIFT', 'CTRL', None],
    list('.LO92SWX'),
    list(',KI83DEC'),
    list('MJU74FRV'),
    list('NHY65GTB'),
    list('/;P01AQZ'),
]
SHIFTED = dict(zip('1234567890=,.;/', '!@#$%^&*()+<>:-'))
FCTNCH = {'A': '|', 'C': '`', 'F': '{', 'G': '}', 'I': '?', 'O': "'", 'P': '"',
          'R': '[', 'T': ']', 'U': '_', 'W': '~', 'Z': '\\'}

def code(key, mod):
    if key is None or key in ('FCTN', 'SHIFT', 'CTRL'):
        return 0
    k = ord(key)
    if key == '\r':
        return 0x8D if mod == 'C' else 0x0D
    if mod == 'N':
        return ord(key.lower())
    if mod == 'S':
        return ord(SHIFTED.get(key, key.upper()))
    if mod == 'F':
        return ord(FCTNCH[key]) if key in FCTNCH else 0xC0 | (k & 0x3F)
    if mod == 'C':
        return 0x80 | (k & 0x3F)

def tables():
    return {m: [code(MATRIX[c][r], m) for c in range(6) for r in range(8)] for m in 'NSFC'}

def main():
    t = tables()
    out = os.path.join(ROOT, 'gen', 'keytab.a99')
    with open(out, 'w') as f:
        f.write('* gen/keytab.a99 - made by tools/keytab.py; do not edit\n')
        f.write('* 48 codes each (column * 8 + row): no modifier, SHIFT, FCTN, CTRL\n')
        for m, label in zip('NSFC', ('KTABN', 'KTABS', 'KTABF', 'KTABC')):
            row = t[m]
            for i in range(0, 48, 8):
                lab = label if i == 0 else ''
                f.write('%-6s BYTE %s\n' % (lab, ','.join('>%02X' % b for b in row[i:i + 8])))
    print('wrote', out)

if __name__ == '__main__':
    main()
