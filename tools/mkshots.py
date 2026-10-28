#!/usr/bin/env python3
"""mkshots.py - docs/images/mode-*.png: every screen of examples/modes, drawn by
tools/f18render.py from the simulator.  Run after tools/lkbuild.py examples/modes."""
import glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import sim9900, f18render
from PIL import Image
NAMES = {'1': 'text80-30', '2': 'text80-24', '3': 'text40-24', '4': 'text40-30', '5': 'graphics1', '6': 'graphics2',
         '7': 'multicolor', '8': 'ecm1-text80', '9': 'ecm2-text40', '0': 'ecm3-graphics1', 'a': 'sprites', 'b': 'sprites-ecm3',
         'c': 'tile-layer-2', 'd': 'bitmap-layer-4', 'e': 'bitmap-layer-16'}
def main():
    cart = open(glob.glob(os.path.join(ROOT, 'build', 'modes', '*8.bin'))[0], 'rb').read()
    os.makedirs(os.path.join(ROOT, 'docs', 'images'), exist_ok=True)
    for key, name in NAMES.items():
        m, cpu, halt = sim9900.run(cart, keys='<WAIT 5>' + key + '<WAIT 20>', frames=900)
        im = Image.fromarray(f18render.render(m))
        k = 1 if im.width >= 512 else 2
        im = im.resize((im.width * k, im.height * k), Image.NEAREST)
        path = os.path.join(ROOT, 'docs', 'images', 'mode-%s.png' % name)
        im.save(path, optimize=True)
        print(path, im.size)
if __name__ == '__main__':
    main()
