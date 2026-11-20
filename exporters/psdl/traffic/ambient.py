# Where the ambient cars of the game go at an intersection, and the path they take through it, as midtown2.exe drives
# them (reverse-engineered, see docs/agents/psdl-and-bai.md of the core, "Ambient car turns"). The checks/trafficPaths
# check of the core draws them.
#
# At the end of its road a car picks the next road from the roads of the BAI intersection, in the order of the BAI,
# with a routine chosen by its lane (0x539750):
# - a single lane (single_lane): any other road with cars leaving the intersection, at random, or the first freeway
#   road found in the order of the BAI. It arrives in the outer lane of a road that turns right by more than 0.5 rad,
#   otherwise in lane 0;
# - lane 0, the inner one (inner_lane): the first road with cars going backwards in the order of the BAI (the left
#   turn) or the next one (straight on), unless the start of its lane of the same number is 2 m or more to the right of
#   the end of the lane of the car; it arrives in lane 0;
# - the outer lane (outer_lane): the same going forwards (the right turn, or straight on unless 2 m or more to the
#   left); it arrives in the outer lane;
# - a lane between them (middle_lane): straight on (the second road with cars) when 3 or more other roads let cars
#   leave, otherwise the roads with 3 or more lanes: the only one, or the one whose outer lane ends least far to the
#   side, or the first road with cars (in its outer lane) without one. It keeps its lane number;
# - on a freeway, a lane other than the outer one first looks for a freeway road (the first one going forwards) and
#   keeps its lane number (unchecked, see the 0x5440c5 crash in docs/agents/exporting.md); the outer lane and the lanes
#   without a freeway road go on as above.
# The lane number on the next road is clamped to its lanes when the car gets there (0x557c6c). Going forwards in the
# order of the BAI meets the right turn first.
#
# With left-hand traffic (the AIMAP flag), the game swaps the lanes of the two sides of every road when it loads the map
# (GameRoad.drive_on_left), and then runs the same routines: the lane next to the centre line becomes the last one.
#
# It leaves its lane on its last segment, its front half length before the end (at the fraction (L - h) / L of the
# segment, L being the length of the last segment of lane 0 of its side), and goes to the start of the lane of the next
# road along a 2D cubic Hermite with the directions of the two roads as tangents, scaled by |dx| + |dz| (the same curve
# as the cable cars, see rails.py). The game also moves each car sideways by a random 0.5 sin(2 pi r) m along the x axis
# of the sections, which isn't drawn.
#
# The emulation works on the BAI roads as written (writers/bai_writer.py Route), in the space of the game (x mirrored,
# y up); the paths are returned in the coordinates of the program.

import math

import numpy as np

from writers.bai_writer import FLAG_FREEWAY, Route, cumulative_lengths, side_traffic_type
from .rails import transition_curve

# the distance from the centre of a car to its front (-min z of its BODY_H box): 1.6 to 2.6 m for the stock ambient
# cars, 3.7 to 6.5 for the limousine, the buses and the truck
CAR_FRONT = 2.3
# the turn of the next road (rad) above which a car of a single lane road arrives in its outer lane (0x558270)
TURN_ANGLE = 0.5
# how far (m) the start of the next lane can be to the right (inner lane) or the left (outer lane) for straight on
STRAIGHT_OFFSET = 2.0
# turns above this angle (rad) are called U-turns
U_TURN_ANGLE = 2.6
# the length (m) of the lanes drawn before and after the curve
LEAD = 5.0

# the sides of a BAI road as the game numbers them: the second side of the file (the left one) goes from the start of
# the road to its end, the first one (the right one) from its end to its start
START_TO_END = 1
END_TO_START = -1

RIGHT, STRAIGHT, LEFT, U_TURN = 'right', 'straight', 'left', 'uturn'


def to_game(p):
    # a point or vector of the space of the writers (x, y, z up) in the space of the game (BinaryFileHelper.write_vec3)
    return np.array((-p[0], p[2], p[1]), dtype=float)


def to_program(p):
    return [float(-p[0]), float(p[1]), float(p[2])]


def xz(v):
    return np.array((v[0], v[2]), dtype=float)


