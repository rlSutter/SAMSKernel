#!/usr/bin/env python3
# Vendored from the TXA project (tools/rlepack.py), MIT, (c) 2026 Rebecca Sutter; tools/skpic.py builds the kernel's picture records on it.
"""rlepack.py - the picture run-length format (decoded by src/rle.a99).

   >00->7F  n: the next n+1 bytes are literal (1-128)
   >80->FE  n: the next byte repeats n - >7D times (3-129)
   >FF      end
Runs of three or more equal bytes become repeats; everything else is
gathered into literal runs.  unpack() is the reference decoder the tests
check the assembly decoder against."""

def pack(data):
    out, lit, i, n = bytearray(), bytearray(), 0, len(data)
    def flush():
        while lit:
            chunk = lit[:128]; del lit[:128]
            out.append(len(chunk) - 1); out.extend(chunk)
    while i < n:
        j = i
        while j < n and data[j] == data[i] and j - i < 129:
            j += 1
        if j - i >= 3:
            flush(); out.append(j - i + 0x7D); out.append(data[i]); i = j
        else:
            lit.append(data[i]); i += 1
    flush(); out.append(0xFF)
    return bytes(out)

def unpack(blob):
    out, i = bytearray(), 0
    while blob[i] != 0xFF:
        c = blob[i]; i += 1
        if c < 0x80:
            out += blob[i:i + c + 1]; i += c + 1
        else:
            out += bytes([blob[i]]) * (c - 0x7D); i += 1
    return bytes(out)

if __name__ == '__main__':
    import os
    for t in [b'', b'a', b'aa', b'aaa', b'ab' * 200, b'x' * 1000, os.urandom(3000)]:
        assert unpack(pack(t)) == t
    print('rlepack self-test ok')
