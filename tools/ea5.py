#!/usr/bin/env python3
"""ea5.py - Editor/Assembler option 5 ("RUN PROGRAM FILE") for the simulator, so that a disk-started program can be tested without E/A.

    import ea5
    entry = ea5.load(machine, disk_image, 'HELLO')     # puts the image's segments in the machine's RAM; returns the start address
    cpu.pc = entry                                     # (the caller sets up the machine: console, mapper off, disk card)

An option 5 image is a chain of PROGRAM files.  Each starts with a six-byte header: a flag word (>FFFF if another file follows, else 0), the length of
the data that follows, and the address to load it at.  The next file's name is the previous name with its last character incremented (E/A's SAVE and
xdt99's `xas99 -i` use that convention).  The program starts at the first file's load address.  This follows xdt99's manual for the format and
the convention; it has not been checked against a real E/A cartridge, which is what the disk-start work's hardware checklist is for.
"""
import tifdc


def parse(data):
    """(address, bytes, more) for one image file's data"""
    flag = (data[0] << 8) | data[1]
    length = (data[2] << 8) | data[3]
    addr = (data[4] << 8) | data[5]
    return addr, data[6:6 + length], flag != 0


def next_name(name):
    """the name of the next file in a chain: the last character incremented"""
    return name[:-1] + chr(ord(name[-1]) + 1)


def segments(image, name):
    """[(address, bytes), ...] of the whole chain starting at file NAME of the disk image; raises if a file is missing"""
    out = []
    while True:
        data = tifdc.read_program(image, name)
        if data is None:
            raise FileNotFoundError('E/A option 5: file %s is not on the disk' % name)
        addr, body, more = parse(data)
        out.append((addr, body))
        if not more:
            return out
        name = next_name(name)


def load(m, image, name):
    """load the chain into the machine's memory the way option 5 does; return the entry address (the first file's load address)"""
    segs = segments(image, name)
    for addr, body in segs:
        for i, b in enumerate(body):
            m.wb(addr + i, b)
    return segs[0][0]
