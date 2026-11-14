# Replays the cable cars of a BAI file through its intersections (traffic/rails.py, the rules of the game) and measures
# how far the paths are from the rail decals of a decals.pathset (the centre lines of the paths whose texture starts
# with r4i_rails, without the crossing squares). The paths of each road from the point where the car leaves it are
# measured, without the first CABLE_CAR_HALF_LENGTH (the stock rail decals start at the end of the road, the car
# leaves it earlier) and the last 0.3 m.
#
#   python -I cable_car_rails_check.py [--sample N] [--seed S] city.bai decals.pathset
#
# On the stock SF the straight crossings match within about 0.1 m; the turns are 1-3 m off whatever tangents are used,
# so their decals were drawn by hand and don't follow the cars. Also lists the intersections where the cars find no
# next road (3 or more than 4 roads with trams).

import argparse
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bai_check import read_bai  # noqa: E402
from decal_check import read_pathset  # noqa: E402
from traffic.rails import CABLE_CAR_HALF_LENGTH, curve_start, next_tram_road, transition_curve  # noqa: E402


def has_trams(road):
    return road['left']['trams'] > 0


def rail(road, forward):
    # the tram vertices of the side going from the start to the end (forward, the left side of the file) or back
    return road['left']['tram_v'][0] if forward else road['right']['tram_v'][0]


def exit_dir(road, forward):
    # the direction of the road where the car leaves it (-z of the last section, z of the first going back)
    return -road['z'][-1] if forward else road['z'][0]


def entry_dir(road, forward):
    return -road['z'][0] if forward else road['z'][-1]


def paths(roads, intersection):
    # [(road id, next road id or None, curve)] for each road with trams arriving at the intersection
    by_id = {r['id']: r for r in roads}
    ids = intersection['roads']
    flags = [has_trams(by_id[i]) for i in ids]
    res = []
    for k, rid in enumerate(ids):
        road = by_id[rid]
        if not flags[k]:
            continue
        forward = road['end']['intersection'] == intersection['id']
        nk = next_tram_road(flags, k)
        if nk is None:
            res.append((rid, None, None))
            continue
        nxt = by_id[ids[nk]]
        n_forward = nxt['start']['intersection'] == intersection['id'] if nk != k else not forward
        n = road['n']
        start = curve_start(rail(road, forward), road['cdist'][n - 1] - road['cdist'][n - 2])
        curve = transition_curve(start, exit_dir(road, forward), rail(nxt, n_forward)[0], entry_dir(nxt, n_forward), 0.5)
        res.append((rid, nxt['id'], curve))
    return res


class Centrelines:
    def __init__(self, decals):
        segments = []
        for name, points in decals:
            low = name.lower()
            if not low.startswith('r4i_rails') or low.startswith('r4i_railsx'):
                continue
            mids = [(points[2 * k] + points[2 * k + 1]) / 2 for k in range(len(points) // 2)]
            segments += [(mids[k][[0, 2]], mids[k + 1][[0, 2]]) for k in range(len(mids) - 1)]
        self.a = np.array([s[0] for s in segments]).reshape(-1, 2)
        self.b = np.array([s[1] for s in segments]).reshape(-1, 2)

    def distance(self, p):
        if len(self.a) == 0:
            return float('inf')
        q = np.asarray(p)[[0, 2]]
        ab = self.b - self.a
        t = np.clip(((q - self.a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-9), 0, 1)
        return float(np.min(np.linalg.norm(self.a + ab * t[:, None] - q, axis=1)))


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample', type=int, default=0, help='check only N random intersections')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('bai')
    parser.add_argument('pathset')
    a = parser.parse_args(args)
    roads, intersections = read_bai(a.bai)
    lines = Centrelines(read_pathset(a.pathset))
    by_id = {r['id']: r for r in roads}
    tram = [it for it in intersections if any(has_trams(by_id[i]) for i in it['roads'])]
    if a.sample:
        random.seed(a.seed)
        tram = random.sample(tram, min(a.sample, len(tram)))
    for it in sorted(tram, key=lambda x: x['id']):
        count = sum(1 for i in it['roads'] if has_trams(by_id[i]))
        for rid, nid, curve in paths(roads, it):
            if curve is None:
                print('intersection %d: road %d finds no next road (%d roads with trams)' % (it['id'], rid, count))
                continue
            if nid == rid:
                print('intersection %d: road %d is the end of a line' % (it['id'], rid))
                continue
            start, end = curve[0], curve[-1]
            ds = [lines.distance(p) for p in curve
                  if np.linalg.norm((p - start)[[0, 2]]) > CABLE_CAR_HALF_LENGTH + 0.3
                  and np.linalg.norm((p - end)[[0, 2]]) > 0.3]
            if ds:
                print('intersection %d: road %d -> %d: mean %.2f m, max %.2f m from the rail decals'
                      % (it['id'], rid, nid, np.mean(ds), max(ds)))


if __name__ == '__main__':
    main(sys.argv[1:])
