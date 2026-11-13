# obj2ea5 demo

Two object files linked by `tools/obj2ea5.py` into an image for RUN PROGRAM FILE (docs/OBJ2EA5.md):

    python3 ~/xdt99/xas99.py -R main.a99 -o main.obj
    python3 ~/xdt99/xas99.py -R lib.a99 -o lib.obj
    python3 ../../tools/obj2ea5.py lib.obj main.obj --disk obj2ea5-demo.dsk --name LINKA

On the console: RUN PROGRAM FILE, `DSK1.LINKA`: `LINKED FROM TWO OBJECT FILES` on row 12 for about three seconds, then
the prompt again. The release has the disk as `images/obj2ea5-demo.dsk` (checklist R5).
