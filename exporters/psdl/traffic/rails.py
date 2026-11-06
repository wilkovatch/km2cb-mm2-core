# The cable car rails going on through an intersection from a road into another one (used by
# converters/generateRailDecals): the roads are paired when their directions towards the intersection are more than
# 60 degrees apart, and each rail is joined to the closest one of the other road along a curve with points about
# every 2 m.

import math

import numpy as np

RAIL_JOIN_MAX_DOT = 0.5
RAIL_JOIN_STEP = 2.0


def join_rails(ends):
    # ends: (heading towards the intersection, [the two rail ends], data) of each road; the most opposite directions
    # are paired first. Returns [(curve, data of the first road)]
    res = []
    pairs = sorted((float(np.dot(ends[i][0], ends[j][0])), i, j) for i in range(len(ends)) for j in range(i + 1, len(ends)))
    used = set()
    for dot, i, j in pairs:
        if dot > RAIL_JOIN_MAX_DOT or i in used or j in used:
            continue
        used.update((i, j))
        (h_a, rails_a, data), (h_b, rails_b, _) = ends[i], ends[j]
        if len(rails_a) != 2 or len(rails_b) != 2:
            continue
        straight = np.linalg.norm(np.subtract(rails_a[0], rails_b[0])) + np.linalg.norm(np.subtract(rails_a[1], rails_b[1]))
        crossed = np.linalg.norm(np.subtract(rails_a[0], rails_b[1])) + np.linalg.norm(np.subtract(rails_a[1], rails_b[0]))
        if crossed < straight:
            rails_b = rails_b[::-1]
        for a, b in zip(rails_a, rails_b):
            length = np.linalg.norm(np.subtract(a, b))
            n = max(2, int(math.ceil(length / RAIL_JOIN_STEP)))
            curve = []
            for k in range(n + 1):
                t = k / n
                h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
                curve.append(np.array(a) * h00 + h_a * length * h10 + np.array(b) * h01 - h_b * length * h11)
            res.append((curve, data))
    return res
