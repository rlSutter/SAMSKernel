"""reversi_model.py - the rules of Reversi and the computer's two levels, in Python, as the reference the
assembly program (examples/reversi) is checked against.  Cells are numbered row * 8 + column."""
DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
WEIGHT = [100, -20, 10, 5, 5, 10, -20, 100,
          -20, -50, -2, -2, -2, -2, -50, -20,
          10, -2, 1, 1, 1, 1, -2, 10,
          5, -2, 1, 0, 0, 1, -2, 5,
          5, -2, 1, 0, 0, 1, -2, 5,
          10, -2, 1, 1, 1, 1, -2, 10,
          -20, -50, -2, -2, -2, -2, -50, -20,
          100, -20, 10, 5, 5, 10, -20, 100]


def start():
    b = [0] * 64
    b[3 * 8 + 4] = 1; b[4 * 8 + 3] = 1     # e4, d5: the first player's
    b[3 * 8 + 3] = 2; b[4 * 8 + 4] = 2     # d4, e5
    return b


def flips(b, cell, p):
    """The cells a disc of player p put on `cell` would turn over (empty list: not a legal move)."""
    if b[cell]:
        return []
    r, c = divmod(cell, 8)
    out = []
    for dr, dc in DIRS:
        line, rr, cc = [], r + dr, c + dc
        while 0 <= rr < 8 and 0 <= cc < 8 and b[rr * 8 + cc] == 3 - p:
            line.append(rr * 8 + cc); rr += dr; cc += dc
        if line and 0 <= rr < 8 and 0 <= cc < 8 and b[rr * 8 + cc] == p:
            out += line
    return out


def legal(b, p):
    return [i for i in range(64) if flips(b, i, p)]


def play(b, cell, p):
    f = flips(b, cell, p)
    assert f
    b = list(b)
    b[cell] = p
    for i in f:
        b[i] = p
    return b


def greedy(b, p):
    """Level 2: the legal cell with the best weight + flips, the first in a tie (None: no move)."""
    best, bc = None, None
    for i in range(64):
        f = flips(b, i, p)
        if f and (best is None or WEIGHT[i] + len(f) > best):
            best, bc = WEIGHT[i] + len(f), i
    return bc


def score(b):
    return b.count(1), b.count(2)
