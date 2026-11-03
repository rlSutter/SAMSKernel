#!/usr/bin/env python3
"""skmusic.py - make SKM music for the SAMS Kernel from a MIDI file or a text score.

    python3 tools/skmusic.py song.txm -o song.skm --loop     a TXA notation file (.txm: the default notation, below)
    python3 tools/skmusic.py tune.mml -o tune.skm            a text score (MML, below)
    python3 tools/skmusic.py song.mid -o song.skm --loop      a MIDI file
    python3 tools/skmusic.py tune.mml --wav tune.wav --info   hear it, and see what it came to

TXA notation (.txm, docs/MUSIC.md) is compiled by tools/txamusic.py, TXA's own reference compiler, into one state per 1/60 second for each voice; a
PAL console's 50 frames a second take the state at each frame's time.  The notation has three tone voices (A, B, C), noise (N), envelopes and repeats.

Options:  --fps 60|50        the machine's frame rate (a PAL console runs at 50)
          --loop             play the song over and over from its start
          --loop-at SECONDS  ... or from that moment on (an introduction plays once)
          --volume N         add N (+/-) to every note's volume, 0-15
          --transpose N      shift every note by N semitones
          --wav FILE         write a preview of the song, made by a model of the sound chip
          --info             print what was made

The chip has three tone voices and one noise voice.  From MIDI the notes of all tracks are shared
among the three tone voices (the highest and the lowest note sounding always get one; an inner note
takes the third when it is free) and the drum channel (10) goes to the noise voice; notes lower than
110 Hz are moved up by octaves until the chip can play them.

Text score (MML).  One track to a voice, any lines, `;` starts a comment:
    V1: t120 o4 l8 c d e f g2 r4        voice 1 (also V2, V3); N: the noise voice
    V2: o3 l2 c g c g
    N:  l8 k4 r k5 r                    k0-k7 a noise burst: bit 2 white (else periodic), bits 1-0 rate
                                        (0 high, 1 medium, 2 low, 3 follows voice 3's pitch)
  tN   tempo in quarter notes a minute      oN   octave (o4 c is middle C)       < >  octave down, up
  lN   default note length (1 2 4 8 16 32)  vN   volume 0-15 (default 12)        qN   gate 1-8 (7: a note
  c d e f g a b   a note, then + # sharp or - flat, a length (c4 c8. c+16), dots lengthen by half
  r    a rest (the same lengths)                                                   sounds 7/8 of its length)

Format of the output (SKM, also in docs/MUSIC.md and kernel/music.a99): 8-byte header 'S' 'K' version flags
loop-target(word) length(word), then commands: 00 end/loop; 01-3F hold n frames; 40-7F tone data byte;
80-FF byte to the chip.
"""
import argparse, os, re, struct, sys

CLOCK = 3579545.0
FPS = 60


def midi_to_div(note):
    """MIDI note number -> the chip's divider (1-1023), moved by octaves into the chip's range."""
    while note < 45:      # 110 Hz is the lowest the 10-bit divider can make
        note += 12
    while note > 108:
        note -= 12
    f = 440.0 * 2 ** ((note - 69) / 12.0)
    return max(1, min(1023, int(round(CLOCK / (32.0 * f)))))


