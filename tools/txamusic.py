#!/usr/bin/env python3
# Vendored, unchanged, from the TXA project (tools/midi2txa/txamusic.py): MIT, (c) 2026 Rebecca Sutter.
# It defines TXA music notation 1.0; tools/skmusic.py compiles .txm through it (docs/MUSIC.md).
"""txamusic.py - the reference compiler for TXA music notation.

This module defines the notation. Whatever it accepts is valid TXA music;
whatever per-tick state it produces is what the music means. The TI
workbench compiler must accept the same text and produce the same state,
tick for tick. docs/MUSIC.md describes the notation for authors; where the
two disagree, this file is right and the document is the bug.

The result of compiling is the internal form the spec names: up to three
tone voices (A, B, C) and one noise voice (N), each a list with one entry
per 1/60-second tick holding (value, attenuation):

    tone voices  value = the 10-bit TMS9919 tone divider (111860.8 / Hz)
    noise voice  value = the noise control byte (>E0 + 4 if white + rate)
    attenuation  0 (loudest) to 15 (silent); a silent tick is (0, 15)

How a platform encodes that state for its own player (the TI's SAMS data,
another machine's sound chip) is that platform's build step, not this file.

Command line:
    python3 txamusic.py SONG.txm [--wav out.wav] [--events out.csv]
"""

import argparse
import math
import re
import sys

VERSION = '1.0'

VOICES = ('A', 'B', 'C', 'N')
TONE_VOICES = ('A', 'B', 'C')
UNITS_PER_WHOLE = 192           # time inside the notation: 1/192 whole note
TICKS_PER_SECOND = 60
CHIP_DIVIDER = 111860.8         # TMS9919 tone value = CHIP_DIVIDER / Hz
LOW_NOTE, HIGH_NOTE = 45, 107   # A2 .. B7, as MIDI note numbers
TEMPO_MIN, TEMPO_MAX = 20, 999
DEFAULT_TEMPO = 120
MAX_REPEAT = 255
MAX_NESTING = 8
MAX_ENV_STEPS = 64
MAX_EXPANDED = 200000           # tokens per voice after repeats

NOTE_OFFSETS = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
VALID_LENGTHS = (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 192)
NOTE_NAMES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')


def _tone_value(midi_note):
    hz = 440.0 * 2.0 ** ((midi_note - 69) / 12.0)
    return int(math.floor(CHIP_DIVIDER / hz + 0.5))


# The tone table, A2 (1017) to B7 (28). A native compiler carries it as a
# 63-entry constant table; it must hold exactly these values.
TONE_TABLE = {n: _tone_value(n) for n in range(LOW_NOTE, HIGH_NOTE + 1)}


