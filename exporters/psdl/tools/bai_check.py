# Checks BAI files against the rules of the stock MM2 cities, using the same functions as the BAI writer
#
#   python -I bai_check.py [--derive] [--lint] [--verbose] file.bai [file2.bai ...]
#
# --derive: computes again the values that follow from the splines of each road (distances, coordinate systems,
#           lane offsets and boundaries...) and reports how far they are from the ones in the file. On the stock
#           sf.bai and london.bai they match (a few stock roads have garbage in the offsets). On the exported files
#           the sidewalk centre differs around the sharp corners, where the BAI writer moves its points along the
#           sidewalk for the pedestrians.
# --lint:   checks the conventions of the stock files (the right side lanes and rails from the end to the start,
#           the sidewalks from the start to the end, at least 4 sections, unit vectors, 1 m traffic light axes,
#           flat flag, road ends and intersections consistent), exits with 1 if something is wrong.
# Without options both are done.

import math
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from common.bai_writer import (CDCD_FLOAT, FLAG_FLAT, MIN_SECTIONS, cumulative_lengths, lane_boundaries,  # noqa: E402
                               lateral_offsets, section_frames)

FILE_UP = np.array([0.0, 1.0, 0.0])  # the file is y-up
CDCDCDCD = 0xcdcdcdcd


class Reader:
    def __init__(self, path):
        with open(path, 'rb') as f:
            self.b = f.read()
        self.o = 0

    def unpack(self, fmt):
        v = struct.unpack_from('<' + fmt, self.b, self.o)
        self.o += struct.calcsize('<' + fmt)
        return v

    def u16(self):
        return self.unpack('H')[0]

    def u32(self):
        return self.unpack('I')[0]

    def f(self):
        return self.unpack('f')[0]

    def floats(self, n):
        return list(self.unpack(str(n) + 'f')) if n > 0 else []

    def vecs(self, n):
        return [np.array(self.unpack('3f'), dtype=float) for _ in range(n)]


def read_side(r, n):
    s = {}
    s['lanes'], s['trams'], s['trains'], s['sidewalks'], s['ambient'] = (r.u16() for _ in range(5))
    nl = s['lanes']
    s['lane_dist'] = [r.floats(n) for _ in range(nl)]
    s['dist'] = r.floats(n)
    s['offsets'] = r.floats(nl + 1)
    s['misc'] = r.floats(10)
    s['lane_v'] = [r.vecs(n) for _ in range(nl)]
    s['sw_c'] = r.vecs(n)
    s['tram_v'] = [r.vecs(n) for _ in range(s['trams'])]
    s['train_v'] = [r.vecs(n) for _ in range(s['trains'])]
    s['sw_i'] = r.vecs(n)
    s['sw_o'] = r.vecs(n)
    return s


def read_end(r):
    return {'intersection': r.u32(), 'unknown0': r.u16(), 'rule': r.u32(), 'index': r.u32(),
            'origin': np.array(r.unpack('3f')), 'axis': np.array(r.unpack('3f'))}


def read_bai(path):
    r = Reader(path)
    if r.b[:4] != b'CAI1':
        raise Exception(path + ' is not a BAI file')
    r.o = 4
    n_int = r.u16()
    n_roads = r.u16()
    roads = []
    for _ in range(n_roads):
        rd = {'id': r.u16()}
        n = rd['n'] = r.u16()
        rd['flags'] = r.u16()
        rd['rooms'] = [r.u16() for _ in range(r.u16())]
        rd['half_width'] = r.f()
        rd['speed'] = r.f()
        rd['right'] = read_side(r, n)
        rd['left'] = read_side(r, n)
        rd['cdist'] = r.floats(n)
        for k in ('centre', 'x', 'y', 'z', 'tangents'):
            rd[k] = r.vecs(n)
        rd['end'] = read_end(r)
        rd['start'] = read_end(r)
        roads.append(rd)
    intersections = []
    for _ in range(n_int):
        it = {'id': r.u16(), 'room': r.u16(), 'centre': np.array(r.unpack('3f'))}
        it['roads'] = [r.u32() for _ in range(r.u16())]
        intersections.append(it)
    return roads, intersections


