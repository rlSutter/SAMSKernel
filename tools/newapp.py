#!/usr/bin/env python3
"""newapp.py - start a SAMS Kernel application.

    python3 tools/newapp.py DIR [--name "MY APP"]

Writes DIR/app.json and DIR/main.a99: a one-module application that builds and
runs (it shows its name, echoes typing and quits on FCTN =).  Then:

    python3 tools/skbuild.py DIR
    python3 tools/sim9900.py build/DIR/myapp8.bin --keys "<ALPHA>hello"
"""
import json, os, sys

TEMPLATE = '''\
*======================================================================
* main.a99 - %(name)s's first module.  See docs/PROGRAMMERS-GUIDE.md.
*======================================================================
       COPY "kernel.equ"      the kernel's symbols
       COPY "macros.a99"      .enter .leave .push .pop .callmod

ATEXT  EQU  (RTEXT*16+RBG)*256        text on the page background
ABAR   EQU  (RBARFG*16+RBARBG)*256    the status bar
CURPOS EQU  APPRAM+0                  where the next character goes

       AORG >C000
       DATA INIT,TICK,REDRAW,0        entries: INIT, TICK, REDRAW, reserved

* INIT - switched to (R0 = the module before, R1 = GOMOD's argument).
INIT   .enter
       BL   @REDRAW
       .leave
       RT

* REDRAW - the whole screen.
REDRAW .enter
       LI   R1,ATEXT
       BL   @CLS
       CLR  R0
       LI   R1,ABAR
       LI   R2,COLS
       BL   @FILLA
       LI   R0,1
       LI   R1,TITLE
       LI   R2,ABAR
       BL   @PUTS
       LI   R0,3*COLS+2
       MOV  R0,@CURPOS
       .leave
       RT

* TICK - once a frame; R0 = the key typed (high byte) or 0.
TICK   .enter
       MOV  R0,R0
       JEQ  TK9
       CI   R0,KQUIT*256              FCTN = quits
       JNE  TK1
       SETO @QUITF
       JMP  TK9
TK1    CI   R0,>2000                  a printable character
       JL   TK9
       CI   R0,>7F00
       JHE  TK9
       MOV  R0,R1
       MOV  @CURPOS,R0
       LI   R2,ATEXT
       BL   @PUTC
       INC  @CURPOS
TK9    .leave
       RT

TITLE  STRI ' %(name)s'
       EVEN
'''

def main():
    a = sys.argv[1:]
    if not a or a[0].startswith('-'):
        print(__doc__); sys.exit(1)
    d = a[0]
    name = (a[a.index('--name') + 1] if '--name' in a else os.path.basename(d.rstrip('/'))).upper()
    os.makedirs(d, exist_ok=True)
    if os.path.exists(os.path.join(d, 'app.json')):
        sys.exit('newapp: %s/app.json exists' % d)
    json.dump({'name': name, 'min_pages': 128, 'modules': [{'name': 'main', 'source': 'main.a99'}]},
              open(os.path.join(d, 'app.json'), 'w'), indent=2)
    open(os.path.join(d, 'main.a99'), 'w').write(TEMPLATE % {'name': name})
    print('wrote %s/app.json and %s/main.a99' % (d, d))

if __name__ == '__main__':
    main()