def note_name(midi_note):
    return '%s%d' % (NOTE_NAMES[midi_note % 12], midi_note // 12 - 1)


def noise_value(white, rate):
    return 0xE0 | (4 if white else 0) | rate


def length_units(n, dots):
    """Units in a note of length n (4 = quarter) with the given dots."""
    if n not in VALID_LENGTHS:
        raise ValueError('length %d is not one of %s'
                         % (n, ', '.join(map(str, VALID_LENGTHS))))
    add = UNITS_PER_WHOLE // n
    total = add
    for _ in range(dots):
        if add % 2:
            raise ValueError('length %d cannot take %d dot%s'
                             % (n, dots, 's' if dots > 1 else ''))
        add //= 2
        total += add
    return total


def ticks_for(units, tempo):
    """Rounded ticks in `units` at `tempo` BPM: round(75 * units / tempo).

    Integer-only so the TI can compute it with MPY and DIV: the quotient
    must fit 16 bits, which limits one tempo segment to about 18 minutes.
    """
    return (150 * units + tempo) // (2 * tempo)


class MusicError(Exception):
    def __init__(self, message, line=None, col=None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col

    def __str__(self):
        if self.line is None:
            return self.message
        if self.col is None:
            return 'line %d: %s' % (self.line, self.message)
        return 'line %d, column %d: %s' % (self.line, self.col, self.message)


class Song:
    """A compiled piece: per-tick chip state for each voice present."""

    def __init__(self, ticks, voices, envelopes, warnings, note_counts):
        self.ticks = ticks
        self.voices = voices            # {'A': [(value, att), ...], ...}
        self.envelopes = envelopes      # {n: [att offsets]}
        self.warnings = warnings
        self.note_counts = note_counts

    @property
    def seconds(self):
        return self.ticks / TICKS_PER_SECOND


# ---------------------------------------------------------------- parsing

_TOKEN = re.compile(
    r'([A-GRWP])([#+\-]?)(\d*)(\.*)'    # note, rest, noise hit
    r'|([LOTV])(\d+)(\.*)'              # L, O, T, V commands
    r'|@(\d+)'                          # envelope select
    r'|\](\d+)'                         # repeat close
    r'|([<>&|\[])'                      # single characters
    r'|(\S)')                           # anything else is an error


def _strip_comment(text):
    i = text.find('!')
    return text if i < 0 else text[:i]


def parse_text(text):
    """Split source into envelope definitions and per-voice token lists."""
    envelopes = {}
    tokens = {v: [] for v in VOICES}
    present = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        if len(raw.rstrip('\r\n')) > 80:
            raise MusicError('line is longer than 80 characters (DV80)', lineno)
        line = _strip_comment(raw).strip().upper()
        if not line:
            continue
        if line.startswith('ENV') and (len(line) == 3 or line[3].isspace()):
            parts = line.split()[1:]
            if len(parts) < 2:
                raise MusicError('ENV needs a number and at least one step',
                                 lineno)
            try:
                n = int(parts[0])
                steps = []
                for p in parts[1:]:
                    if '*' in p:                    # value*count
                        v, c = p.split('*', 1)
                        if not 1 <= int(c) <= MAX_ENV_STEPS:
                            raise ValueError
                        steps += [int(v)] * int(c)
                    else:
                        steps.append(int(p))
            except ValueError:
                raise MusicError('ENV takes numbers, or value*count for a '
                                 'run', lineno)
            if not 1 <= n <= 15:
                raise MusicError('envelope number must be 1 to 15 '
                                 '(@0 is always flat)', lineno)
            if n in envelopes:
                raise MusicError('envelope %d is defined twice' % n, lineno)
            if len(steps) > MAX_ENV_STEPS:
                raise MusicError('an envelope has at most %d steps'
                                 % MAX_ENV_STEPS, lineno)
            if any(not 0 <= s <= 15 for s in steps):
                raise MusicError('envelope steps must be 0 to 15', lineno)
            envelopes[n] = steps
            continue
        m = re.match(r'([ABCN])\s*:(.*)$', line)
        if not m:
            raise MusicError('expected A:, B:, C:, N: or ENV', lineno, 1)
        voice, body = m.group(1), m.group(2)
        if voice not in present:
            present.append(voice)
        offset = len(line) - len(body)
        for tm in _TOKEN.finditer(body):
            col = tm.start() + offset + 1
            g = tm.groups()
            if g[10] is not None:
                raise MusicError('unexpected character "%s"' % g[10],
                                 lineno, col)
            if g[0] is not None:
                tokens[voice].append(('note', (g[0], g[1], g[2], len(g[3])),
                                      lineno, col))
            elif g[4] is not None:
                tokens[voice].append(('cmd', (g[4], int(g[5]), len(g[6])),
                                      lineno, col))
            elif g[7] is not None:
                tokens[voice].append(('cmd', ('@', int(g[7]), 0), lineno, col))
            elif g[8] is not None:
                tokens[voice].append((']', int(g[8]), lineno, col))
            else:
                tokens[voice].append((g[9], None, lineno, col))
    return envelopes, {v: tokens[v] for v in present}


def _expand(tokens):
    """Expand [ ... ]n repeats into a flat token list."""
    stack = [[]]
    opens = []
    for tok in tokens:
        if tok[0] == '[':
            if len(stack) > MAX_NESTING:
                raise MusicError('repeats nest at most %d deep' % MAX_NESTING,
                                 tok[2], tok[3])
            stack.append([])
            opens.append(tok)
        elif tok[0] == ']':
            if len(stack) == 1:
                raise MusicError('"]" without a matching "["', tok[2], tok[3])
            count = tok[1]
            if not 1 <= count <= MAX_REPEAT:
                raise MusicError('repeat count must be 1 to %d' % MAX_REPEAT,
                                 tok[2], tok[3])
            body = stack.pop()
            opens.pop()
            stack[-1].extend(body * count)
            if len(stack[-1]) > MAX_EXPANDED:
                raise MusicError('repeats expand past %d tokens' % MAX_EXPANDED,
                                 tok[2], tok[3])
        else:
            stack[-1].append(tok)
    if opens:
        tok = opens[-1]
        raise MusicError('"[" is never closed', tok[2], tok[3])
    return stack[0]


class _Note:
    __slots__ = ('value', 'env', 'start', 'pieces', 'line')

    def __init__(self, value, env, start, line):
        self.value = value
        self.env = env
        self.start = start
        self.pieces = []
        self.line = line


def _run_voice(voice, tokens, envelopes, warnings):
    """Interpret one voice. Returns (notes, end_tick)."""
    noise = voice == 'N'
    octave = 1 if noise else 4
    default_len = (4, 0)
    volume = 15
    env = 0
    tempo = DEFAULT_TEMPO
    units = 0                   # position in 1/192 whole notes
    seg_units = 0               # where the current tempo began
    seg_tick = 0
    notes = []
    tie = None                  # the '&' token waiting for its note
    last_was_note = False

    def tick_at(u):
        return seg_tick + ticks_for(u - seg_units, tempo)

    for kind, val, line, col in tokens:
        if kind == 'note':
            letter, acc, num, dots = val
            try:
                if num:
                    d = length_units(int(num), dots)
                else:
                    d = length_units(default_len[0], default_len[1] + dots)
            except ValueError as exc:
                raise MusicError(str(exc), line, col)
            if letter == 'R':
                if tie is not None:
                    raise MusicError('"&" must be followed by a note, not a '
                                     'rest', tie[2], tie[3])
                if acc:
                    raise MusicError('a rest takes no sharp or flat', line, col)
                units += d
                last_was_note = False
                continue
            if noise:
                if letter not in 'WP':
                    raise MusicError('the noise voice plays W (white) and P '
                                     '(periodic), not %s' % letter, line, col)
                if acc:
                    raise MusicError('noise takes no sharp or flat', line, col)
                if not 0 <= octave <= 3:
                    raise MusicError('noise rate (O) must be 0 to 3, is %d'
                                     % octave, line, col)
                value = noise_value(letter == 'W', octave)
            else:
                if letter in 'WP':
                    raise MusicError('%s is a noise hit; tone voices play C '
                                     'to B' % letter, line, col)
                pitch = (octave + 1) * 12 + NOTE_OFFSETS[letter]
                pitch += {'#': 1, '+': 1, '-': -1, '': 0}[acc]
                if not LOW_NOTE <= pitch <= HIGH_NOTE:
                    raise MusicError('%s is outside the chip\'s range (A2 to B7)'
                                     % note_name(pitch) if 0 <= pitch < 132
                                     else 'note outside the chip\'s range',
                                     line, col)
                value = TONE_TABLE[pitch]
            start, end = tick_at(units), tick_at(units + d)
            if tie is not None:
                prev = notes[-1]
                if prev.value != value:
                    raise MusicError('"&" joins notes of the same pitch only',
                                     line, col)
                prev.pieces.append((start, end, volume))
            else:
                note = _Note(value, env, start, line)
                note.pieces.append((start, end, volume))
                notes.append(note)
            if end == start and tie is None:
                warnings.append('line %d: a %s note is shorter than one tick '
                                'and is not heard' % (line, voice))
            tie = None
            units += d
            last_was_note = True
        elif kind == '&':
            if not last_was_note:
                raise MusicError('"&" must follow a note', line, col)
            tie = (kind, val, line, col)
        elif kind == '|':
            pass                                    # bar line, for reading
        elif kind == '>':
            octave += 1
        elif kind == '<':
            octave -= 1
        elif kind == 'cmd':
            cmd, n, dots = val
            if cmd != 'L' and dots:
                raise MusicError('only L takes dots', line, col)
            if cmd == 'L':
                try:
                    length_units(n, dots)
                except ValueError as exc:
                    raise MusicError(str(exc), line, col)
                default_len = (n, dots)
            elif cmd == 'O':
                if n > 9:
                    raise MusicError('octave must be 0 to 9', line, col)
                octave = n
            elif cmd == 'V':
                if n > 15:
                    raise MusicError('volume must be 0 to 15', line, col)
                volume = n
            elif cmd == '@':
                if n and n not in envelopes:
                    raise MusicError('envelope %d is not defined (ENV %d ...)'
                                     % (n, n), line, col)
                env = n
            elif cmd == 'T':
                if not TEMPO_MIN <= n <= TEMPO_MAX:
                    raise MusicError('tempo must be %d to %d'
                                     % (TEMPO_MIN, TEMPO_MAX), line, col)
                seg_tick = tick_at(units)
                seg_units = units
                tempo = n
        else:
            raise MusicError('unexpected "%s"' % kind, line, col)
    if tie is not None:
        raise MusicError('"&" at the end of the voice', tie[2], tie[3])
    end = tick_at(units)
    if end - seg_tick > 65535:
        raise MusicError('one tempo stretch is longer than 65535 ticks '
                         '(about 18 minutes); add a T command')
    return notes, end


def compile_text(text):
    """Compile notation text into a Song. Raises MusicError."""
    envelopes, voice_tokens = parse_text(text)
    if not voice_tokens:
        raise MusicError('no voices (A:, B:, C: or N: lines)')
    warnings = []
    results = {}
    for voice, toks in voice_tokens.items():
        results[voice] = _run_voice(voice, _expand(toks), envelopes, warnings)
    total = max(end for _, end in results.values())
    voices = {}
    counts = {}
    for voice in VOICES:
        if voice not in results:
            continue
        notes, _ = results[voice]
        state = [(0, 15)] * total
        for note in notes:
            steps = envelopes.get(note.env, [0])
            last = len(steps) - 1
            for s, e, vol in note.pieces:
                base = 15 - vol
                for t in range(s, e):
                    k = t - note.start
                    att = base + steps[k if k < last else last]
                    state[t] = (note.value, att) if att < 15 else (0, 15)
        voices[voice] = state
        counts[voice] = len(notes)
    return Song(total, voices, dict(envelopes), warnings, counts)


def compile_file(path):
    with open(path, 'r', encoding='ascii', errors='strict') as f:
        return compile_text(f.read())


# ------------------------------------------------------------ CSV export

def write_events(song, path):
    """Write the internal form as CSV, one row per tick where state changes."""
    voices = [v for v in VOICES if v in song.voices]
    with open(path, 'w') as f:
        cols = []
        for v in voices:
            cols += ['%s_value' % v, '%s_att' % v]
        f.write('tick,' + ','.join(cols) + '\n')
        prev = None
        for t in range(song.ticks):
            row = tuple(song.voices[v][t] for v in voices)
            if row != prev:
                f.write('%d,%s\n' % (t, ','.join(
                    '%d,%d' % cell for cell in row)))
                prev = row
        f.write('%d,%s\n' % (song.ticks, ','.join('0,15' for _ in voices)))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Compile TXA music notation and check it.')
    ap.add_argument('source', help='notation file (DV80 text)')
    ap.add_argument('--wav', help='render a preview WAV file')
    ap.add_argument('--loops', type=int, default=1,
                    help='play the piece this many times in the WAV')
    ap.add_argument('--events', help='write the per-tick internal form as CSV')
    args = ap.parse_args(argv)
    try:
        song = compile_file(args.source)
    except MusicError as exc:
        print('%s: %s' % (args.source, exc), file=sys.stderr)
        return 1
    except UnicodeDecodeError:
        print('%s: the file must be plain ASCII' % args.source, file=sys.stderr)
        return 1
    for w in song.warnings:
        print('warning: ' + w, file=sys.stderr)
    print('%s: %.1f seconds (%d ticks); notes per voice: %s'
          % (args.source, song.seconds, song.ticks,
             ', '.join('%s %d' % kv for kv in song.note_counts.items())))
    if args.events:
        write_events(song, args.events)
    if args.wav:
        import snpreview
        snpreview.render(song, args.wav, loops=args.loops)
    return 0


if __name__ == '__main__':
    sys.exit(main())
