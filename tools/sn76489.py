#!/usr/bin/env python3
"""sn76489.py - the TI's sound chip (TMS9919 / SN76489), for previews and tests.

    chip = Sn76489()
    chip.write(0x8E); chip.write(0x0F); chip.write(0x90)     # voice 1 a divider of 254, loudest
    samples = chip.render(22050)                              # one second, float32, -1..1
    wav(samples, 'out.wav')

Registers (writes are bytes): a byte with bit 7 set latches a register and carries 4 data bits:
    1 cc 0 dddd   tone divider low 4 bits, voice cc = 0-2; cc = 3: noise (dddd = 0 fb nn)
    1 cc 1 aaaa   attenuation of voice cc, 0 loudest ... 15 off, 2 dB a step
a byte with bit 7 clear sets the high 6 bits of the latched tone divider.
A tone's frequency is 3,579,545 / (32 * divider) Hz.  Noise: a 15-bit shift register clocked
at 3,579,545 / (16 * 32 / 2^k) with k = nn (0-2) or by voice 2's tone (nn = 3); fb = 1 white,
0 periodic.  An approximation of the chip, good for hearing and measuring a tune, not for
cycle-exact work.
"""
import numpy as np

CLOCK = 3579545.0


class Sn76489:
    def __init__(self, rate=22050):
        self.rate = rate
        self.div = [1024, 1024, 1024]
        self.att = [15, 15, 15, 15]
        self.noise = 0
        self.latch = 0
        self.phase = [0.0, 0.0, 0.0]
        self.lfsr = 0x4000
        self.nphase = 0.0
        self.nout = 1

    def write(self, b):
        if b & 0x80:
            self.latch = (b >> 4) & 7
            reg, d = self.latch, b & 0xF
            ch = reg >> 1
            if reg & 1:
                self.att[ch] = d
            elif ch < 3:
                self.div[ch] = (self.div[ch] & 0x3F0) | d
            else:
                self.noise = d & 7
                self.lfsr = 0x4000
        else:
            reg = self.latch
            if reg & 1 == 0 and (reg >> 1) < 3:
                ch = reg >> 1
                self.div[ch] = ((b & 0x3F) << 4) | (self.div[ch] & 0xF)

    def _amp(self, a):
        return 0.0 if a >= 15 else 10 ** (-2.0 * a / 20.0)

    def render(self, n):
        out = np.zeros(n, np.float32)
        t = np.arange(n)
        for ch in range(3):
            amp = self._amp(self.att[ch])
            if amp == 0.0:
                self.phase[ch] = (self.phase[ch] + n * 0) % 1
                continue
            f = CLOCK / (32.0 * max(1, self.div[ch]))
            ph = self.phase[ch] + t * (f / self.rate)
            out += (np.where((ph % 1.0) < 0.5, 1.0, -1.0) * amp).astype(np.float32)
            self.phase[ch] = (self.phase[ch] + n * f / self.rate) % 1.0
        amp = self._amp(self.att[3])
        if amp > 0.0:
            nf = self.noise & 3
            f = CLOCK / (16.0 * 32.0 / (2 ** nf if nf < 3 else 1)) if nf < 3 else CLOCK / (32.0 * max(1, self.div[2]))
            white = bool(self.noise & 4)
            step = f / self.rate
            for i in range(n):
                self.nphase += step
                while self.nphase >= 1.0:
                    self.nphase -= 1.0
                    fb = ((self.lfsr ^ (self.lfsr >> 1)) & 1) if white else (self.lfsr & 1)
                    self.nout = self.lfsr & 1
                    self.lfsr = (self.lfsr >> 1) | (fb << 14)
                out[i] += (1.0 if self.nout else -1.0) * amp
        return out / 3.0


def synth(events, seconds=None, rate=22050):
    """events: [(time in seconds, byte)] -> float32 samples."""
    ev = sorted(events, key=lambda e: e[0])
    chip = Sn76489(rate)
    end = seconds if seconds is not None else (ev[-1][0] + 0.25 if ev else 0.0)
    parts, pos = [], 0
    for t, b in ev:
        n = int(round(t * rate)) - pos
        if n > 0:
            parts.append(chip.render(n)); pos += n
        chip.write(b)
    n = int(round(end * rate)) - pos
    if n > 0:
        parts.append(chip.render(n))
    return np.concatenate(parts) if parts else np.zeros(0, np.float32)


def wav(samples, path, rate=22050):
    import wave
    pcm = (np.clip(samples, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def peak_hz(samples, rate=22050):
    """The strongest frequency in the samples."""
    if len(samples) == 0:
        return 0.0
    w = samples * np.hanning(len(samples))
    spec = np.abs(np.fft.rfft(w))
    return float(np.argmax(spec[1:]) + 1) * rate / len(samples)