# ----- text score -----------------------------------------------------------------------------
def parse_mml(text, fps):
    """-> (tone_notes[3], noise_hits): notes (start, end, midi, volume) in frames; hits (start, end, mode, volume)."""
    tracks = {}
    for line in text.split('\n'):
        line = line.split(';')[0].strip()
        m = re.match(r'^(V[123]|N)\s*:(.*)$', line, re.I)
        if m:
            tracks.setdefault(m.group(1).upper(), []).append(m.group(2))
    tone = [[], [], []]
    noise = []
    for name, lines in tracks.items():
        src = ' '.join(lines).lower()
        t, octave, length, vol, gate, now = 120.0, 4, 4, 12, 7, 0.0
        i = 0
        while i < len(src):
            c = src[i]
            if c.isspace():
                i += 1; continue
            def number():
                nonlocal i
                m = re.match(r'\d+', src[i:])
                if not m: return None
                i += m.end(); return int(m.group())
            def dur():
                nonlocal i
                n = number() or length
                dots = 0
                while i < len(src) and src[i] == '.': dots += 1; i += 1
                return (4.0 * 60.0 / t) / n * (2 - 0.5 ** dots)
            i += 1
            if c == 't': t = float(number() or 120)
            elif c == 'o': octave = number()
            elif c == 'l': length = number() or 4
            elif c == 'v': vol = max(0, min(15, number() or 0))
            elif c == 'q': gate = max(1, min(8, number() or 8))
            elif c == '<': octave -= 1
            elif c == '>': octave += 1
            elif c == 'r': now += dur()
            elif c == 'k' and name == 'N':
                mode = number() or 0
                d = dur()
                s, e = round(now * fps), max(round(now * fps) + 1, round((now + d * gate / 8.0) * fps))
                noise.append((s, e, mode & 7, vol)); now += d
            elif c in 'abcdefg' and name != 'N':
                semi = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}[c]
                while i < len(src) and src[i] in '+#-':
                    semi += -1 if src[i] == '-' else 1; i += 1
                d = dur()
                s = round(now * fps)
                e = max(s + 1, round((now + d * gate / 8.0) * fps))
                tone[int(name[1]) - 1].append((s, e, 12 * (octave + 1) + semi, vol))
                now += d
            else:
                raise SystemExit('skmusic: cannot read %r in track %s' % (src[i - 1:i + 8], name))
    return tone, noise


# ----- MIDI -----------------------------------------------------------------------------------
def read_midi(data, fps):
    if data[:4] != b'MThd':
        raise SystemExit('skmusic: not a MIDI file')
    fmt, ntr, div = struct.unpack('>HHH', data[8:14])
    if div & 0x8000:
        raise SystemExit('skmusic: SMPTE timing is not supported')
    pos = 14
    tempos, notes = [(0, 500000)], []
    for _ in range(ntr):
        if data[pos:pos + 4] != b'MTrk': break
        n = struct.unpack('>I', data[pos + 4:pos + 8])[0]
        trk = data[pos + 8:pos + 8 + n]; pos += 8 + n
        i, tick, run = 0, 0, 0
        on = {}
        def vlq():
            nonlocal i
            v = 0
            while True:
                b = trk[i]; i += 1
                v = (v << 7) | (b & 0x7F)
                if not b & 0x80: return v
        while i < len(trk):
            tick += vlq()
            b = trk[i]
            if b == 0xFF:
                typ = trk[i + 1]; i += 2; ln = vlq()
                if typ == 0x51 and ln == 3:
                    tempos.append((tick, int.from_bytes(trk[i:i + 3], 'big')))
                i += ln; continue
            if b in (0xF0, 0xF7):
                i += 1; ln = vlq(); i += ln; continue
            if b & 0x80: run = b; i += 1
            st = run & 0xF0; ch = run & 0x0F
            if st in (0x80, 0x90):
                k, v = trk[i], trk[i + 1]; i += 2
                if st == 0x90 and v > 0:
                    on[(ch, k)] = (tick, v)
                else:
                    if (ch, k) in on:
                        t0, v0 = on.pop((ch, k)); notes.append((t0, tick, ch, k, v0))
            elif st in (0xA0, 0xB0, 0xE0):
                i += 2
            elif st in (0xC0, 0xD0):
                i += 1
    tempos.sort()
    def secs(tk):
        s, last, tp = 0.0, 0, 500000
        for t0, tpo in tempos:
            if t0 >= tk: break
            s += (t0 - last) * tp / 1e6 / div; last, tp = t0, tpo
        return s + (tk - last) * tp / 1e6 / div
    out = []
    for t0, t1, ch, k, v in notes:
        s = round(secs(t0) * fps); e = max(s + 1, round(secs(t1) * fps))
        out.append((s, e, ch, k, v))
    return sorted(out)