class GameRoad:
    # a BAI road as the game reads it, in the space of the game: lanes[side] are its lanes (inner first) and then its
    # sidewalk, in the order the file stores them (the right side lanes from the end to the start). drive_on_left: the
    # AIMAP has [Ambients Drive On The Left] (the left-hand traffic of the city)
    def __init__(self, road, drive_on_left=False):
        route = Route(road)
        self.road = road
        self.n = route.num_sections()
        self.freeway = bool(route.flags & FLAG_FREEWAY)

        def conv(points):
            return [to_game(p) for p in points]
        right = [conv(list(reversed(lane))) for lane in route.right.lanes]
        left = [conv(lane) for lane in route.left.lanes]
        self.lanes = {END_TO_START: right + [conv(route.right.sidewalk)], START_TO_END: left + [conv(route.left.sidewalk)]}
        self.count = {END_TO_START: len(right), START_TO_END: len(left)}
        self.type = {END_TO_START: side_traffic_type(road, True), START_TO_END: side_traffic_type(road, False)}
        self.centre = conv(route.centre)
        self.x = conv(route.x)
        self.z = conv(route.z)
        self.mismatched_sides = False
        if drive_on_left:
            self.drive_on_left()

    def drive_on_left(self):
        # 0x545d00, when the map loads: the lanes of each side are copied over the array of the other side, the last one
        # first and each one reversed, so the cars of a side follow the lanes drawn for the other direction (lane 0, the
        # one next to the centre line, becomes the last lane). The lane counts stay: with different counts, the lanes
        # past the count of the other side keep their own geometry (and the game writes past the shorter array)
        a, b = self.lanes[END_TO_START], self.lanes[START_TO_END]
        ca, cb = self.count[END_TO_START], self.count[START_TO_END]
        new_a, new_b = list(a), list(b)
        for k in range(min(ca, len(b))):
            new_b[k] = list(reversed(a[ca - 1 - k]))
        for k in range(min(cb, len(a))):
            new_a[k] = list(reversed(b[cb - 1 - k]))
        self.lanes = {END_TO_START: new_a, START_TO_END: new_b}
        self.mismatched_sides = ca > 0 and cb > 0 and ca != cb

    def cars(self, side):
        # whether cars go along a side (ambient type 0 or 2)
        return self.type[side] & 1 == 0

    def lane_end(self, side, lane):
        return self.lanes[side][lane][-1]

    def lane_start(self, side, lane):
        return self.lanes[side][lane][0]

    def arrival_x(self, side):
        # the x axis of the section where a car of the side leaves the road
        return self.x[-1] if side == START_TO_END else self.x[0]

    def arrival_direction(self, side):
        # the direction of the road where a car of the side leaves it (548cc0)
        return -self.z[-1] if side == START_TO_END else self.z[0]

    def departure_direction(self, side):
        # the direction of the road where a car of the side enters it (548d50)
        return -self.z[0] if side == START_TO_END else self.z[-1]

    def first_segment(self, side):
        # the direction of the first segment of the centre line for a car entering the side
        c = self.centre
        return np.subtract(c[1], c[0]) if side == START_TO_END else np.subtract(c[-2], c[-1])


class Move:
    # where a car of a lane can go: the slot of the next road in the intersection, its side and lane, and the path
    def __init__(self, slot, road, side, lane):
        self.slot = slot
        self.road = road  # GameRoad
        self.side = side
        self.lane = lane  # as the turn routine set it (unclamped)
        self.turn = STRAIGHT
        self.points = []  # the path, in the coordinates of the program

    def driven_lane(self):
        return min(self.lane, self.road.count[self.side] - 1)


class LaneResult:
    def __init__(self, road, side, lane):
        self.road = road
        self.side = side
        self.lane = lane
        self.moves = []
        self.problems = []  # (code, message)


