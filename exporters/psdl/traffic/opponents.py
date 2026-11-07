# The route of the race opponents, as midtown2.exe drives it (reverse-engineered, see docs/agents/races-and-state.md of
# the core), to find the opponents that get stuck before playing the race.
#
# The OPP file of an opponent has its start (first row), its waypoints and the finish (last row). The game looks up the
# room of every row (an error if there is none) and replaces each waypoint with the first BAI intersection of its room
# (if there is none, the waypoint is left undefined). The opponent doesn't search for a route: from a waypoint to the
# next one it follows the road joining their intersections, if a single road joins them, otherwise it drives straight
# to the centre of the next intersection, through whatever is in the way (the stock races do it on purpose to take
# shortcuts through parks). On a circuit, after the last waypoint it goes on to the second one.
#
# Positions are in the coordinates of the program (x, y up, z).

import numpy as np

from .rooms import RoomFinder

# the step of the points checked along a straight leg (m), how far from a waypoint they start (m), and the height above
# its bottom under which a facade blocks the car (m)
STRAIGHT_STEP = 2.0
STRAIGHT_MARGIN = 3.0
FACADE_CLEARANCE = 1.0

# what an opponent does on a leg
ROAD = 'road'  # follows a road
STRAIGHT = 'straight'  # drives straight, with nothing found in the way
BLOCKED = 'blocked'  # drives straight into a facade or out of the city


class Leg:
    def __init__(self, kind, start, end, points, road=None, outside=0.0, facades=0, first_problem=None):
        self.kind = kind
        self.start = start  # labels of the ends (e.g. "start", "waypoint 2", "finish")
        self.end = end
        self.points = points  # the path of the opponent
        self.road = road  # the BaiRoad followed (ROAD)
        self.outside = outside  # metres of a straight leg out of the rooms of the city
        self.facades = facades  # facades crossed by a straight leg
        self.first_problem = first_problem  # where a blocked leg first hits something


class Issue:
    def __init__(self, level, code, message, position, leg=None):
        self.level = level  # error, warning
        self.code = code
        self.message = message
        self.position = position
        self.leg = leg


class OpponentRoute:
    def __init__(self):
        self.legs = []
        self.issues = []

    def ok(self):
        return not any(i.level == 'error' for i in self.issues)


def road_label(road):
    # a chain of roads has the names of all of them
    return ', '.join(road.name) if isinstance(road.name, (list, tuple)) else str(road.name)


def _centre_line(road, from_start):
    # the centre of the road, from its start (or its end), midway between the curbs
    right, left = road.paths.right.curb, road.paths.left.curb
    points = [(np.asarray(a, dtype=float) + np.asarray(b, dtype=float)) * 0.5 for a, b in zip(right, left)]
    return points if from_start else list(reversed(points))


