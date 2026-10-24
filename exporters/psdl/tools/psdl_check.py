# Checks the room perimeters of PSDL files (stock or exported)
#
#   python -I psdl_check.py [--verbose] file.psdl [file2.psdl ...]
#
# The game takes the edges of a room as the doors to its neighbours: crossing an edge whose neighbour is 0 takes a car
# out of the city (mm2.log: "PHYS.DeclareMover : mover not even in city", every frame for the player car). So inside
# the city no edge must lead to room 0:
# - spikes out of the city: the perimeter goes to a vertex and comes back along the same line (zero width), and an
#   edge of the spike leads to room 0. The stock files have some spikes too, towards their neighbours, except for 3
#   in london.psdl (rooms 173 and 1013).
# - slits out of the city: an edge that leads to room 0 with its own room on both sides.
# - vertices and neighbours out of range.
# Exits with 1 if something is wrong.
# --verbose: lists each problem.

import struct
import sys

import numpy as np

SPIKE_MIN_LENGTH = 0.03  # m, the epsilon of the PSDL writer
SPIKE_WIDTH = 0.1  # m, the spike_width of the PSDL writer
SIDE_OFFSET = 0.05  # m, how far from an edge its two sides are tested


class Reader:
    def __init__(self, path):
        with open(path, 'rb') as f:
            self.b = f.read()
        self.o = 0

    def unpack(self, fmt):
        v = struct.unpack_from('<' + fmt, self.b, self.o)
        self.o += struct.calcsize('<' + fmt)
        return v

    def u32(self):
        return self.unpack('I')[0]

    def skip(self, n):
        if n < 0 or self.o + n > len(self.b):
            raise Exception('unexpected end of file at offset ' + str(self.o))
        self.o += n


def read_psdl(path):
    # only the parts up to the perimeters: vertices (y up) and, for each room, its perimeter as (vertex, neighbour)
    # pairs; the neighbour of a pair is the room across the edge to the next pair (0 = none, rooms count from 1)
    r = Reader(path)
    if r.b[:4] != b'PSD0':
        raise Exception(path + ' is not a PSDL file')
    r.o = 8
    n_vertices = r.u32()
    vertices = np.frombuffer(r.b, dtype='<f4', count=3 * n_vertices, offset=r.o).astype(float).reshape(-1, 3)
    r.skip(12 * n_vertices)
    r.skip(4 * r.u32())  # heights
    for _ in range(r.u32() - 1):  # textures (the count is one more than the names)
        r.skip(r.unpack('B')[0])
    n_rooms = r.u32() - 1
    r.u32()
    rooms = []
    for _ in range(n_rooms):
        n_points, n_attributes = r.unpack('2I')
        pairs = np.frombuffer(r.b, dtype='<u2', count=2 * n_points, offset=r.o).tolist()
        r.skip(4 * n_points)
        rooms.append(list(zip(pairs[0::2], pairs[1::2])))
        r.skip(2 * n_attributes)
    return vertices, rooms


def edges(perimeter):
    # the edges between consecutive different vertices (a vertex is repeated once for each of its neighbours)
    res = []
    n = len(perimeter)
    for k in range(n):
        v0, neighbour = perimeter[k]
        v1 = perimeter[(k + 1) % n][0]
        if v0 != v1:
            res.append((v0, v1, neighbour))
    return res


def distinct_vertices(perimeter):
    res = []
    for v, _ in perimeter:
        if not res or res[-1] != v:
            res.append(v)
    while len(res) > 1 and res[0] == res[-1]:
        res.pop()
    return res


def is_spike(a, x, b):
    # x is the tip of a spike when b is within SPIKE_WIDTH of the line from x to a, or a of the one from x to b, on the
    # same side of x (2D), with both farther than SPIKE_MIN_LENGTH from x (the stock files have different vertices at
    # almost the same place); the same test as the PSDL writer
    u = a - x
    w = b - x
    lu = np.linalg.norm(u)
    lw = np.linalg.norm(w)
    if lu < SPIKE_MIN_LENGTH or lw < SPIKE_MIN_LENGTH or float(np.dot(u, w)) <= 0:
        return False
    far, near, l_far = (u, w, lu) if lu >= lw else (w, u, lw)
    return abs(float(far[0] * near[1] - far[1] * near[0])) / l_far < SPIKE_WIDTH


def inside(poly, p):
    x, z = p
    res = False
    n = len(poly)
    for k in range(n):
        x0, z0 = poly[k]
        x1, z1 = poly[(k + 1) % n]
        if (z0 > z) != (z1 > z) and x < x0 + (z - z0) * (x1 - x0) / (z1 - z0):
            res = not res
    return res


def lint(vertices, rooms, verbose):
    problems = []

    def problem(text):
        problems.append(text)
        if verbose:
            print('  ' + text)

    def pos(v):
        return '(%.2f, %.2f, %.2f)' % tuple(vertices[v])

    flat = vertices[:, [0, 2]]
    for i, room in enumerate(rooms):
        name = 'room ' + str(i + 1)
        bad = [v for v, _ in room if v >= len(vertices)]
        for v in bad:
            problem(name + ': vertex ' + str(v) + ' out of range')
        for _, neighbour in room:
            if neighbour > len(rooms):
                problem(name + ': neighbour ' + str(neighbour) + ' out of range')
        if bad:
            continue
        out = [(v0, v1) for v0, v1, neighbour in edges(room) if neighbour == 0]
        reported = set()
        ids = distinct_vertices(room)
        n = len(ids)
        for k in range(n if n >= 3 else 0):
            a, x, b = ids[k - 1], ids[k], ids[(k + 1) % n]
            if is_spike(flat[a], flat[x], flat[b]) and ((a, x) in out or (x, b) in out):
                problem(name + ': spike out of the city to vertex ' + str(x) + ' ' + pos(x))
                reported.update(((a, x), (x, b)))
        poly = flat[ids]
        for v0, v1 in out:
            d = flat[v1] - flat[v0]
            if (v0, v1) in reported or np.linalg.norm(d) < 1e-6:
                continue
            normal = np.array([-d[1], d[0]]) / np.linalg.norm(d)
            mid = (flat[v0] + flat[v1]) / 2
            if inside(poly, mid + SIDE_OFFSET * normal) and inside(poly, mid - SIDE_OFFSET * normal):
                problem(name + ': slit out of the city from ' + pos(v0) + ' to ' + pos(v1))
    return problems


def main(args):
    verbose = '--verbose' in args
    files = [a for a in args if not a.startswith('--')]
    if not files:
        print('usage: psdl_check.py [--verbose] file.psdl ...')
        return 2
    failed = False
    for path in files:
        vertices, rooms = read_psdl(path)
        print('== %s: %d rooms, %d vertices' % (path, len(rooms), len(vertices)))
        problems = lint(vertices, rooms, verbose)
        kinds = {}
        for p in problems:
            key = p.split(': ', 1)[1] if ': ' in p else p
            key = key.split(' (', 1)[0].rstrip('0123456789 ')
            kinds[key] = kinds.get(key, 0) + 1
        print('  lint: %d problems' % len(problems))
        for key, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
            print('    %5d x %s' % (count, key))
        failed = failed or len(problems) > 0
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