class IntersectionTraffic:
    # the ambient cars of a BAI intersection; roads: a dict BaiRoad -> GameRoad shared between intersections
    def __init__(self, node, roads, drive_on_left=False, car_front=CAR_FRONT):
        self.node = node
        self.roads = roads
        self.drive_on_left = drive_on_left
        self.car_front = car_front

    def game_road(self, road):
        res = self.roads.get(road)
        if res is None:
            res = self.roads[road] = GameRoad(road, self.drive_on_left)
        return res

    def slot(self, j):
        # the road of a slot of the intersection and the side a car takes to leave the intersection on it (the game
        # compares the intersection at the start of the road with this one)
        road = self.node.roads[j][0]
        side = START_TO_END if road.start.intersection is self.node else END_TO_START
        return self.game_road(road), side

    def around(self, own, step):
        # the other slots of the intersection, going forwards (step 1) or backwards (-1) in the order of the BAI
        n = len(self.node.roads)
        for k in range(1, n):
            j = (own + step * k) % n
            road, side = self.slot(j)
            yield j, road, side

    def turn_angle(self, road, side, nxt, nside):
        # the angle of the first segment of the next road from the direction of the car, positive to the right (0x558270)
        d = nxt.first_segment(nside)
        x = road.x[-1] * -1 if side == START_TO_END else road.x[0]
        z = road.z[-1] * -1 if side == START_TO_END else road.z[0]
        return math.atan2(float(np.dot(d, x)), float(np.dot(d, z)))

    def offset_left(self, road, side, lane, nxt, nside):
        # how far to the left the start of the lane of the same number of the next road is from the end of the lane of
        # the car (along x and z only); a lane number past the lanes is clamped only when it's greater than their count,
        # so the count itself reads the sidewalk, as the game does
        n = nxt.count[nside]
        k = lane if lane <= n else n - 1
        q = nxt.lane_start(nside, k)
        p = road.lane_end(side, lane)
        left = road.arrival_x(side) * (1 if side == START_TO_END else -1)
        return float(np.dot(xz(q - p), xz(left)))

    # the turn routines: each returns the moves (several when the game picks one at random)

    def single_lane(self, own, road, side, lane):
        found = []
        for j, nxt, nside in self.around(own, 1):
            if not nxt.cars(nside):
                continue
            if nxt.freeway:
                return [Move(j, nxt, nside, nxt.count[nside] - 1)]
            found.append((j, nxt, nside))
        res = []
        for j, nxt, nside in found:
            right = self.turn_angle(road, side, nxt, nside) > TURN_ANGLE
            res.append(Move(j, nxt, nside, nxt.count[nside] - 1 if right else 0))
        return res

    def two_choices(self, own, road, side, lane, step):
        # the inner lane (step -1, lane 0) and the outer lane (step 1, the outer lane of the next road): the first road
        # with cars, and the one after it if the start of its lane isn't too far to the side
        res = []
        first = True
        for j, nxt, nside in self.around(own, step):
            if not nxt.cars(nside):
                continue
            if first:
                res.append((j, nxt, nside))
                first = False
                continue
            s = self.offset_left(road, side, lane, nxt, nside)
            if (s > -STRAIGHT_OFFSET) if step < 0 else (s < STRAIGHT_OFFSET):
                res.append((j, nxt, nside))
            break
        return [Move(j, nxt, nside, 0 if step < 0 else nxt.count[nside] - 1) for j, nxt, nside in res]

    def first_road(self, own):
        # 0x538ec0: the first road with cars going forwards, in its outer lane
        for j, nxt, nside in self.around(own, 1):
            if nxt.cars(nside):
                return [Move(j, nxt, nside, nxt.count[nside] - 1)]
        return []

    def exits(self, road):
        # the other roads of the intersection that let cars leave it (0x54a060)
        res = 0
        for other, _ in self.node.roads:
            if other is road.road:
                continue
            g = self.game_road(other)
            if other.start.intersection is self.node:
                res += 1 if g.cars(START_TO_END) else 0
            elif g.count[END_TO_START] > 0 and g.cars(END_TO_START):
                res += 1
        return res

    def middle_lane(self, own, road, side, lane):
        if self.exits(road) >= 3:
            found = 0
            for j, nxt, nside in self.around(own, 1):
                if nxt.cars(nside):
                    found += 1
                    if found == 2:
                        return [Move(j, nxt, nside, min(lane, nxt.count[nside] - 1))]
            return []
        wide = [(j, nxt, nside) for j, nxt, nside in self.around(own, 1) if nxt.cars(nside) and nxt.count[nside] >= 3]
        if len(wide) == 1:
            j, nxt, nside = wide[0]
            return [Move(j, nxt, nside, lane)]
        if not wide:
            return self.first_road(own)
        # the road whose outer lane ends least far to the side of the end of the lane of the car
        p = road.lane_end(side, lane)
        x = xz(road.arrival_x(side))
        best, best_d = None, 1e6
        for j, nxt, nside in wide:
            d = abs(float(np.dot(xz(nxt.lanes[nside][nxt.count[nside] - 1][-1] - p), x)))
            if d < best_d:
                best, best_d = (j, nxt, nside), d
        j, nxt, nside = best
        return [Move(j, nxt, nside, lane)]

    def freeway_lane(self, own, road, side, lane):
        # a lane of a freeway other than the outer one (0x539870)
        for j, nxt, nside in self.around(own, 1):
            if nxt.cars(nside) and nxt.freeway:
                return [Move(j, nxt, nside, lane)]
        return self.by_lane(own, road, side, lane)

    def by_lane(self, own, road, side, lane):
        count = road.count[side]
        if lane == 0:
            return self.two_choices(own, road, side, lane, -1)
        if lane == count - 1:
            return self.two_choices(own, road, side, lane, 1)
        return self.middle_lane(own, road, side, lane)

    def moves(self, own, road, side, lane):
        # the dispatcher (0x539750)
        count = road.count[side]
        if road.freeway:
            if lane == count - 1:
                # 0x5399a0: its own choice is overwritten by the routine of the lane
                return self.by_lane(own, road, side, lane)
            return self.freeway_lane(own, road, side, lane)
        if count == 1:
            return self.single_lane(own, road, side, lane)
        return self.by_lane(own, road, side, lane)

    def path(self, road, side, lane, move):
        # the path of a car from its lane through the intersection into the next lane, in the coordinates of the program
        nxt, nside = move.road, move.side
        points = road.lanes[side][lane]
        a, b = points[-2], points[-1]
        lane0 = cumulative_lengths(road.lanes[side][0])
        length = lane0[-1] - lane0[-2]
        t = (length - self.car_front) / length if length > 1e-6 else 1.0
        start = a + (b - a) * t
        end = nxt.lane_start(nside, move.driven_lane())
        curve = transition_curve(start, road.arrival_direction(side), end, nxt.departure_direction(nside))
        res = []
        back = a - start
        if np.linalg.norm(back) > 1e-6:
            res.append(start + back * min(1.0, LEAD / float(np.linalg.norm(back))))
        res += curve
        after = nxt.lanes[nside][move.driven_lane()][1] - end
        if np.linalg.norm(after) > 1e-6:
            res.append(end + after * min(1.0, LEAD / float(np.linalg.norm(after))))
        return [to_program(p) for p in res]

    def lanes(self):
        # the result of every lane of every road arriving at the intersection with cars
        res = []
        for own, (bai_road, at_start) in enumerate(self.node.roads):
            road = self.game_road(bai_road)
            side = END_TO_START if at_start else START_TO_END
            if not road.cars(side):
                continue
            for lane in range(road.count[side]):
                result = LaneResult(road, side, lane)
                if road.mismatched_sides and lane == 0:
                    result.problems.append(('traffic_left_hand_lanes', 'with left-hand traffic the game swaps the lanes '
                                            'of the two directions but keeps their counts, so a two-way road needs the '
                                            'same number of lanes both ways (' + str(road.count[END_TO_START]) + ' and '
                                            + str(road.count[START_TO_END]) + ' here): some cars follow the wrong lanes'))
                result.moves = self.moves(own, road, side, lane)
                if not result.moves:
                    result.problems.append(('traffic_no_road', 'no road to turn onto: the game logs "No eligible roads '
                                            'identified to turn onto from road ' + str(bai_road.index) + '"'))
                for move in result.moves:
                    angle = self.turn_angle(road, side, move.road, move.side)
                    move.turn = (U_TURN if abs(angle) > U_TURN_ANGLE else RIGHT if angle > TURN_ANGLE
                                 else LEFT if angle < -TURN_ANGLE else STRAIGHT)
                    move.points = self.path(road, side, lane, move)
                    if move.lane >= move.road.count[move.side]:
                        result.problems.append(('traffic_lane_unchecked', 'the game keeps the lane number of the car on '
                                                + move.road.road.name + ', which has only '
                                                + str(move.road.count[move.side]) + ' lanes that way: it may crash '
                                                '(0x5440c5)'))
                res.append(result)
        return res