def allocate_midi(notes, transpose=0, volume=0):
    """MIDI notes -> three voices of (start, end, midi, volume) and noise hits (start, end, mode, volume)."""
    tone = [[], [], []]; noise = []; dropped = 0
    busy = [None, None, None]      # (end, pitch, vel, note tuple)
    melodic = []
    for (s, e, ch, k, v) in notes:
        vol = max(0, min(15, 2 + (v * 13) // 127 + volume))
        if ch == 9:
            if k in (35, 36): noise.append((s, s + 8, 6, vol))           # kick: low periodic-ish thud
            elif k in (38, 40, 37, 39): noise.append((s, s + 6, 5, vol))   # snare: white, medium
            elif k in (42, 44, 46, 49, 51, 59): noise.append((s, s + 3, 4, max(0, vol - 3)))   # hats: white, high
            continue
        melodic.append((s, e, k + transpose, vol))
    melodic.sort()
    for (s, e, k, vol) in melodic:
        for vi in range(3):                       # free voices first
            if busy[vi] is None or busy[vi][0] <= s:
                busy[vi] = (e, k, vol); tone[vi].append((s, e, k, vol)); break
        else:
            cand = [(busy[vi][1], vi) for vi in range(3)] + [(k, -1)]
            cand.sort()
            middle = [c for c in cand[1:3]]                        # drop one of the two middle notes
            drop = min(middle, key=lambda c: (busy[c[1]][2] if c[1] >= 0 else vol))
            if drop[1] == -1:
                dropped += 1
            else:
                vi = drop[1]
                ss, ee, kk, vv = tone[vi][-1]
                tone[vi][-1] = (ss, max(ss + 1, s), kk, vv)         # cut the stolen note short
                busy[vi] = (e, k, vol); tone[vi].append((s, e, k, vol)); dropped += 1
    return tone, noise, dropped


# ----- frames -> SKM --------------------------------------------------------------------------
def to_frames(tone, noise, transpose=0, volume=0):
    total = 0
    for v in tone:
        for n in v: total = max(total, n[1])
    for n in noise: total = max(total, n[1])
    states = [{'t': [(None, 15)] * 3, 'n': (None, 15)} for _ in range(total + 1)]
    for vi, notes in enumerate(tone):
        for (s, e, k, vol) in notes:
            vol = max(0, min(15, vol + volume))
            for f in range(s, min(e, total)):
                states[f]['t'][vi] = (midi_to_div(k + transpose), 15 - vol)
    for (s, e, mode, vol) in noise:
        vol = max(0, min(15, vol + volume))
        for f in range(s, min(e, total)):
            decay = (f - s) // 2
            states[f]['n'] = (mode, min(15, 15 - vol + decay))
    return states[:total]


def encode(states, loop_frame=None):
    prev_div = [None, None, None]; prev_att = [15, 15, 15]; prev_noise = None; prev_natt = 15
    out = bytearray(); cur = 0; loop_off = 0xFFFF; uses_noise = False
    first = True
    def wait(n):
        while n > 0:
            c = min(63, n); out.append(c); n -= c
    for f, st in enumerate(states):
        force = (loop_frame is not None and f == loop_frame)
        w = bytearray()
        for vi in range(3):
            div, att = st['t'][vi]
            if div is not None and (force or div != prev_div[vi]):
                hi_same = prev_div[vi] is not None and (prev_div[vi] >> 4) == (div >> 4)
                w.append(0x80 | (vi << 5) | (div & 15))
                if force or not hi_same: w.append(0x40 | (div >> 4))
                prev_div[vi] = div
            if force or att != prev_att[vi]:
                w.append(0x90 | (vi << 5) | att); prev_att[vi] = att
        mode, natt = st['n']
        if mode is not None and (force or mode != prev_noise):
            w.append(0xE0 | mode); prev_noise = mode; uses_noise = True
        if force or natt != prev_natt:
            w.append(0xF0 | natt); prev_natt = natt
        if w or force or f == 0:
            if f > cur or (f == 0 and False): wait(f - cur)
            cur = f
            if force: loop_off = 8 + len(out)
            out += w
    wait(len(states) - cur)
    out.append(0)
    hdr = b'SK' + bytes([1, 1 if uses_noise else 0]) + struct.pack('>HH', loop_off, (8 + len(out)) & 0xFFFF)
    return bytes(hdr + out)


def decode(skm, passes=1):
    """The player's job, in Python: -> [(frame, byte)], and the frames in one pass."""
    assert skm[:2] == b'SK'
    loop = struct.unpack('>H', skm[4:6])[0]
    ev, frame, pos, done = [], 0, 8, 0
    while True:
        c = skm[pos]; pos += 1
        if c == 0:
            done += 1
            if loop == 0xFFFF or done >= passes: break
            pos = loop
        elif c < 0x40: frame += c
        elif c < 0x80: ev.append((frame, c & 0x3F))
        else: ev.append((frame, c))
    return ev, frame


def read_txm(text, fps):
    """TXA music notation -> the frame states encode() takes: tools/txamusic.py compiles it, tick by tick (1/60 s), to (value, attenuation) for each of
    the voices A, B, C (the tone dividers) and N (the noise control byte); a silent tick is (0, 15)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import txamusic
    try:
        song = txamusic.compile_text(text)
    except txamusic.MusicError as e:
        raise SystemExit('skmusic: %s' % e)
    n = song.ticks
    frames = n if fps == 60 else int(n * fps / 60.0)
    silent = [(0, 15)] * n
    states = []
    for f in range(frames):
        t = min(n - 1, int(f * 60 / float(fps)))
        tone = []
        for v in 'ABC':
            value, att = song.voices.get(v, silent)[t]
            tone.append((None if (att == 15 and value == 0) else value, att))
        value, att = song.voices.get('N', silent)[t]
        states.append({'t': tone, 'n': (None if (att == 15 and value == 0) else value & 7, att)})
    return states, sum(song.note_counts.values()), song.warnings


def compile_file(path, fps=FPS, loop=False, loop_at=None, volume=0, transpose=0):
    data = open(path, 'rb').read()
    info = {}
    if path.lower().endswith('.txm'):
        states, info['notes'], info['warnings'] = read_txm(data.decode('latin-1'), fps)
        if volume or transpose:
            raise SystemExit('skmusic: --volume and --transpose are for MML and MIDI; a .txm file has its own V and notes')
    elif path.lower().endswith(('.mid', '.midi')):
        notes = read_midi(data, fps)
        tone, noise, dropped = allocate_midi(notes, transpose, volume)
        info['notes'] = len(notes); info['dropped'] = dropped
        states = to_frames(tone, noise)
    else:
        tone, noise = parse_mml(data.decode('latin-1'), fps)
        states = to_frames(tone, noise, transpose, volume)
        info['notes'] = sum(len(v) for v in tone)
    lf = None
    if loop_at is not None: lf = round(loop_at * fps)
    elif loop: lf = 0
    skm = encode(states, lf)
    if len(skm) > 65535:
        raise SystemExit('skmusic: the song is %d bytes: the player addresses 65,535 (shorten it, or lower the note count)' % len(skm))
    info.update(frames=len(states), seconds=len(states) / float(fps), bytes=len(skm))
    return skm, info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source'); ap.add_argument('-o', '--out')
    ap.add_argument('--fps', type=int, default=FPS); ap.add_argument('--loop', action='store_true')
    ap.add_argument('--loop-at', type=float); ap.add_argument('--volume', type=int, default=0)
    ap.add_argument('--transpose', type=int, default=0); ap.add_argument('--wav'); ap.add_argument('--info', action='store_true')
    a = ap.parse_args()
    skm, info = compile_file(a.source, a.fps, a.loop, a.loop_at, a.volume, a.transpose)
    out = a.out or os.path.splitext(a.source)[0] + '.skm'
    open(out, 'wb').write(skm)
    if a.info or not a.wav:
        print('%s: %d bytes, %d frames (%.1f s at %d Hz), %d notes%s' % (out, info['bytes'], info['frames'], info['seconds'], a.fps,
              info['notes'], (', %d dropped (more than three at once)' % info['dropped']) if info.get('dropped') else ''))
    if a.wav:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import sn76489
        ev, frames = decode(skm, 1)
        sn76489.wav(sn76489.synth([(f / float(a.fps), b) for f, b in ev], frames / float(a.fps) + 0.2), a.wav)
        print('wrote', a.wav)


if __name__ == '__main__':
    main()