class OpponentMap:
    # the city as an opponent sees it: room_of(position) -> the room (block) number, 0 if none; the BAI network; the
    # facade bounds as (a, b, bottom, top), a and b the ends of their base (x, z)
    def __init__(self, room_of, network, facades=()):
        self.room_of = room_of
        self.network = network
        self.intersection_in = {}
        for node in network.intersections:  # the first one of a room, as the game finds it
            self.intersection_in.setdefault(node.room, node)
        self.road_in = {}
        for road in network.roads:
            for room in road.rooms:
                self.road_in.setdefault(room, road)
        f = list(facades)
        self.facade_a = np.array([x[0] for x in f], dtype=float).reshape(-1, 2)
        self.facade_b = np.array([x[1] for x in f], dtype=float).reshape(-1, 2)
        self.facade_bottom = np.array([x[2] for x in f], dtype=float)
        self.facade_top = np.array([x[3] for x in f], dtype=float)

    @staticmethod
    def from_processor(jp, parts):
        # jp: a JsonProcessor after get_objects (its network built), parts: the parts it returned
        facades = []
        for part in parts:
            if not part.name.endswith('_FACB') or len(part.vertices) < 4:
                continue
            v = [np.asarray(p, dtype=float) for p in part.vertices]
            ys = [p[1] for p in v]
            facades.append(((v[0][0], v[0][2]), (v[1][0], v[1][2]), min(ys), max(ys)))
        rooms = RoomFinder(jp)
        return OpponentMap(rooms.room_of, jp.network, facades)

    @staticmethod
    def road_between(a, b):
        # the road joining two intersections, with the direction from a: as the game does, the first road in the list
        # of a that is also in the list of b
        for road, at_start in a.roads:
            if any(other is road for other, _ in b.roads):
                return road, at_start
        return None, False

    def road_from(self, room, node):
        # the road of a room with an end on an intersection (the start or the finish next to a waypoint)
        road = self.road_in.get(room)
        if road is not None and node is not None and node in (road.start.intersection, road.end.intersection):
            return road
        return None

    def straight(self, a, b, label_a, label_b):
        # a straight leg from a to b: the points out of the rooms and the facades in the way
        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)
        d = b - a
        length = float(np.hypot(d[0], d[2]))
        outside = 0.0
        first = None
        if length > 2 * STRAIGHT_MARGIN:
            n = max(1, int((length - 2 * STRAIGHT_MARGIN) / STRAIGHT_STEP))
            for k in range(n + 1):
                t = (STRAIGHT_MARGIN + (length - 2 * STRAIGHT_MARGIN) * k / n) / length
                p = a + d * t
                if self.room_of(p) == 0:
                    outside += (length - 2 * STRAIGHT_MARGIN) / n if n > 0 else 0.0
                    if first is None:
                        first = p
        facades = 0
        if len(self.facade_a) > 0 and length > 0:
            # 2D intersections of the leg with the base of the facades, blocking if the car is under their top
            p, r = np.array([a[0], a[2]]), np.array([d[0], d[2]])
            q, s = self.facade_a, self.facade_b - self.facade_a
            denom = r[0] * s[:, 1] - r[1] * s[:, 0]
            qp = q - p
            with np.errstate(divide='ignore', invalid='ignore'):
                t = (qp[:, 0] * s[:, 1] - qp[:, 1] * s[:, 0]) / denom
                u = (qp[:, 0] * r[1] - qp[:, 1] * r[0]) / denom
                hit = (np.abs(denom) > 1e-9) & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
                # the height of the car there, as if the ground were straight between the ends
                y = a[1] + d[1] * np.where(hit, t, 0.0)
            hit &= (y >= self.facade_bottom - FACADE_CLEARANCE) & (y <= self.facade_top)
            idx = np.nonzero(hit)[0]
            facades = len(idx)
            if facades > 0:
                tmin = float(np.min(t[idx]))
                if first is None or tmin * length < np.hypot(first[0] - a[0], first[2] - a[2]):
                    first = a + d * tmin
        kind = BLOCKED if (facades > 0 or outside > 0) else STRAIGHT
        return Leg(kind, label_a, label_b, [a, b], outside=outside, facades=facades, first_problem=first)

    def check(self, start, waypoints, circuit=False):
        # start: the position of the car, waypoints: the positions of the waypoints, the last one being the finish
        res = OpponentRoute()
        rows = [np.asarray(start, dtype=float)] + [np.asarray(p, dtype=float) for p in waypoints]
        labels = ['start'] + ['waypoint ' + str(i + 1) for i in range(len(waypoints))]
        if len(waypoints) > 0:
            labels[-1] = 'finish (waypoint ' + str(len(waypoints)) + ')'
        if len(waypoints) < 2:
            res.issues.append(Issue('error', 'opponent_no_waypoints',
                                    'it needs at least a waypoint on an intersection and the finish (the last waypoint)', rows[0]))
        rooms = [self.room_of(p) for p in rows]
        for i, room in enumerate(rooms):
            if room == 0:
                res.issues.append(Issue('error', 'opponent_point_no_room',
                                        'the ' + labels[i] + ' is not in any room of the city', rows[i]))
        # the waypoints between the start and the finish are intersections
        nodes = []
        for i in range(1, len(rows) - 1):
            node = self.intersection_in.get(rooms[i]) if rooms[i] != 0 else None
            if node is None and rooms[i] != 0:
                road = self.road_in.get(rooms[i])
                where = (' (it is on ' + road_label(road) + ')') if road is not None else ''
                res.issues.append(Issue('error', 'opponent_waypoint_not_intersection',
                                        'the ' + labels[i] + ' is not on an intersection' + where
                                        + ': the game leaves it undefined, so the opponent goes astray', rows[i]))
            nodes.append(node)
        if len(waypoints) < 2:
            return res

        def leg_between(i, j, a, b):
            # from waypoint row i to row j, a and b their intersections
            if a is None or b is None:
                return None
            if a is b:
                res.issues.append(Issue('warning', 'opponent_waypoint_repeated',
                                        'the ' + labels[i] + ' and the ' + labels[j] + ' are on the same intersection', rows[j]))
                return Leg(ROAD, labels[i], labels[j], [a.centre, b.centre])
            road, from_start = self.road_between(a, b)
            if road is not None:
                return Leg(ROAD, labels[i], labels[j], _centre_line(road, from_start), road=road)
            return self.straight(a.centre, b.centre, labels[i], labels[j])

        def leg_end(i, j, node, toward):
            # between the start or the finish (row i or j, a position) and the waypoint next to it
            pos_room = rooms[i] if toward else rooms[j]
            pos = rows[i] if toward else rows[j]
            if node is None:
                return None
            if pos_room != 0 and self.intersection_in.get(pos_room) is node:
                return Leg(ROAD, labels[i], labels[j], [pos, node.centre] if toward else [node.centre, pos])
            road = self.road_from(pos_room, node)
            if road is not None:
                return Leg(ROAD, labels[i], labels[j], [pos, node.centre] if toward else [node.centre, pos], road=road)
            return self.straight(pos, node.centre, labels[i], labels[j]) if toward else self.straight(node.centre, pos, labels[i], labels[j])

        legs = []
        if len(nodes) > 0:
            legs.append(leg_end(0, 1, nodes[0], True))
            for k in range(len(nodes) - 1):
                legs.append(leg_between(k + 1, k + 2, nodes[k], nodes[k + 1]))
            if circuit and len(nodes) > 1:
                # after the last waypoint the next lap goes on to the second one
                legs.append(leg_between(len(nodes), 2, nodes[-1], nodes[1]) if nodes[-1] is not nodes[0] else None)
            legs.append(leg_end(len(nodes), len(nodes) + 1, nodes[-1], False))
        else:
            legs.append(self.straight(rows[0], rows[-1], labels[0], labels[-1]))
        def why(leg):
            # why a leg is straight
            if leg.start == labels[0]:
                return 'the start is not on the intersection of the ' + leg.end + ' or on a road to it'
            if leg.end == labels[-1]:
                return 'the finish is not on the intersection of the ' + leg.start + ' or on a road from it'
            return 'no single road joins the intersections of the ' + leg.start + ' and of the ' + leg.end

        for leg in legs:
            if leg is None:
                continue
            res.legs.append(leg)
            if leg.kind == STRAIGHT:
                res.issues.append(Issue('warning', 'opponent_leg_straight',
                                        why(leg) + ': the opponent leaves the roads and drives straight', leg.points[0], leg))
            elif leg.kind == BLOCKED:
                what = []
                if leg.facades > 0:
                    what.append(str(leg.facades) + (' facades' if leg.facades > 1 else ' facade'))
                if leg.outside > 0:
                    what.append('%.0f m out of the city' % leg.outside)
                res.issues.append(Issue('error', 'opponent_leg_blocked',
                                        why(leg) + ': the opponent drives straight through ' + ' and '.join(what)
                                        + ' (add a waypoint on every intersection along the way)',
                                        leg.first_problem if leg.first_problem is not None else leg.points[0], leg))
        return res