def max_diff(a, b):
    if len(a) == 0:
        return 0.0
    return max(float(np.max(np.abs(np.subtract(x, y)))) for x, y in zip(a, b))


class Stats:
    def __init__(self):
        self.values = {}
        self.worst = {}

    def add(self, name, value, where):
        self.values.setdefault(name, []).append(value)
        if value > self.worst.get(name, (-1, None))[0]:
            self.worst[name] = (value, where)

    def report(self, tolerance):
        bad = []
        for name, values in self.values.items():
            v = np.array(values)
            over = int(np.sum(v > tolerance))
            print('  %-28s n=%5d median=%.4f p95=%.4f max=%.4f over %.2f: %d (worst: %s)' % (
                name, len(v), np.median(v), np.percentile(v, 95), v.max(), tolerance, over, self.worst[name][1]))
            if over > 0:
                bad.append(name)
        return bad


def derive(roads, stats):
    for rd in roads:
        name = 'road ' + str(rd['id'])
        n = rd['n']
        centre = rd['centre']
        xs, ys, zs, tangents = section_frames(centre, FILE_UP)
        stats.add('centre distances', max_diff(rd['cdist'], cumulative_lengths(centre)), name)
        stats.add('x axes', max_diff(rd['x'], xs), name)
        stats.add('y axes', max_diff(rd['y'], ys), name)
        stats.add('z axes', max_diff(rd['z'], zs), name)
        stats.add('tangents', max_diff(rd['tangents'], tangents), name)
        half_width = float(np.linalg.norm(rd['right']['sw_o'][0] - rd['left']['sw_o'][0])) / 2
        stats.add('half width', abs(half_width - rd['half_width']), name)
        for side_name in ('right', 'left'):
            s = rd[side_name]
            where = name + ' ' + side_name
            for lane, dists in zip(s['lane_v'], s['lane_dist']):
                stats.add('lane distances', max_diff(dists, cumulative_lengths(lane)), where)
            stats.add('sidewalk distances', max_diff(s['dist'], cumulative_lengths(s['sw_c'])), where)
            mid = [(a + b) / 2 for a, b in zip(s['sw_i'], s['sw_o'])]
            stats.add('sidewalk centre', max_diff(s['sw_c'], mid), where)
            first = [lane[-1] if side_name == 'right' else lane[0] for lane in s['lane_v']] + [s['sw_c'][0]]
            offsets = lateral_offsets(first, centre[0], rd['x'][0])
            stats.add('lane offsets', max_diff(s['offsets'], offsets), where)
            expected = lane_boundaries(s['offsets'], rd['half_width'])
            got = list(s['misc'])
            if s['lanes'] == 0:
                got[0] = expected[0]  # garbage in the stock files
            stats.add('lane boundaries', max(abs(a - b) if b != CDCD_FLOAT else (0.0 if a == CDCD_FLOAT else 1.0)
                                             for a, b in zip(got, expected)), where)
            for rail in s['tram_v'] + s['train_v']:
                k = n - 1 if side_name == 'right' else 0
                off = abs(float(np.dot(rail[k] - centre[0], rd['x'][0])))
                stats.add('rail offset spread', abs(off - abs(float(np.dot(rail[n - 1 - k] - centre[-1], rd['x'][-1])))), where)


