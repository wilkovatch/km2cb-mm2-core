# How the game moves the cable cars from a road into the next one through an intersection (reverse-engineered from
# midtown2.exe, see docs/agents/trains-and-boats.md, "Cable cars"). lua/cableCars.lua draws the rails of the
# intersections with the same rules: keep the two in sync.
#
# A cable car goes along the tram vertices of the side of its road, and at the end of the road it takes the next road
# of the intersection with trams (next_tram_road): the only other one when the intersection has 2, the second one
# after its own in the order of the intersection when it has 4, its own road in the other direction when it has 1
# (the end of a line). With 3 or more than 4 it finds none (it keeps going on its own road from its start, jumping
# back across the road). It crosses the intersection along a 2D cubic Hermite (transition_curve) from the point of
# the last segment of its road half its length before the end, to the first tram vertex of the side of the next road
# going away from the intersection, with the directions of the two roads there (the z axis of the sections) as
# tangents, scaled by the distance between the two points along x plus the one along z.

import numpy as np

CABLE_CAR_HALF_LENGTH = 4.36  # -min z of the bounding box of va_cablecar_f (BODY_H and BODY_M)
CURVE_STEP = 2.0  # the length of the segments of the drawn curves


def next_tram_road(has_trams, own):
    # has_trams: whether each road of the intersection (in the order of the BAI) has trams; own: the index of the road
    # the cable car comes from. Returns the index of the next road (own at the end of a line), None if there is none
    count = sum(1 for t in has_trams if t)
    if count == 1:
        return own
    need = {2: 1, 4: 2}.get(count)
    if need is None:
        return None
    n = len(has_trams)
    i, found = own, 0
    for _ in range(n):
        i = (i + 1) % n
        if has_trams[i]:
            found += 1
            if found == need:
                return i
    return None


def curve_start(rail, centre_length, half_length=CABLE_CAR_HALF_LENGTH):
    # where the cable car leaves its road: on the last segment of the rail (in the direction it goes), at the fraction
    # (L - half_length) / L of it, with L the length of the last segment of the centre line (as the game does)
    a, b = np.asarray(rail[-2], dtype=float), np.asarray(rail[-1], dtype=float)
    return a + (b - a) * ((centre_length - half_length) / centre_length)


def hermite(p0, p1, t0, t1, t):
    h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
    return p0 * h00 + t0 * h10 + p1 * h01 + t1 * h11


def transition_curve(start, start_dir, end, end_dir, step=CURVE_STEP):
    # the path of the cable car through the intersection, in a y-up space: from start, going along start_dir (the
    # direction of the road it leaves), to end, going along end_dir (the direction of the next road). The game
    # evaluates only x and z; y goes linearly from start to end here (the game keeps its own height)
    start, end = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
    scale = abs(start[0] - end[0]) + abs(start[2] - end[2])
    t0 = np.asarray(start_dir, dtype=float) * scale
    t1 = np.asarray(end_dir, dtype=float) * scale
    n = max(2, int(np.ceil(np.linalg.norm((end - start)[[0, 2]]) / step)))
    res = []
    for k in range(n + 1):
        t = k / n
        p = hermite(start, end, t0, t1, t)
        p[1] = start[1] + (end[1] - start[1]) * t
        res.append(p)
    return res