def lint(roads, intersections, verbose):
    problems = []

    def problem(text):
        problems.append(text)
        if verbose:
            print('  ' + text)

    for i, rd in enumerate(roads):
        name = 'road ' + str(rd['id'])
        n = rd['n']
        centre = rd['centre']
        if rd['id'] != i:
            problem(name + ': id is not its index ' + str(i))
        if n < MIN_SECTIONS:
            problem(name + ': ' + str(n) + ' sections (the stock roads have at least ' + str(MIN_SECTIONS) + ')')
        for k in ('x', 'y', 'z', 'tangents'):
            if any(abs(np.linalg.norm(v) - 1) > 1e-3 for v in rd[k]):
                problem(name + ': ' + k + ' not unit vectors')
        if any(abs(float(np.dot(a, b))) > 1e-3 for a, b in zip(rd['x'], rd['z'])):
            problem(name + ': x and z axes not orthogonal')
        # (the stock files set it on some sloped roads too)
        if all(abs(float(z[1])) < 1e-3 for z in rd['z']) and not rd['flags'] & FLAG_FLAT:
            problem(name + ': flat flag missing on a level road')
        if rd['half_width'] <= 0:
            problem(name + ': half width ' + str(rd['half_width']))
        for side_name, sign in (('right', 1), ('left', -1)):
            s = rd[side_name]
            for k in ('sw_c', 'sw_i', 'sw_o'):
                if np.linalg.norm(s[k][0] - centre[0]) > np.linalg.norm(s[k][0] - centre[-1]) + 1e-3:
                    problem(name + ' ' + side_name + ': ' + k + ' goes from the end to the start')
            if np.linalg.norm(s['sw_o'][0] - centre[0]) > 1e-3 and sign * float(np.dot(s['sw_o'][0] - centre[0], rd['x'][0])) <= 0:
                problem(name + ' ' + side_name + ': sidewalk on the wrong side of the x axis')
            for lane in s['lane_v'] + s['tram_v'] + s['train_v']:
                reversed_order = np.linalg.norm(lane[0] - centre[-1]) < np.linalg.norm(lane[0] - centre[0])
                if n > 1 and np.linalg.norm(centre[0] - centre[-1]) > 1 and reversed_order != (side_name == 'right'):
                    problem(name + ' ' + side_name + ': lane or rail in the wrong direction')
            if any(o < 0 for o in s['offsets']) or any(o > rd['half_width'] + 1e-3 for o in s['offsets']):
                problem(name + ' ' + side_name + ': lane offsets out of the road ' + str(s['offsets']))
            if s['lanes'] > 4:
                problem(name + ' ' + side_name + ': more than 4 lanes')
        for end_name in ('start', 'end'):
            e = rd[end_name]
            if e['index'] != CDCDCDCD:
                if e['intersection'] >= len(intersections):
                    problem(name + ' ' + end_name + ': intersection ' + str(e['intersection']) + ' out of range')
                elif e['index'] >= len(intersections[e['intersection']]['roads']) or intersections[e['intersection']]['roads'][e['index']] != i:
                    problem(name + ' ' + end_name + ': not at its index in the intersection')
            if np.any(e['origin'] != 0):
                if abs(np.linalg.norm(e['axis'] - e['origin']) - 1) > 1e-3:
                    problem(name + ' ' + end_name + ': traffic light axis %.2f m long' % np.linalg.norm(e['axis'] - e['origin']))
    for it in intersections:
        if len(it['roads']) < 3:
            continue
        angles = []
        for ri in it['roads']:
            rd = roads[ri]
            near = rd['centre'][0] if np.linalg.norm(rd['centre'][0] - it['centre']) < np.linalg.norm(rd['centre'][-1] - it['centre']) else rd['centre'][-1]
            angles.append(math.atan2(near[2] - it['centre'][2], near[0] - it['centre'][0]))
        turns = sum((angles[k] - angles[(k + 1) % len(angles)]) % (2 * math.pi) for k in range(len(angles)))
        if turns > 2 * math.pi + 1e-3:
            problem('intersection ' + str(it['id']) + ': roads not in the stock order (decreasing atan2(z, x))')
    return problems


def main(args):
    do_derive = '--derive' in args
    do_lint = '--lint' in args
    verbose = '--verbose' in args
    files = [a for a in args if not a.startswith('--')]
    if not files:
        print(__doc__ if __doc__ else 'usage: bai_check.py [--derive] [--lint] [--verbose] file.bai ...')
        return 2
    if not do_derive and not do_lint:
        do_derive = do_lint = True
    failed = False
    for path in files:
        roads, intersections = read_bai(path)
        print('== %s: %d roads, %d intersections' % (path, len(roads), len(intersections)))
        if do_derive:
            stats = Stats()
            derive(roads, stats)
            stats.report(0.05)
        if do_lint:
            problems = lint(roads, intersections, verbose)
            kinds = {}
            for p in problems:
                key = p.split(': ', 1)[1] if ': ' in p else p
                key = ''.join(c for c in key if not c.isdigit() and c != '.')
                kinds[key] = kinds.get(key, 0) + 1
            print('  lint: %d problems' % len(problems))
            for key, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
                print('    %5d x %s' % (count, key))
            failed = failed or len(problems) > 0
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
